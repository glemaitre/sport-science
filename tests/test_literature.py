import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from http import HTTPStatus

from literature.classify import screen_version
from literature.db import (
    connect,
    coverage,
    finish_run,
    insert_work,
    journal_progress,
    latest_run_id,
    migrate,
    needs_note,
    needs_screen,
    paper_record,
    replace_journals,
    reset_classification,
    save_note,
    save_progress,
    save_screen,
    set_file_url,
    set_summary,
    set_triage,
    stale_ids,
    start_run,
    SUMMARY_LIMIT,
)
from literature.journals import parse_scimago_csv
from literature.openalex import normalize_work, reconstruct_abstract
from literature.page import render_papers_js, write_papers_js
from literature.run import backward_window, forward_windows, month_before, parse_triage_file, within_last_month
from literature.server import (
    Jobs,
    backfill_body,
    classify_body,
    fetch_body,
    file_body,
    paper_body,
    summary_body,
    triage_body,
)

SEMICOLON_CSV = """\
Rank;Sourceid;Title;Type;Issn;SJR;SJR Best Quartile
1;1;British Journal of Sports Medicine;journal;03063674, 14730480;4,847;Q1
2;2;Journal of Applied Physiology;journal;87507587;1,106;Q2
3;3;A Book Series;book series;87654321;2,000;Q1
4;4;Medicine and Science in Sports and Exercise;journal;0195-9131;1,481;Q1
5;5;A Lower Journal;journal;11111111;0,200;Q3
"""

COMMA_CSV = """\
Rank,Title,Type,Issn,SJR,SJR Best Quartile
1,"Journal, of Physiology",journal,00223751,"1.476",Q1
"""


class ScimagoTests(unittest.TestCase):
    def test_q1_and_q2_journals_and_issns(self):
        journals = {journal.issn: journal for journal in parse_scimago_csv(SEMICOLON_CSV)}
        self.assertEqual(
            set(journals),
            {"0306-3674", "1473-0480", "8750-7587", "0195-9131"},
        )
        self.assertEqual(journals["0306-3674"].title, "British Journal of Sports Medicine")
        self.assertEqual(journals["0306-3674"].sjr, 4.847)
        self.assertEqual(journals["0195-9131"].sjr, 1.481)
        self.assertEqual(journals["0306-3674"].quartile, "Q1")
        self.assertEqual(journals["8750-7587"].quartile, "Q2")
        self.assertEqual(journals["8750-7587"].title, "Journal of Applied Physiology")

    def test_comma_delimiter_and_quoted_title(self):
        journals = parse_scimago_csv(COMMA_CSV)
        self.assertEqual(len(journals), 1)
        self.assertEqual(journals[0].title, "Journal, of Physiology")
        self.assertEqual(journals[0].issn, "0022-3751")

    def test_html_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_scimago_csv("<!DOCTYPE html><html><body>blocked</body></html>")


