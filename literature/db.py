import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from literature.config import DB_PATH

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
    classified_at TEXT,
    run_id INTEGER
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    watermark_before TEXT,
    watermark_after TEXT,
    scanned INTEGER,
    kept INTEGER
);

CREATE INDEX IF NOT EXISTS papers_classified ON papers (classified_at);
CREATE INDEX IF NOT EXISTS papers_published ON papers (published_on);
CREATE INDEX IF NOT EXISTS papers_run ON papers (run_id);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: Path | None = None) -> sqlite3.Connection:
    database = path or DB_PATH
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    connection.commit()


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


def current_watermark(connection: sqlite3.Connection, lookback_days: int) -> str:
    row = connection.execute(
        """
        SELECT watermark_after FROM runs
        WHERE watermark_after IS NOT NULL AND finished_at IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return (date.today() - timedelta(days=lookback_days)).isoformat()
    return row["watermark_after"]


def start_run(connection: sqlite3.Connection, watermark_before: str) -> int:
    with connection:
        cursor = connection.execute(
            "INSERT INTO runs (started_at, watermark_before) VALUES (?, ?)",
            (utc_now(), watermark_before),
        )
        return int(cursor.lastrowid)


def finish_run(
    connection: sqlite3.Connection,
    run_id: int,
    watermark_after: str,
    scanned: int,
    kept: int,
) -> None:
    with connection:
        connection.execute(
            """
            UPDATE runs
            SET finished_at = ?, watermark_after = ?, scanned = ?, kept = ?
            WHERE id = ?
            """,
            (utc_now(), watermark_after, scanned, kept, run_id),
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
            ORDER BY published_on, openalex_id
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
            ORDER BY published_on, openalex_id
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
                model = ?, classified_at = ?, run_id = ?
            WHERE openalex_id = ? AND classified_at IS NULL
            """,
            (
                score,
                keep,
                result.get("kind") or "",
                result.get("sport") or "",
                result.get("why") or "",
                model,
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
) -> None:
    with connection:
        connection.execute(
            """
            UPDATE papers
            SET learn = ?, model = ?, classified_at = ?, run_id = ?,
                keep = 1
            WHERE openalex_id = ? AND classified_at IS NULL
            """,
            (
                result.get("learn") or "",
                model,
                utc_now(),
                run_id,
                openalex_id,
            ),
        )


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
    row = connection.execute(
        """
        SELECT id FROM runs
        WHERE finished_at IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def classified_papers(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT * FROM papers
            WHERE classified_at IS NOT NULL
            ORDER BY published_on DESC, openalex_id
            """
        ).fetchall()
    )
