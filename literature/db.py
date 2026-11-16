import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from literature.config import DB_PATH

TRIAGE_STATUSES = ("to-read", "read", "useful", "not-relevant")
SUMMARY_LIMIT = 50_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS journals (
    issn TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    sjr REAL,
    quartile TEXT NOT NULL,
    refreshed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS papers (
    openalex_id TEXT PRIMARY KEY,
    doi TEXT,
    title TEXT NOT NULL,
    abstract TEXT,
    abstract_missing INTEGER NOT NULL DEFAULT 0,
    journal_issn TEXT,
    journal_title TEXT,
    published_on TEXT,
    authors TEXT,
    fetched_at TEXT NOT NULL,
    score INTEGER,
    keep INTEGER,
    kind TEXT,
    sport TEXT,
    why TEXT,
    learn TEXT,
    model TEXT,
    screen_version TEXT,
    note_version TEXT,
    classified_at TEXT,
    run_id INTEGER
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    scanned INTEGER,
    kept INTEGER
);

CREATE TABLE IF NOT EXISTS journal_progress (
    issn TEXT PRIMARY KEY,
    fetched_from TEXT,
    fetched_through TEXT
);

CREATE TABLE IF NOT EXISTS triage (
    openalex_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS summary (
    openalex_id TEXT PRIMARY KEY,
    markdown TEXT NOT NULL,
    file_url TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS papers_classified ON papers (classified_at);
CREATE INDEX IF NOT EXISTS papers_published ON papers (published_on);
CREATE INDEX IF NOT EXISTS papers_run ON papers (run_id);
"""

PAPER_COLUMNS = {"screen_version": "TEXT", "note_version": "TEXT"}
SUMMARY_COLUMNS = {"file_url": "TEXT NOT NULL DEFAULT ''"}
URL_LIMIT = 2_000


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: Path | None = None) -> sqlite3.Connection:
    database = path or DB_PATH
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}


def migrate(connection: sqlite3.Connection) -> None:
    progress_existed = "journal_progress" in {
        row["name"]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    connection.executescript(SCHEMA)
    existing = _columns(connection, "papers")
    for name, kind in PAPER_COLUMNS.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE papers ADD COLUMN {name} {kind}")
    summary_columns = _columns(connection, "summary")
    for name, kind in SUMMARY_COLUMNS.items():
        if name not in summary_columns:
            connection.execute(f"ALTER TABLE summary ADD COLUMN {name} {kind}")
    if not progress_existed:
        _seed_progress_from_runs(connection)
    connection.commit()


def _seed_progress_from_runs(connection: sqlite3.Connection) -> None:
    """Carry the range read by the old single-watermark runs into journal_progress."""
    if "watermark_before" not in _columns(connection, "runs"):
        return
    row = connection.execute(
        """
        SELECT MIN(watermark_before) AS since, MAX(finished_at) AS until
        FROM runs WHERE finished_at IS NOT NULL AND watermark_before IS NOT NULL
        """
    ).fetchone()
    if row is None or not row["since"] or not row["until"]:
        return
    connection.execute(
        """
        INSERT OR IGNORE INTO journal_progress (issn, fetched_from, fetched_through)
        SELECT issn, ?, ? FROM journals
        """,
        (row["since"], row["until"][:10]),
    )


def replace_journals(connection: sqlite3.Connection, journals: list[dict]) -> None:
    refreshed_at = utc_now()
    with connection:
        connection.execute("DELETE FROM journals")
        connection.executemany(
            """
            INSERT INTO journals (issn, title, sjr, quartile, refreshed_at)
            VALUES (:issn, :title, :sjr, :quartile, :refreshed_at)
            """,
            [{**journal, "refreshed_at": refreshed_at} for journal in journals],
        )


def journal_issns(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT issn FROM journals ORDER BY sjr DESC, title, issn"
    ).fetchall()
    return [row["issn"] for row in rows]


def journal_progress(connection: sqlite3.Connection) -> dict[str, tuple[str | None, str | None]]:
    """Fetched range for every stored journal. A journal never fetched maps to (None, None)."""
    rows = connection.execute(
        """
        SELECT journals.issn AS issn, progress.fetched_from, progress.fetched_through
        FROM journals
        LEFT JOIN journal_progress AS progress ON progress.issn = journals.issn
        """
    ).fetchall()
    return {row["issn"]: (row["fetched_from"], row["fetched_through"]) for row in rows}


def save_progress(
    connection: sqlite3.Connection,
    issns: list[str],
    fetched_from: str | None = None,
    fetched_through: str | None = None,
) -> None:
    with connection:
        for issn in issns:
            connection.execute(
                "INSERT OR IGNORE INTO journal_progress (issn) VALUES (?)", (issn,)
            )
            if fetched_from is not None:
                connection.execute(
                    """
                    UPDATE journal_progress
                    SET fetched_from = CASE
                        WHEN fetched_from IS NULL OR fetched_from > ? THEN ? ELSE fetched_from END
                    WHERE issn = ?
                    """,
                    (fetched_from, fetched_from, issn),
                )
            if fetched_through is not None:
                connection.execute(
                    """
                    UPDATE journal_progress
                    SET fetched_through = CASE
                        WHEN fetched_through IS NULL OR fetched_through < ? THEN ? ELSE fetched_through END
                    WHERE issn = ?
                    """,
                    (fetched_through, fetched_through, issn),
                )


def coverage(connection: sqlite3.Connection) -> tuple[str | None, str | None]:
    """The range every stored journal has been read over."""
    row = connection.execute(
        """
        SELECT MAX(progress.fetched_from) AS since, MIN(progress.fetched_through) AS until,
               SUM(CASE WHEN progress.issn IS NULL OR progress.fetched_from IS NULL THEN 1 ELSE 0 END)
                   AS missing
        FROM journals
        LEFT JOIN journal_progress AS progress ON progress.issn = journals.issn
        """
    ).fetchone()
    if row is None or row["missing"]:
        return None, None
    return row["since"], row["until"]


def start_run(connection: sqlite3.Connection) -> int:
    with connection:
        cursor = connection.execute("INSERT INTO runs (started_at) VALUES (?)", (utc_now(),))
        return int(cursor.lastrowid)


def finish_run(connection: sqlite3.Connection, run_id: int, scanned: int, kept: int) -> None:
    with connection:
        connection.execute(
            "UPDATE runs SET finished_at = ?, scanned = ?, kept = ? WHERE id = ?",
            (utc_now(), scanned, kept, run_id),
        )


def insert_work(connection: sqlite3.Connection, work: dict) -> bool:
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO papers (
            openalex_id, doi, title, abstract, abstract_missing,
            journal_issn, journal_title, published_on, authors, fetched_at
        ) VALUES (
            :openalex_id, :doi, :title, :abstract, :abstract_missing,
            :journal_issn, :journal_title, :published_on, :authors, :fetched_at
        )
        """,
        work,
    )
    return cursor.rowcount == 1


def unclassified_count(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT COUNT(*) AS n FROM papers WHERE classified_at IS NULL"
    ).fetchone()
    return int(row["n"])


def needs_screen(connection: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    if limit <= 0:
        return []
    return list(
        connection.execute(
            """
            SELECT * FROM papers
            WHERE classified_at IS NULL AND score IS NULL
            ORDER BY published_on DESC, openalex_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    )


def rows_by_ids(connection: sqlite3.Connection, ids: list[str]) -> list[sqlite3.Row]:
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    rows = connection.execute(
        f"""
        SELECT * FROM papers
        WHERE openalex_id IN ({marks}) AND classified_at IS NULL
        """,
        ids,
    ).fetchall()
    order = {paper_id: index for index, paper_id in enumerate(ids)}
    return sorted(rows, key=lambda row: order.get(row["openalex_id"], 0))


def needs_note(
    connection: sqlite3.Connection, keep_threshold: int, limit: int
) -> list[sqlite3.Row]:
    if limit <= 0:
        return []
    return list(
        connection.execute(
            """
            SELECT * FROM papers
            WHERE classified_at IS NULL AND score IS NOT NULL AND score >= ?
            ORDER BY published_on DESC, openalex_id
            LIMIT ?
            """,
            (keep_threshold, limit),
        ).fetchall()
    )


def save_screen(
    connection: sqlite3.Connection,
    openalex_id: str,
    result: dict,
    keep_threshold: int,
    model: str,
    run_id: int,
    version: str = "",
) -> None:
    score = result["score"]
    keep = 1 if score >= keep_threshold else 0
    classified_at = None if keep else utc_now()
    stored_run = None if keep else run_id
    with connection:
        connection.execute(
            """
            UPDATE papers
            SET score = ?, keep = ?, kind = ?, sport = ?, why = ?,
                model = ?, screen_version = ?, classified_at = ?, run_id = ?
            WHERE openalex_id = ? AND classified_at IS NULL
            """,
            (
                score,
                keep,
                result.get("kind") or "",
                result.get("sport") or "",
                result.get("why") or "",
                model,
                version or None,
                classified_at,
                stored_run,
                openalex_id,
            ),
        )


def save_note(
    connection: sqlite3.Connection,
    openalex_id: str,
    result: dict,
    model: str,
    run_id: int,
    version: str = "",
) -> None:
    with connection:
        connection.execute(
            """
            UPDATE papers
            SET learn = ?, model = ?, note_version = ?, classified_at = ?, run_id = ?,
                keep = 1
            WHERE openalex_id = ? AND classified_at IS NULL
            """,
            (
                result.get("learn") or "",
                model,
                version or None,
                utc_now(),
                run_id,
                openalex_id,
            ),
        )


def stale_ids(
    connection: sqlite3.Connection, version: str, include_dropped: bool = False
) -> list[str]:
    """Screened papers whose screen was made with another prompt, brief, or model."""
    keep_clause = "" if include_dropped else "AND keep = 1"
    rows = connection.execute(
        f"""
        SELECT openalex_id FROM papers
        WHERE score IS NOT NULL
          AND (screen_version IS NULL OR screen_version != ?)
          {keep_clause}
        ORDER BY published_on DESC, openalex_id
        """,
        (version,),
    ).fetchall()
    return [row["openalex_id"] for row in rows]


def reset_classification(connection: sqlite3.Connection, ids: list[str]) -> int:
    """Send papers back to the queue. Triage, your summary, and the stored URL live in their own tables."""
    with connection:
        for openalex_id in ids:
            connection.execute(
                """
                UPDATE papers
                SET score = NULL, keep = NULL, kind = NULL, sport = NULL, why = NULL,
                    learn = NULL, model = NULL, screen_version = NULL, note_version = NULL,
                    classified_at = NULL, run_id = NULL
                WHERE openalex_id = ?
                """,
                (openalex_id,),
            )
    return len(ids)


def run_counts(connection: sqlite3.Connection, run_id: int) -> tuple[int, int]:
    row = connection.execute(
        """
        SELECT
            COUNT(*) AS scanned,
            COALESCE(SUM(CASE WHEN keep = 1 THEN 1 ELSE 0 END), 0) AS kept
        FROM papers
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    return int(row["scanned"]), int(row["kept"])


def latest_run_id(connection: sqlite3.Connection) -> int | None:
    """The newest run that kept a paper, so the default view is never empty after a small run."""
    row = connection.execute(
        """
        SELECT id FROM runs
        WHERE finished_at IS NOT NULL AND kept > 0
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def status_counts(connection: sqlite3.Connection) -> dict[str, int]:
    row = connection.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN classified_at IS NULL THEN 1 ELSE 0 END), 0) AS unclassified,
            COALESCE(SUM(CASE WHEN classified_at IS NOT NULL AND keep = 1 THEN 1 ELSE 0 END), 0)
                AS of_interest,
            COALESCE(SUM(CASE WHEN classified_at IS NOT NULL AND keep = 0 THEN 1 ELSE 0 END), 0)
                AS discarded
        FROM papers
        """
    ).fetchone()
    return {
        "unclassified": int(row["unclassified"]),
        "of-interest": int(row["of_interest"]),
        "discarded": int(row["discarded"]),
    }


def all_papers(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT papers.*, triage.status AS triage,
                COALESCE(summary.markdown, '') AS summary,
                COALESCE(summary.file_url, '') AS file_url
            FROM papers
            LEFT JOIN triage ON triage.openalex_id = papers.openalex_id
            LEFT JOIN summary ON summary.openalex_id = papers.openalex_id
            ORDER BY papers.published_on DESC, papers.openalex_id
            """
        ).fetchall()
    )


def _require_paper(connection: sqlite3.Connection, openalex_id: str) -> None:
    exists = connection.execute(
        "SELECT 1 FROM papers WHERE openalex_id = ?", (openalex_id,)
    ).fetchone()
    if exists is None:
        raise KeyError(openalex_id)


def http_url(value: str) -> str:
    """An http or https URL, or an empty string when the field is cleared."""
    if not isinstance(value, str):
        raise ValueError("A URL is text.")
    text = value.strip()
    if not text:
        return ""
    if len(text) > URL_LIMIT:
        raise ValueError(f"A URL is at most {URL_LIMIT} characters.")
    parts = urlsplit(text)
    if parts.scheme not in {"http", "https"} or not parts.netloc or " " in parts.netloc:
        raise ValueError("A URL starts with http:// or https://.")
    return text


def _drop_empty_summary(connection: sqlite3.Connection, openalex_id: str) -> None:
    connection.execute(
        """
        DELETE FROM summary
        WHERE openalex_id = ? AND markdown = '' AND file_url = ''
        """,
        (openalex_id,),
    )


def set_summary(connection: sqlite3.Connection, openalex_id: str, markdown: str) -> str:
    """Store your markdown note. Blank text clears it and keeps a stored URL."""
    if not isinstance(markdown, str):
        raise ValueError("A summary is text.")
    if len(markdown) > SUMMARY_LIMIT:
        raise ValueError(f"A summary is at most {SUMMARY_LIMIT} characters.")
    _require_paper(connection, openalex_id)
    text = markdown.strip()
    with connection:
        if text:
            connection.execute(
                """
                INSERT INTO summary (openalex_id, markdown, updated_at) VALUES (?, ?, ?)
                ON CONFLICT (openalex_id) DO UPDATE
                SET markdown = excluded.markdown, updated_at = excluded.updated_at
                """,
                (openalex_id, text, utc_now()),
            )
        else:
            connection.execute(
                "UPDATE summary SET markdown = '', updated_at = ? WHERE openalex_id = ?",
                (utc_now(), openalex_id),
            )
            _drop_empty_summary(connection, openalex_id)
    return text


def set_file_url(connection: sqlite3.Connection, openalex_id: str, url: str) -> str:
    """Store where you keep this paper. A blank value clears the link and keeps the summary."""
    stored = http_url(url)
    _require_paper(connection, openalex_id)
    with connection:
        if stored:
            connection.execute(
                """
                INSERT INTO summary (openalex_id, markdown, file_url, updated_at)
                VALUES (?, '', ?, ?)
                ON CONFLICT (openalex_id) DO UPDATE
                SET file_url = excluded.file_url, updated_at = excluded.updated_at
                """,
                (openalex_id, stored, utc_now()),
            )
        else:
            connection.execute(
                "UPDATE summary SET file_url = '', updated_at = ? WHERE openalex_id = ?",
                (utc_now(), openalex_id),
            )
            _drop_empty_summary(connection, openalex_id)
    return stored


def paper_record(connection: sqlite3.Connection, openalex_id: str) -> dict:
    """The abstract, your summary, and where you store the paper. The abstract stays off the public page."""
    row = connection.execute(
        """
        SELECT papers.abstract AS abstract, papers.abstract_missing AS abstract_missing,
            COALESCE(summary.markdown, '') AS summary,
            COALESCE(summary.file_url, '') AS file_url
        FROM papers
        LEFT JOIN summary ON summary.openalex_id = papers.openalex_id
        WHERE papers.openalex_id = ?
        """,
        (openalex_id,),
    ).fetchone()
    if row is None:
        raise KeyError(openalex_id)
    abstract = "" if row["abstract_missing"] else (row["abstract"] or "")
    return {
        "id": openalex_id,
        "abstract": abstract,
        "abstract_missing": bool(row["abstract_missing"]),
        "summary": row["summary"] or "",
        "file_url": row["file_url"] or "",
    }


def set_triage(connection: sqlite3.Connection, openalex_id: str, status: str) -> None:
    """Store your own mark on a paper. An empty status clears it."""
    status = (status or "").strip()
    if status and status not in TRIAGE_STATUSES:
        raise ValueError(f"Unknown triage status: {status}")
    _require_paper(connection, openalex_id)
    with connection:
        if status:
            connection.execute(
                """
                INSERT INTO triage (openalex_id, status, updated_at) VALUES (?, ?, ?)
                ON CONFLICT (openalex_id) DO UPDATE
                SET status = excluded.status, updated_at = excluded.updated_at
                """,
                (openalex_id, status, utc_now()),
            )
        else:
            connection.execute("DELETE FROM triage WHERE openalex_id = ?", (openalex_id,))
