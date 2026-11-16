import argparse
from datetime import date

from dotenv import load_dotenv

from literature.config import ROOT
from literature.run import (
    classify_waiting,
    fetch_month,
    import_triage,
    refresh_journals,
    rescreen,
    run_literature,
    within_last_month,
)

# About two seconds per paper, so 3000 fits inside the workflow's 150-minute timeout.
MAX_BACKFILL = 3000


def _iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value} is not a date like 2026-01-01.") from exc


def _last_month_date(value: str) -> str:
    try:
        return within_last_month(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _papers(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value} is not a whole number.") from exc
    if number < 0 or number > MAX_BACKFILL:
        raise argparse.ArgumentTypeError(f"--papers is between 0 and {MAX_BACKFILL}.")
    return number


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m literature")
    commands = root.add_subparsers(dest="command")

    journals = commands.add_parser("journals", help="Refresh the SCImago journal list.")
    journals.add_argument("--csv", help="A CSV saved from the SCImago Download link.")

    backfill = commands.add_parser("backfill", help="Classify more of the waiting papers.")
    backfill.add_argument("--papers", type=_papers, default=200)
    backfill.add_argument("--since", type=_iso_date, help="Read OpenAlex back to this date first.")

    fetch = commands.add_parser("fetch", help="Read the last month from OpenAlex, without classifying.")
    fetch.add_argument("--since", type=_last_month_date, required=True)

    commands.add_parser("classify", help="Classify every paper still waiting.")

    again = commands.add_parser("rescreen", help="Queue papers screened with an older prompt.")
    again.add_argument("--all", action="store_true", help="Include dropped papers too.")

    triage = commands.add_parser("triage", help="Load a triage file exported from the page.")
    triage.add_argument("path")

    app = commands.add_parser("app", help="Serve the page with triage and backfill.")
    app.add_argument("--port", type=int, default=8766)
    return root


def main(argv: list[str]) -> int:
    load_dotenv(ROOT / ".env")
    args = parser().parse_args(argv)
    if args.command is None:
        return run_literature()
    if args.command == "journals":
        return refresh_journals(args.csv)
    if args.command == "backfill":
        return run_literature(max_papers=args.papers, since=args.since)
    if args.command == "fetch":
        return fetch_month(args.since)
    if args.command == "classify":
        return classify_waiting()
    if args.command == "rescreen":
        return rescreen(include_dropped=args.all)
    if args.command == "triage":
        return import_triage(args.path)
    if args.command == "app":
        from literature.server import serve

        return serve(args.port)
    return 2
