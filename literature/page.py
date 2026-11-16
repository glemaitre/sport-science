import json
import sqlite3
from pathlib import Path

from literature.config import PAPERS_JS, load_config
from literature.db import all_papers, coverage, latest_run_id, status_counts


def job_status(row: sqlite3.Row) -> str:
    if row["classified_at"] is None:
        return "unclassified"
    return "of-interest" if row["keep"] == 1 else "discarded"


def paper_payload(row: sqlite3.Row) -> dict:
    published_on = row["published_on"] or ""
    status = job_status(row)
    paper = {
        "id": row["openalex_id"],
        "doi": row["doi"] or "",
        "title": row["title"],
        "authors": row["authors"] or "",
        "published_on": published_on,
        "year": published_on[:4],
        "journal": row["journal_title"] or "",
        "status": status,
        "triage": row["triage"] or "",
        "summary": row["summary"] or "" if "summary" in row.keys() else "",
        "file_url": row["file_url"] or "" if "file_url" in row.keys() else "",
        "abstract_missing": bool(row["abstract_missing"]),
    }
    if status == "unclassified":
        paper.update({"score": None, "kind": "", "sport": "", "why": "", "learn": "", "run_id": None})
        return paper
    paper.update(
        {
            "score": row["score"],
            "kind": row["kind"] or "",
            "sport": row["sport"] or "",
            "why": row["why"] or "",
            "learn": row["learn"] or "",
            "run_id": row["run_id"],
        }
    )
    return paper


def library_payload(connection: sqlite3.Connection, start_date: str) -> dict:
    covered_from, covered_through = coverage(connection)
    return {
        "start_date": start_date,
        "covered_from": covered_from,
        "covered_through": covered_through,
        "counts": status_counts(connection),
    }


def render_papers_js(papers: list[dict], latest: int | None, library: dict | None = None) -> str:
    lines = [json.dumps(paper, ensure_ascii=True, separators=(",", ":")) for paper in papers]
    body = "[\n" + ",\n".join(lines) + "\n]" if lines else "[]"
    latest_text = "null" if latest is None else str(int(latest))
    library_text = json.dumps(library or {}, ensure_ascii=True, separators=(",", ":"))
    return (
        f"window.PAPERS = {body};\n"
        f"window.LATEST_RUN_ID = {latest_text};\n"
        f"window.LIBRARY = {library_text};\n"
    )


def build_papers_js(connection: sqlite3.Connection) -> str:
    papers = [paper_payload(row) for row in all_papers(connection)]
    library = library_payload(connection, load_config().start_date)
    return render_papers_js(papers, latest_run_id(connection), library)


def write_papers_js(connection: sqlite3.Connection, destination: Path | None = None) -> str:
    text = build_papers_js(connection)
    path = destination or PAPERS_JS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text
