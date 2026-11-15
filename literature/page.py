import json
import sqlite3
from pathlib import Path

from literature.config import PAPERS_JS
from literature.db import classified_papers, latest_run_id


def paper_payload(row: sqlite3.Row) -> dict:
    published_on = row["published_on"] or ""
    return {
        "id": row["openalex_id"],
        "doi": row["doi"] or "",
        "title": row["title"],
        "authors": row["authors"] or "",
        "published_on": published_on,
        "year": published_on[:4],
        "journal": row["journal_title"] or "",
        "score": row["score"],
        "keep": bool(row["keep"]),
        "kind": row["kind"] or "",
        "sport": row["sport"] or "",
        "why": row["why"] or "",
        "learn": row["learn"] or "",
        "lecture": row["lecture"] or "",
        "abstract_missing": bool(row["abstract_missing"]),
        "run_id": row["run_id"],
    }


def render_papers_js(papers: list[dict], latest: int | None) -> str:
    body = json.dumps(papers, ensure_ascii=True, indent=2)
    latest_text = "null" if latest is None else str(int(latest))
    return f"window.PAPERS = {body};\nwindow.LATEST_RUN_ID = {latest_text};\n"


def write_papers_js(connection: sqlite3.Connection, destination: Path | None = None) -> str:
    papers = [paper_payload(row) for row in classified_papers(connection)]
    text = render_papers_js(papers, latest_run_id(connection))
    path = destination or PAPERS_JS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text
