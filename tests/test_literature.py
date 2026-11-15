import json
import tempfile
import unittest
from pathlib import Path

from literature.db import (
    connect,
    insert_work,
    migrate,
    needs_note,
    needs_screen,
    save_screen,
)
from literature.journals import parse_scimago_csv
from literature.openalex import normalize_work, reconstruct_abstract
from literature.page import render_papers_js, write_papers_js
from literature.run import next_watermark

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
        destination = Path(self.tmp.name) / "papers.js"
        text = write_papers_js(self.connection, destination)
        self.assertNotIn("UNIQUE_ABSTRACT_TEXT", text)
        self.assertNotIn('"abstract"', text)
        papers = json.loads(text.split("window.PAPERS = ", 1)[1].split(";\nwindow.LATEST_RUN_ID", 1)[0])
        self.assertEqual(papers[0]["score"], 4)
        self.assertEqual(papers[0]["published_on"], "2026-11-01")
        self.assertEqual(papers[0]["run_id"], 7)
        self.assertEqual(papers[0]["lecture"], "")
        self.assertNotIn("abstract", papers[0])


class PageAndWatermarkTests(unittest.TestCase):
    def test_render_includes_the_latest_run(self):
        text = render_papers_js(
            [
                {
                    "id": "W9",
                    "score": 9,
                    "published_on": "2026-11-02",
                    "run_id": 3,
                    "lecture": "mitochondria",
                }
            ],
            3,
        )
        self.assertIn('"lecture": "mitochondria"', text)
        self.assertTrue(text.endswith("window.LATEST_RUN_ID = 3;\n"))

    def test_watermark_stays_when_papers_remain(self):
        self.assertEqual(next_watermark("2026-11-01", 2, True, 0, "2026-11-15"), "2026-11-01")
        self.assertEqual(next_watermark("2026-11-01", 0, False, 0, "2026-11-15"), "2026-11-01")
        self.assertEqual(next_watermark("2026-11-01", 0, True, 1, "2026-11-15"), "2026-11-01")
        self.assertEqual(next_watermark("2026-11-01", 0, True, 0, "2026-11-15"), "2026-11-15")


if __name__ == "__main__":
    unittest.main()
