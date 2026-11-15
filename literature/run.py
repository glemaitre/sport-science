import sys
from datetime import date
from pathlib import Path

import httpx

from literature.classify import screen_papers, write_notes
from literature.config import Config, load_config, openalex_mailto, openrouter_key
from literature.db import (
    connect,
    current_watermark,
    finish_run,
    insert_work,
    journal_issns,
    migrate,
    needs_note,
    needs_screen,
    replace_journals,
    rows_by_ids,
    run_counts,
    save_note,
    save_screen,
    start_run,
    unclassified_count,
)
from literature.journals import download_scimago, parse_scimago_csv
from literature.openalex import fetch_works
from literature.page import write_papers_js


def chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def next_watermark(
    watermark_before: str,
    unclassified: int,
    fetch_complete: bool,
    failed: int,
    today: str,
) -> str:
    if unclassified == 0 and fetch_complete and failed == 0:
        return today
    return watermark_before


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


def _note_batch(client, connection, key: str, config: Config, rows, run_id: int) -> int:
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
        save_note(connection, row["openalex_id"], note, config.model, run_id)
    return failed


def _classify(connection, config: Config, run_id: int, key: str) -> int:
    failed = 0
    budget = config.max_papers
    with httpx.Client(timeout=120) as client:
        pending_notes = needs_note(connection, config.keep_threshold, budget)
        for batch in chunks(pending_notes, config.note_batch):
            failed += _note_batch(client, connection, key, config, batch, run_id)
            budget -= len(batch)
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
                )
                if result["score"] >= config.keep_threshold:
                    kept_ids.append(row["openalex_id"])
            for note_batch in chunks(rows_by_ids(connection, kept_ids), config.note_batch):
                failed += _note_batch(client, connection, key, config, note_batch, run_id)
    return failed


def run_literature() -> int:
    config = load_config()
    connection = connect()
    try:
        migrate(connection)
        issns = journal_issns(connection)
        if not issns:
            print("No journals stored. Run: pixi run literature-journals", file=sys.stderr)
            return 1
        watermark_before = current_watermark(connection, config.lookback_days)
        run_id = start_run(connection, watermark_before)
        try:
            with httpx.Client(timeout=45, follow_redirects=True) as client:
                works, fetch_complete = fetch_works(
                    issns,
                    watermark_before,
                    openalex_mailto(),
                    client,
                    config.fetch_cap,
                )
            inserted = 0
            with connection:
                for work in works:
                    if insert_work(connection, work):
                        inserted += 1
            print(f"Fetched {len(works)} works since {watermark_before}. {inserted} were new.")
            waiting = unclassified_count(connection)
            key = openrouter_key()
            failed = 0
            if waiting and not key:
                print(
                    "OPENROUTER_API_KEY is missing. "
                    "Add it to .env, or to the Actions secret of the same name.",
                    file=sys.stderr,
                )
                failed = waiting
            elif waiting:
                failed = _classify(connection, config, run_id, key)
            scanned, kept = run_counts(connection, run_id)
            watermark_after = next_watermark(
                watermark_before,
                unclassified_count(connection),
                fetch_complete,
                failed,
                date.today().isoformat(),
            )
            finish_run(connection, run_id, watermark_after, scanned, kept)
            write_papers_js(connection)
            print(f"Classified {scanned} papers this run. Kept {kept}.")
            if failed and scanned == 0:
                return 1
            return 0
        except (httpx.HTTPError, ValueError) as exc:
            finish_run(connection, run_id, watermark_before, *run_counts(connection, run_id))
            write_papers_js(connection)
            print(exc, file=sys.stderr)
            return 1
    finally:
        connection.close()
