import calendar
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

from literature.classify import note_version, screen_papers, screen_version, write_notes
from literature.config import Config, load_config, openalex_key, openalex_mailto, openrouter_key
from literature.db import (
    connect,
    coverage,
    finish_run,
    insert_work,
    journal_issns,
    journal_progress,
    migrate,
    needs_note,
    needs_screen,
    replace_journals,
    reset_classification,
    rows_by_ids,
    run_counts,
    save_note,
    save_progress,
    save_screen,
    set_triage,
    stale_ids,
    start_run,
    unclassified_count,
)
from literature.journals import download_scimago, parse_scimago_csv
from literature.openalex import fetch_works
from literature.page import write_papers_js


def month_before(today: date) -> date:
    """The same day in the previous month, clipped when that month is shorter."""
    year, month = today.year, today.month - 1
    if month == 0:
        year, month = year - 1, 12
    day = min(today.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def within_last_month(value: str, today: date | None = None) -> str:
    """Accept a date from one month ago through today."""
    current = date.today() if today is None else today
    try:
        chosen = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("since is a date like 2026-01-01.") from exc
    earliest = month_before(current)
    if chosen < earliest or chosen > current:
        raise ValueError(f"since is from {earliest.isoformat()} through {current.isoformat()}.")
    return chosen.isoformat()


def chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def forward_windows(
    progress: dict[str, tuple[str | None, str | None]], overlap_days: int
) -> list[tuple[str, list[str]]]:
    """Open-ended windows from the last read date minus the overlap, grouped by start."""
    groups: dict[str, list[str]] = {}
    for issn, (_, fetched_through) in progress.items():
        if not fetched_through:
            continue
        since = (date.fromisoformat(fetched_through) - timedelta(days=overlap_days)).isoformat()
        groups.setdefault(since, []).append(issn)
    return sorted(groups.items())


def backward_window(
    progress: dict[str, tuple[str | None, str | None]], start: str, today: str
) -> tuple[str, str, list[str]] | None:
    """The next calendar month to read backwards, for the journals furthest from the start."""
    first_day = date.fromisoformat(start)
    ends: dict[date, list[str]] = {}
    for issn, (fetched_from, _) in progress.items():
        if fetched_from:
            end = date.fromisoformat(fetched_from) - timedelta(days=1)
        else:
            end = date.fromisoformat(today)
        if end < first_day:
            continue
        ends.setdefault(end, []).append(issn)
    if not ends:
        return None
    end = max(ends)
    since = max(end.replace(day=1), first_day)
    return since.isoformat(), end.isoformat(), sorted(ends[end])


def _store(connection, works: list[dict]) -> int:
    inserted = 0
    with connection:
        for work in works:
            if insert_work(connection, work):
                inserted += 1
    return inserted


def _fetch_window(connection, config: Config, issns: list[str], since: str, today: str) -> tuple[int, int, bool]:
    """Read one publication window. Does not move journal progress."""
    mailto = openalex_mailto()
    key = openalex_key()
    fetched = 0
    inserted = 0
    try:
        with httpx.Client(timeout=45, follow_redirects=True) as client:
            works, complete = fetch_works(
                issns, since, mailto, client, config.fetch_cap, to_date=today, api_key=key
            )
            fetched = len(works)
            inserted = _store(connection, works)
            if not complete:
                return fetched, inserted, True
    except httpx.HTTPError as exc:
        print(f"OpenAlex request failed: {exc}", file=sys.stderr)
        response = getattr(exc, "response", None)
        if response is not None and response.status_code in {401, 429}:
            print(
                "Without OPENALEX_API_KEY, OpenAlex shares one small daily budget per IP address. "
                "A free key is at https://openalex.org/settings/api.",
                file=sys.stderr,
            )
        return fetched, inserted, True
    return fetched, inserted, False


def fetch_month(since: str) -> int:
    """Read OpenAlex from since through today and report how many papers are unclassified.

    since has to fall in the last month. Journal progress is left unchanged.
    """
    try:
        since = within_last_month(since)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    config = load_config()
    today = date.today().isoformat()
    connection = connect()
    try:
        migrate(connection)
        issns = journal_issns(connection)
        if not issns:
            print("No journals stored. Run: pixi run literature-journals", file=sys.stderr)
            return 1
        fetched, inserted, fetch_failed = _fetch_window(connection, config, issns, since, today)
        waiting = unclassified_count(connection)
        print(f"Fetched {fetched} works. {inserted} were new. {waiting} need classification.")
        return 1 if fetch_failed else 0
    finally:
        connection.close()


def classify_waiting() -> int:
    """Screen every paper still waiting. Does not call OpenAlex."""
    config = load_config()
    connection = connect()
    try:
        migrate(connection)
        waiting = unclassified_count(connection)
        if waiting == 0:
            print("Nothing is waiting for classification.")
            return 0
        key = openrouter_key()
        if not key:
            print(
                "OPENROUTER_API_KEY is missing. "
                "Add it to .env, or to the Actions secret of the same name.",
                file=sys.stderr,
            )
            return 1
        run_id = start_run(connection)
        failed = _classify(connection, config, run_id, key, waiting)
        scanned, kept = run_counts(connection, run_id)
        finish_run(connection, run_id, scanned, kept)
        write_papers_js(connection)
        left = unclassified_count(connection)
        print(f"Classified {scanned} papers this run. Kept {kept}. {left} are waiting.")
        if failed and scanned == 0:
            return 1
        return 0
    finally:
        connection.close()


def fetch_new(connection, config: Config, start: str, today: str) -> tuple[int, int, bool]:
    """Read OpenAlex forward from each journal's last date, then backward toward start.

    Returns works read, works new to the database, and whether a request failed.
    """
    budget = config.fetch_cap
    fetched = 0
    inserted = 0
    mailto = openalex_mailto()
    key = openalex_key()
    try:
        with httpx.Client(timeout=45, follow_redirects=True) as client:
            for since, issns in forward_windows(journal_progress(connection), config.overlap_days):
                if budget <= 0:
                    return fetched, inserted, False
                works, complete = fetch_works(issns, since, mailto, client, budget, api_key=key)
                budget -= len(works)
                fetched += len(works)
                inserted += _store(connection, works)
                if not complete:
                    return fetched, inserted, False
                save_progress(connection, issns, fetched_through=today)
            while budget > 0:
                window = backward_window(journal_progress(connection), start, today)
                if window is None:
                    break
                since, until, issns = window
                works, complete = fetch_works(
                    issns, since, mailto, client, budget, to_date=until, api_key=key
                )
                budget -= len(works)
                fetched += len(works)
                inserted += _store(connection, works)
                if not complete:
                    break
                save_progress(connection, issns, fetched_from=since, fetched_through=until)
    except httpx.HTTPError as exc:
        print(f"OpenAlex request failed: {exc}", file=sys.stderr)
        response = getattr(exc, "response", None)
        if response is not None and response.status_code in {401, 429}:
            print(
                "Without OPENALEX_API_KEY, OpenAlex shares one small daily budget per IP address. "
                "A free key is at https://openalex.org/settings/api.",
                file=sys.stderr,
            )
        return fetched, inserted, True
    return fetched, inserted, False


def refresh_journals(csv_path: str | None = None) -> int:
    config = load_config()
    try:
        if csv_path:
            text = Path(csv_path).read_text(encoding="utf-8")
        else:
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                text = download_scimago(config.scimago_area, config.scimago_category, client)
        journals = parse_scimago_csv(text)
    except (OSError, httpx.HTTPError, ValueError) as exc:
        print(exc, file=sys.stderr)
        print("The stored journal list was left unchanged.", file=sys.stderr)
        return 1
    if not journals:
        print("No Q1 or Q2 journals were found. The stored list was left unchanged.", file=sys.stderr)
        return 1
    connection = connect()
    try:
        migrate(connection)
        replace_journals(
            connection,
            [
                {
                    "issn": journal.issn,
                    "title": journal.title,
                    "sjr": journal.sjr,
                    "quartile": journal.quartile,
                }
                for journal in journals
            ],
        )
    finally:
        connection.close()
    titles = {journal.title for journal in journals}
    print(f"Stored {len(journals)} ISSNs from {len(titles)} Q1 and Q2 journals.")
    return 0


def _note_batch(client, connection, key: str, config: Config, rows, run_id: int, version: str) -> int:
    if not rows:
        return 0
    try:
        notes = write_notes(client, key, config, rows)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        print(f"Learning-note call failed: {exc}", file=sys.stderr)
        return len(rows)
    failed = 0
    for row in rows:
        note = notes.get(row["openalex_id"])
        if note is None:
            failed += 1
            print(f"No learning note for {row['openalex_id']}.", file=sys.stderr)
            continue
        save_note(connection, row["openalex_id"], note, config.model, run_id, version)
    return failed


def _classify(connection, config: Config, run_id: int, key: str, budget: int) -> int:
    failed = 0
    screen_tag = screen_version(config.model)
    note_tag = note_version(config.model)
    with httpx.Client(timeout=120) as client:
        pending_notes = needs_note(connection, config.keep_threshold, budget)
        for batch in chunks(pending_notes, config.note_batch):
            failed += _note_batch(client, connection, key, config, batch, run_id, note_tag)
            budget -= len(batch)
        screened_n = 0
        kept_n = 0
        for batch in chunks(needs_screen(connection, max(budget, 0)), config.screen_batch):
            try:
                screened = screen_papers(client, key, config, batch)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                print(f"Screening call failed: {exc}", file=sys.stderr)
                failed += len(batch)
                continue
            kept_ids = []
            for row in batch:
                result = screened.get(row["openalex_id"])
                if result is None:
                    failed += 1
                    print(f"No score for {row['openalex_id']}.", file=sys.stderr)
                    continue
                save_screen(
                    connection,
                    row["openalex_id"],
                    result,
                    config.keep_threshold,
                    config.model,
                    run_id,
                    screen_tag,
                )
                if result["score"] >= config.keep_threshold:
                    kept_ids.append(row["openalex_id"])
            kept_n += len(kept_ids)
            for note_batch in chunks(rows_by_ids(connection, kept_ids), config.note_batch):
                failed += _note_batch(
                    client, connection, key, config, note_batch, run_id, note_tag
                )
            screened_n += len(batch)
            print(
                f"Screened {screened_n} this run. Kept {kept_n}. {failed} failed.",
                flush=True,
            )
    return failed


def run_literature(max_papers: int | None = None, since: str | None = None) -> int:
    """Fetch, classify up to max_papers from the queue, and rewrite the page.

    since reaches further back than start_date in config.toml, for one backfill.
    """
    config = load_config()
    start = min(config.start_date, since) if since else config.start_date
    budget = config.max_papers if max_papers is None else max_papers
    today = date.today().isoformat()
    connection = connect()
    try:
        migrate(connection)
        if not journal_issns(connection):
            print("No journals stored. Run: pixi run literature-journals", file=sys.stderr)
            return 1
        run_id = start_run(connection)
        fetched, inserted, fetch_failed = fetch_new(connection, config, start, today)
        covered_from, covered_through = coverage(connection)
        span = (
            f" Every journal is read from {covered_from} to {covered_through}."
            if covered_from
            else ""
        )
        print(f"Fetched {fetched} works. {inserted} were new.{span}")
        waiting = unclassified_count(connection)
        key = openrouter_key()
        failed = 1 if fetch_failed else 0
        if waiting and budget > 0 and not key:
            print(
                "OPENROUTER_API_KEY is missing. "
                "Add it to .env, or to the Actions secret of the same name.",
                file=sys.stderr,
            )
            failed += waiting
        elif waiting and budget > 0:
            failed += _classify(connection, config, run_id, key, budget)
        scanned, kept = run_counts(connection, run_id)
        finish_run(connection, run_id, scanned, kept)
        write_papers_js(connection)
        left = unclassified_count(connection)
        print(f"Classified {scanned} papers this run. Kept {kept}. {left} are waiting.")
        if failed and scanned == 0:
            return 1
        return 0
    finally:
        connection.close()


def rescreen(include_dropped: bool = False) -> int:
    config = load_config()
    connection = connect()
    try:
        migrate(connection)
        ids = stale_ids(connection, screen_version(config.model), include_dropped)
        reset_classification(connection, ids)
        write_papers_js(connection)
    finally:
        connection.close()
    which = "screened" if include_dropped else "kept"
    print(
        f"Sent {len(ids)} {which} papers with an older screen back to the queue. "
        "The next run screens them again."
    )
    return 0


def parse_triage_file(text: str) -> dict[str, str]:
    data = json.loads(text)
    if isinstance(data, dict) and isinstance(data.get("triage"), dict):
        data = data["triage"]
    if isinstance(data, list):
        data = {str(item.get("id")): str(item.get("status") or "") for item in data if isinstance(item, dict)}
    if not isinstance(data, dict):
        raise ValueError("A triage file is a JSON object of OpenAlex id to status.")
    return {str(key): str(value or "") for key, value in data.items()}


def import_triage(path: str) -> int:
    try:
        marks = parse_triage_file(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    connection = connect()
    stored = 0
    skipped = 0
    try:
        migrate(connection)
        for openalex_id, status in marks.items():
            try:
                set_triage(connection, openalex_id, status)
                stored += 1
            except (KeyError, ValueError) as exc:
                skipped += 1
                print(f"Skipped {openalex_id}: {exc}", file=sys.stderr)
        write_papers_js(connection)
    finally:
        connection.close()
    print(f"Stored {stored} triage marks. Skipped {skipped}.")
    return 0 if stored or not marks else 1