class OpenAlexTests(unittest.TestCase):
    def test_reconstruct_abstract(self):
        inverted = {"The": [0], "mitochondrion": [1], "makes": [2], "ATP": [3]}
        self.assertEqual(reconstruct_abstract(inverted), "The mitochondrion makes ATP")

    def test_missing_positions_are_skipped(self):
        self.assertEqual(reconstruct_abstract({"Lactate": [0], "fuel": [2]}), "Lactate fuel")
        self.assertEqual(reconstruct_abstract(None), "")

    def test_normalize_work(self):
        work = normalize_work(
            {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1000/example",
                "title": "  Fat use\non the bike ",
                "publication_date": "2026-11-14",
                "authorships": [
                    {"author": {"display_name": "Ada Rider"}},
                    {"author": {"display_name": "Bo Runner"}},
                ],
                "abstract_inverted_index": {"Fat": [0], "use": [1]},
                "primary_location": {
                    "source": {"display_name": "Sports Medicine", "issn": ["0112-1642"]}
                },
            },
            fetched_at="2026-11-15T00:00:00+00:00",
        )
        self.assertEqual(work["title"], "Fat use on the bike")
        self.assertEqual(work["authors"], "Ada Rider, Bo Runner")
        self.assertEqual(work["abstract"], "Fat use")
        self.assertEqual(work["abstract_missing"], 0)
        self.assertEqual(work["published_on"], "2026-11-14")

    def _fake_client(self, total):
        calls = []

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        def work(index):
            return {"id": f"https://openalex.org/W{index}", "title": f"Paper {index}"}

        class Client:
            def get(self, url, params, headers):
                calls.append(dict(params))
                if "cursor" in params:
                    start = 0 if params["cursor"] == "*" else int(params["cursor"])
                    end = min(start + 100, total)
                    nxt = str(end) if end < total else None
                    return Response(
                        {"results": [work(i) for i in range(start, end)], "meta": {"next_cursor": nxt}}
                    )
                start = (int(params["page"]) - 1) * 100
                end = min(start + 100, total)
                return Response({"results": [work(i) for i in range(start, end)], "meta": {"count": total}})

        return Client(), calls

    def test_numbered_pages_without_a_key_and_cursor_with_one(self):
        import literature.openalex as openalex

        original = openalex.time.sleep
        openalex.time.sleep = lambda seconds: None
        self.addCleanup(setattr, openalex.time, "sleep", original)

        client, calls = self._fake_client(250)
        works, complete = openalex.fetch_works(["0306-3674"], "2026-10-01", "", client, 1000, "2026-10-31")
        self.assertEqual((len(works), complete), (250, True))
        self.assertEqual([call["page"] for call in calls], ["1", "2", "3"])
        self.assertNotIn("cursor", calls[0])
        self.assertIn("to_publication_date:2026-10-31", calls[0]["filter"])

        client, calls = self._fake_client(250)
        works, complete = openalex.fetch_works(["0306-3674"], "2026-10-01", "", client, 1000, api_key="k")
        self.assertEqual((len(works), complete), (250, True))
        self.assertEqual([call["cursor"] for call in calls], ["*", "100", "200"])
        self.assertEqual(calls[0]["api_key"], "k")
        self.assertNotIn("to_publication_date", calls[0]["filter"])

        client, _ = self._fake_client(250)
        works, complete = openalex.fetch_works(["0306-3674"], "2026-10-01", "", client, 120)
        self.assertEqual((len(works), complete), (120, False))


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.connection = connect(Path(self.tmp.name) / "literature.sqlite")
        self.addCleanup(self.connection.close)
        migrate(self.connection)

    def _work(self, openalex_id, title, abstract="Secret abstract sentence."):
        return {
            "openalex_id": openalex_id,
            "doi": f"https://doi.org/10.1000/{openalex_id}",
            "title": title,
            "abstract": abstract,
            "abstract_missing": 0,
            "journal_issn": "0306-3674",
            "journal_title": "Sports Medicine",
            "published_on": "2026-11-01",
            "authors": "Ada Rider",
            "fetched_at": "2026-11-15T00:00:00+00:00",
        }

    def test_classified_papers_are_not_screened_again(self):
        self.assertTrue(insert_work(self.connection, self._work("W1", "Already read")))
        self.assertFalse(insert_work(self.connection, self._work("W1", "Already read")))
        insert_work(self.connection, self._work("W2", "Still waiting"))
        save_screen(
            self.connection,
            "W1",
            {"score": 3, "kind": "", "sport": "", "why": "Surgery technique."},
            6,
            "test-model",
            1,
        )
        self.connection.commit()
        waiting = [row["openalex_id"] for row in needs_screen(self.connection, 10)]
        self.assertEqual(waiting, ["W2"])

    def test_latest_run_skips_runs_that_kept_nothing(self):
        self.assertIsNone(latest_run_id(self.connection))
        kept = start_run(self.connection)
        finish_run(self.connection, kept, 200, 5)
        empty = start_run(self.connection)
        finish_run(self.connection, empty, 2, 0)
        start_run(self.connection)
        self.assertEqual(latest_run_id(self.connection), kept)

    def test_a_kept_score_waits_for_the_learning_note(self):
        insert_work(self.connection, self._work("W3", "Cristae and VO2max"))
        save_screen(
            self.connection,
            "W3",
            {"score": 8, "kind": "cycling", "sport": "cycling", "why": "Cyclists."},
            6,
            "test-model",
            1,
        )
        self.connection.commit()
        self.assertEqual(needs_screen(self.connection, 10), [])
        notes = [row["openalex_id"] for row in needs_note(self.connection, 6, 10)]
        self.assertEqual(notes, ["W3"])

    def _papers_js(self):
        destination = Path(self.tmp.name) / "papers.js"
        text = write_papers_js(self.connection, destination)
        body = text.split("window.PAPERS = ", 1)[1].split(";\nwindow.LATEST_RUN_ID", 1)[0]
        return text, {paper["id"]: paper for paper in json.loads(body)}

    def _keep(self, openalex_id, score=8, version="old"):
        save_screen(
            self.connection,
            openalex_id,
            {"score": score, "kind": "cycling", "sport": "cycling", "why": "Cyclists."},
            6,
            "test-model",
            1,
            version,
        )
        if score >= 6:
            save_note(self.connection, openalex_id, {"learn": "Something."}, "test-model", 1, "n")

    def test_page_payload_keeps_the_score_and_leaves_out_the_abstract(self):
        insert_work(
            self.connection,
            self._work("W4", "Glycogen after a long ride", abstract="UNIQUE_ABSTRACT_TEXT"),
        )
        save_screen(
            self.connection,
            "W4",
            {"score": 4, "kind": "endurance", "sport": "running", "why": "Runners."},
            6,
            "test-model",
            7,
        )
        self.connection.commit()
        text, papers = self._papers_js()
        self.assertNotIn("UNIQUE_ABSTRACT_TEXT", text)
        self.assertNotIn('"abstract"', text)
        self.assertEqual(papers["W4"]["summary"], "")
        self.assertEqual(papers["W4"]["score"], 4)
        self.assertEqual(papers["W4"]["published_on"], "2026-11-01")
        self.assertEqual(papers["W4"]["run_id"], 7)
        self.assertNotIn("lecture", papers["W4"])

    def test_payload_status_for_each_stage(self):
        insert_work(self.connection, self._work("W5", "Waiting"))
        insert_work(self.connection, self._work("W6", "Dropped"))
        insert_work(self.connection, self._work("W7", "Kept"))
        insert_work(self.connection, self._work("W8", "Kept, note missing"))
        self._keep("W6", score=3)
        self._keep("W7", score=9)
        save_screen(
            self.connection,
            "W8",
            {"score": 7, "kind": "endurance", "sport": "rowing", "why": "Rowers."},
            6,
            "test-model",
            1,
        )
        _, papers = self._papers_js()
        self.assertEqual(papers["W5"]["status"], "unclassified")
        self.assertIsNone(papers["W5"]["score"])
        self.assertEqual(papers["W6"]["status"], "discarded")
        self.assertEqual(papers["W7"]["status"], "of-interest")
        self.assertEqual(papers["W8"]["status"], "unclassified")
        self.assertEqual(papers["W8"]["why"], "")

    def test_queue_is_newest_first(self):
        old = self._work("W10", "Old")
        new = {**self._work("W11", "New"), "published_on": "2026-11-12"}
        insert_work(self.connection, old)
        insert_work(self.connection, new)
        waiting = [row["openalex_id"] for row in needs_screen(self.connection, 10)]
        self.assertEqual(waiting, ["W11", "W10"])

    def test_stale_screen_is_found_for_kept_papers_only(self):
        current = screen_version("test-model", brief="brief")
        for openalex_id in ("W20", "W21", "W22"):
            insert_work(self.connection, self._work(openalex_id, openalex_id))
        self._keep("W20", score=8, version="old")
        self._keep("W21", score=8, version=current)
        self._keep("W22", score=2, version="old")
        self.assertEqual(stale_ids(self.connection, current), ["W20"])
        self.assertEqual(sorted(stale_ids(self.connection, current, include_dropped=True)), ["W20", "W22"])
        self.assertNotEqual(current, screen_version("other-model", brief="brief"))
        self.assertNotEqual(current, screen_version("test-model", brief="another brief"))

    def test_triage_survives_a_rescreen(self):
        insert_work(self.connection, self._work("W30", "Kept"))
        self._keep("W30", score=8)
        set_triage(self.connection, "W30", "useful")
        reset_classification(self.connection, ["W30"])
        _, papers = self._papers_js()
        self.assertEqual(papers["W30"]["status"], "unclassified")
        self.assertEqual(papers["W30"]["triage"], "useful")
        self.assertEqual([row["openalex_id"] for row in needs_screen(self.connection, 10)], ["W30"])

    def test_triage_rejects_unknown_status_and_paper(self):
        insert_work(self.connection, self._work("W31", "Kept"))
        with self.assertRaises(ValueError):
            set_triage(self.connection, "W31", "maybe")
        with self.assertRaises(KeyError):
            set_triage(self.connection, "W404", "read")
        set_triage(self.connection, "W31", "read")
        set_triage(self.connection, "W31", "")
        _, papers = self._papers_js()
        self.assertEqual(papers["W31"]["triage"], "")

    def test_summary_round_trip_and_survives_a_rescreen(self):
        insert_work(self.connection, self._work("W32", "Noted", abstract="Hidden abstract."))
        self._keep("W32", score=8)
        self.assertEqual(set_summary(self.connection, "W32", "  Heat **hurts** fuel use.  "), "Heat **hurts** fuel use.")
        self.assertEqual(paper_record(self.connection, "W32")["abstract"], "Hidden abstract.")
        self.assertEqual(paper_record(self.connection, "W32")["summary"], "Heat **hurts** fuel use.")
        reset_classification(self.connection, ["W32"])
        _, papers = self._papers_js()
        self.assertEqual(papers["W32"]["status"], "unclassified")
        self.assertEqual(papers["W32"]["summary"], "Heat **hurts** fuel use.")
        self.assertNotIn("Hidden abstract.", papers["W32"].get("abstract", ""))
        self.assertEqual(
            set_file_url(self.connection, "W32", "  https://files.example/paper.pdf  "),
            "https://files.example/paper.pdf",
        )
        set_summary(self.connection, "W32", "   ")
        record = paper_record(self.connection, "W32")
        self.assertEqual(record["summary"], "")
        self.assertEqual(record["file_url"], "https://files.example/paper.pdf")
        _, papers = self._papers_js()
        self.assertEqual(papers["W32"]["file_url"], "https://files.example/paper.pdf")
        set_file_url(self.connection, "W32", "")
        self.assertEqual(paper_record(self.connection, "W32")["file_url"], "")
        with self.assertRaises(ValueError):
            set_file_url(self.connection, "W32", "ftp://files.example/paper.pdf")
        with self.assertRaises(ValueError):
            set_summary(self.connection, "W32", "x" * (SUMMARY_LIMIT + 1))
        with self.assertRaises(KeyError):
            set_summary(self.connection, "W404", "note")

    def test_file_url_column_is_added_to_an_existing_summary_table(self):
        self.connection.execute("DROP TABLE summary")
        self.connection.execute(
            """
            CREATE TABLE summary (
                openalex_id TEXT PRIMARY KEY,
                markdown TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()
        migrate(self.connection)
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(summary)")}
        self.assertIn("file_url", columns)


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.connection = connect(Path(self.tmp.name) / "literature.sqlite")
        self.addCleanup(self.connection.close)
        migrate(self.connection)
        replace_journals(
            self.connection,
            [
                {"issn": "0000-0001", "title": "A", "sjr": 2.0, "quartile": "Q1"},
                {"issn": "0000-0002", "title": "B", "sjr": 1.0, "quartile": "Q2"},
            ],
        )

    def test_forward_windows_use_the_overlap(self):
        progress = {
            "0000-0001": ("2026-11-01", "2026-11-15"),
            "0000-0002": ("2026-11-01", "2026-11-15"),
            "0000-0003": (None, None),
        }
        self.assertEqual(
            forward_windows(progress, 14),
            [("2026-11-01", ["0000-0001", "0000-0002"])],
        )

    def test_backward_windows_go_one_month_at_a_time(self):
        progress = {"0000-0001": ("2026-11-08", "2026-11-15"), "0000-0002": (None, None)}
        self.assertEqual(
            backward_window(progress, "2026-01-01", "2026-11-15"),
            ("2026-11-01", "2026-11-15", ["0000-0002"]),
        )
        progress["0000-0002"] = ("2026-11-01", "2026-11-15")
        self.assertEqual(
            backward_window(progress, "2026-01-01", "2026-11-15"),
            ("2026-11-01", "2026-11-07", ["0000-0001"]),
        )
        progress["0000-0001"] = ("2026-11-01", "2026-11-15")
        self.assertEqual(
            backward_window(progress, "2026-01-01", "2026-11-15"),
            ("2026-10-01", "2026-10-31", ["0000-0001", "0000-0002"]),
        )
        done = {"0000-0001": ("2026-01-01", "2026-11-15")}
        self.assertIsNone(backward_window(done, "2026-01-01", "2026-11-15"))
        self.assertEqual(
            backward_window(done, "2025-12-15", "2026-11-15"),
            ("2025-12-15", "2025-12-31", ["0000-0001"]),
        )

    def test_progress_only_widens_and_sets_coverage(self):
        self.assertEqual(journal_progress(self.connection)["0000-0002"], (None, None))
        self.assertEqual(coverage(self.connection), (None, None))
        save_progress(self.connection, ["0000-0001", "0000-0002"], "2026-10-01", "2026-11-15")
        save_progress(self.connection, ["0000-0001"], "2026-10-20", "2026-11-10")
        self.assertEqual(journal_progress(self.connection)["0000-0001"], ("2026-10-01", "2026-11-15"))
        save_progress(self.connection, ["0000-0002"], "2026-09-01")
        self.assertEqual(coverage(self.connection), ("2026-10-01", "2026-11-15"))

    def test_old_runs_seed_the_progress(self):
        database = Path(self.tmp.name) / "old.sqlite"
        old = connect(database)
        self.addCleanup(old.close)
        old.executescript(
            """
            CREATE TABLE journals (issn TEXT PRIMARY KEY, title TEXT NOT NULL, sjr REAL,
                quartile TEXT NOT NULL, refreshed_at TEXT NOT NULL);
            CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
                finished_at TEXT, watermark_before TEXT, watermark_after TEXT,
                scanned INTEGER, kept INTEGER);
            INSERT INTO journals VALUES ('0000-0001', 'A', 1.0, 'Q1', 'now');
            INSERT INTO runs (started_at, finished_at, watermark_before, watermark_after, scanned, kept)
                VALUES ('2026-11-15T15:00:00+00:00', '2026-11-15T15:50:00+00:00', '2026-11-08', '2026-11-08', 149, 14);
            """
        )
        migrate(old)
        self.assertEqual(journal_progress(old)["0000-0001"], ("2026-11-08", "2026-11-15"))


class TriageFileAndServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.connection = connect(Path(self.tmp.name) / "literature.sqlite")
        self.addCleanup(self.connection.close)
        migrate(self.connection)
        insert_work(
            self.connection,
            {
                "openalex_id": "W1",
                "doi": "",
                "title": "A ride",
                "abstract": "",
                "abstract_missing": 1,
                "journal_issn": "",
                "journal_title": "",
                "published_on": "2026-11-01",
                "authors": "",
                "fetched_at": "2026-11-15T00:00:00+00:00",
            },
        )

    def test_triage_file_formats(self):
        self.assertEqual(parse_triage_file('{"triage": {"W1": "read"}}'), {"W1": "read"})
        self.assertEqual(parse_triage_file('[{"id": "W1", "status": "useful"}]'), {"W1": "useful"})
        with self.assertRaises(ValueError):
            parse_triage_file('"read"')

    def test_triage_endpoint(self):
        import literature.server as server

        written = []
        original = server.write_papers_js
        server.write_papers_js = lambda connection: written.append(True)
        self.addCleanup(setattr, server, "write_papers_js", original)
        status, body = triage_body(self.connection, {"id": "W1", "status": "to-read"})
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(body, {"id": "W1", "status": "to-read"})
        self.assertEqual(written, [True])
        self.assertEqual(triage_body(self.connection, {"id": "W1", "status": "maybe"})[0], HTTPStatus.BAD_REQUEST)
        self.assertEqual(triage_body(self.connection, {"id": "W9", "status": "read"})[0], HTTPStatus.NOT_FOUND)

    def test_summary_endpoint(self):
        import literature.server as server

        written = []
        original = server.write_papers_js
        server.write_papers_js = lambda connection: written.append(True)
        self.addCleanup(setattr, server, "write_papers_js", original)
        status, body = summary_body(self.connection, {"id": "W1", "markdown": "A note"})
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(body["summary"], "A note")
        self.assertEqual(written, [True])
        found, record = paper_body(self.connection, "W1")
        self.assertEqual(found, HTTPStatus.OK)
        self.assertEqual(record["summary"], "A note")
        self.assertNotIn("abstract_text", record)
        self.assertEqual(summary_body(self.connection, {"id": "W1"})[0], HTTPStatus.BAD_REQUEST)
        self.assertEqual(summary_body(self.connection, {"id": "W9", "markdown": "no"})[0], HTTPStatus.NOT_FOUND)
        self.assertEqual(
            summary_body(self.connection, {"id": "W1", "markdown": "y" * (SUMMARY_LIMIT + 1)})[0],
            HTTPStatus.BAD_REQUEST,
        )
        self.assertEqual(paper_body(self.connection, "")[0], HTTPStatus.BAD_REQUEST)
        self.assertEqual(paper_body(self.connection, "W9")[0], HTTPStatus.NOT_FOUND)

    def test_file_url_endpoint(self):
        import literature.server as server

        written = []
        original = server.write_papers_js
        server.write_papers_js = lambda connection: written.append(True)
        self.addCleanup(setattr, server, "write_papers_js", original)
        status, body = file_body(self.connection, {"id": "W1", "url": "https://files.example/W1.pdf"})
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(body["url"], "https://files.example/W1.pdf")
        self.assertEqual(written, [True])
        found, record = paper_body(self.connection, "W1")
        self.assertEqual(found, HTTPStatus.OK)
        self.assertEqual(record["file_url"], "https://files.example/W1.pdf")
        self.assertEqual(file_body(self.connection, {"id": "W1", "url": "not a url"})[0], HTTPStatus.BAD_REQUEST)
        self.assertEqual(file_body(self.connection, {"id": "W1"})[0], HTTPStatus.BAD_REQUEST)
        self.assertEqual(file_body(self.connection, {"id": "W9", "url": "https://files.example/no"})[0], HTTPStatus.NOT_FOUND)
        cleared, empty = file_body(self.connection, {"id": "W1", "url": "  "})
        self.assertEqual(cleared, HTTPStatus.OK)
        self.assertEqual(empty["url"], "")

    def test_backfill_endpoint_validates_and_runs_one_job(self):
        jobs = Jobs(command=lambda args: ["python", "-c", "print('done')"])
        self.assertEqual(backfill_body(jobs, {"papers": 0})[0], HTTPStatus.BAD_REQUEST)
        self.assertEqual(backfill_body(jobs, {"papers": "many"})[0], HTTPStatus.BAD_REQUEST)
        self.assertEqual(backfill_body(jobs, {"papers": 5, "since": "soon"})[0], HTTPStatus.BAD_REQUEST)
        status, job = backfill_body(jobs, {"papers": 5, "since": "2025-06-01"})
        self.assertEqual(status, HTTPStatus.ACCEPTED)
        self.assertEqual(job["since"], "2025-06-01")
        self.assertEqual(job["kind"], "backfill")

    def test_last_month_bound(self):
        today = date(2026, 3, 31)
        self.assertEqual(month_before(today), date(2026, 2, 28))
        self.assertEqual(month_before(date(2024, 3, 31)), date(2024, 2, 29))
        self.assertEqual(month_before(date(2026, 1, 31)), date(2025, 12, 31))
        self.assertEqual(month_before(date(2026, 5, 31)), date(2026, 4, 30))
        self.assertEqual(within_last_month("2026-03-01", today), "2026-03-01")
        self.assertEqual(within_last_month("2026-02-28", today), "2026-02-28")
        with self.assertRaises(ValueError):
            within_last_month("2026-02-27", today)
        with self.assertRaises(ValueError):
            within_last_month("2026-04-01", today)
        with self.assertRaises(ValueError):
            within_last_month("soon", today)

    def test_fetch_endpoint_rejects_dates_outside_the_last_month(self):
        jobs = Jobs(command=lambda args: ["python", "-c", "print('done')"])
        today = date(2026, 11, 16)
        self.assertEqual(fetch_body(jobs, {}, today)[0], HTTPStatus.BAD_REQUEST)
        self.assertEqual(fetch_body(jobs, {"since": "soon"}, today)[0], HTTPStatus.BAD_REQUEST)
        self.assertEqual(fetch_body(jobs, {"since": "2026-10-15"}, today)[0], HTTPStatus.BAD_REQUEST)
        status, job = fetch_body(jobs, {"since": "2026-10-16"}, today)
        self.assertEqual(status, HTTPStatus.ACCEPTED)
        self.assertEqual(job["kind"], "fetch")
        self.assertEqual(job["since"], "2026-10-16")

    def test_classify_is_refused_while_a_job_is_running(self):
        jobs = Jobs(command=lambda args: ["python", "-c", "import time; time.sleep(30)"])
        today = date(2026, 11, 16)
        status, job = fetch_body(jobs, {"since": "2026-11-16"}, today)
        self.addCleanup(lambda: jobs.process.kill() if jobs.process and jobs.process.poll() is None else None)
        self.assertEqual(status, HTTPStatus.ACCEPTED)
        self.assertEqual(job["state"], "running")
        refused, body = classify_body(jobs)
        self.assertEqual(refused, HTTPStatus.CONFLICT)
        self.assertIn("already running", body["error"])


class PageRenderTests(unittest.TestCase):
    def test_render_includes_the_latest_run_and_library(self):
        text = render_papers_js(
            [{"id": "W9", "score": 9, "published_on": "2026-11-02", "run_id": 3}],
            3,
            {"start_date": "2026-01-01"},
        )
        self.assertIn('"id":"W9"', text)
        self.assertIn("window.LATEST_RUN_ID = 3;\n", text)
        self.assertTrue(text.endswith('window.LIBRARY = {"start_date":"2026-01-01"};\n'))
        self.assertEqual(render_papers_js([], None).split("\n", 1)[0], "window.PAPERS = [];")


if __name__ == "__main__":
    unittest.main()
