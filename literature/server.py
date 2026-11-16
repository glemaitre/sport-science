"""Serve the literature page locally, with triage writes and backfill runs.

Bound to 127.0.0.1 only. The published page has no API and stays read-only.
"""

import json
import os
import subprocess
import sys
import threading
from datetime import date
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from literature.cli import MAX_BACKFILL
from literature.config import ROOT, WEB_DIR, load_config
from literature.db import (
    TRIAGE_STATUSES,
    SUMMARY_LIMIT,
    connect,
    migrate,
    paper_record,
    set_file_url,
    set_summary,
    set_triage,
)
from literature.page import build_papers_js, library_payload, write_papers_js
from literature.run import within_last_month

HOST = "127.0.0.1"
LOG_LINES = 200


class Jobs:
    """At most one backfill at a time, run as the same CLI the workflow uses."""

    def __init__(self, command=None):
        self.lock = threading.Lock()
        self.current: dict | None = None
        self.next_id = 1
        self.process: subprocess.Popen | None = None
        self.command = command or (lambda args: [sys.executable, "-m", "literature", *args])

    def snapshot(self) -> dict | None:
        with self.lock:
            if self.current is None:
                return None
            return {key: (list(value) if key == "log" else value) for key, value in self.current.items()}

    def start(self, args: list[str], fields: dict) -> dict:
        with self.lock:
            if self.current is not None and self.current["state"] == "running":
                raise RuntimeError("A job is already running.")
            job = {
                "id": self.next_id,
                "state": "running",
                "log": [],
                "returncode": None,
                **fields,
            }
            self.next_id += 1
            self.current = job
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        self.process = subprocess.Popen(
            self.command(args),
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        threading.Thread(target=self._follow, args=(job, self.process), daemon=True).start()
        return {key: value for key, value in job.items() if key != "log"}

    def _follow(self, job: dict, process: subprocess.Popen) -> None:
        assert process.stdout is not None
        code = 1
        try:
            for line in process.stdout:
                with self.lock:
                    job["log"].append(line.rstrip())
                    del job["log"][:-LOG_LINES]
            code = process.wait()
        finally:
            process.stdout.close()
        with self.lock:
            job["returncode"] = code
            job["state"] = "done" if code == 0 else "failed"


def status_body(connection, jobs: Jobs) -> dict:
    return {
        "mode": "local",
        "library": library_payload(connection, load_config().start_date),
        "job": jobs.snapshot(),
        "max_papers": MAX_BACKFILL,
    }


def triage_body(connection, payload: dict) -> tuple[HTTPStatus, dict]:
    openalex_id = str(payload.get("id") or "").strip()
    status = str(payload.get("status") or "").strip()
    if not openalex_id:
        return HTTPStatus.BAD_REQUEST, {"error": "id is required."}
    if status and status not in TRIAGE_STATUSES:
        return HTTPStatus.BAD_REQUEST, {"error": f"status is one of {', '.join(TRIAGE_STATUSES)}."}
    try:
        set_triage(connection, openalex_id, status)
    except KeyError:
        return HTTPStatus.NOT_FOUND, {"error": "No paper with that id."}
    write_papers_js(connection)
    return HTTPStatus.OK, {"id": openalex_id, "status": status}


def paper_body(connection, paper_id: str) -> tuple[HTTPStatus, dict]:
    paper_id = paper_id.strip()
    if not paper_id:
        return HTTPStatus.BAD_REQUEST, {"error": "id is required."}
    try:
        return HTTPStatus.OK, paper_record(connection, paper_id)
    except KeyError:
        return HTTPStatus.NOT_FOUND, {"error": "No paper with that id."}


def summary_body(connection, payload: dict) -> tuple[HTTPStatus, dict]:
    openalex_id = str(payload.get("id") or "").strip()
    if not openalex_id:
        return HTTPStatus.BAD_REQUEST, {"error": "id is required."}
    markdown = payload.get("markdown")
    if not isinstance(markdown, str):
        return HTTPStatus.BAD_REQUEST, {"error": "markdown is text."}
    try:
        stored = set_summary(connection, openalex_id, markdown)
    except ValueError:
        return HTTPStatus.BAD_REQUEST, {"error": f"A summary is at most {SUMMARY_LIMIT} characters."}
    except KeyError:
        return HTTPStatus.NOT_FOUND, {"error": "No paper with that id."}
    write_papers_js(connection)
    return HTTPStatus.OK, {"id": openalex_id, "summary": stored}


def file_body(connection, payload: dict) -> tuple[HTTPStatus, dict]:
    openalex_id = str(payload.get("id") or "").strip()
    if not openalex_id:
        return HTTPStatus.BAD_REQUEST, {"error": "id is required."}
    url = payload.get("url")
    if not isinstance(url, str):
        return HTTPStatus.BAD_REQUEST, {"error": "url is text."}
    try:
        stored = set_file_url(connection, openalex_id, url)
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
    except KeyError:
        return HTTPStatus.NOT_FOUND, {"error": "No paper with that id."}
    write_papers_js(connection)
    return HTTPStatus.OK, {"id": openalex_id, "url": stored}


def backfill_body(jobs: Jobs, payload: dict) -> tuple[HTTPStatus, dict]:
    try:
        papers = int(payload.get("papers", 200))
    except (TypeError, ValueError):
        return HTTPStatus.BAD_REQUEST, {"error": "papers is a whole number."}
    if papers < 1 or papers > MAX_BACKFILL:
        return HTTPStatus.BAD_REQUEST, {"error": f"papers is between 1 and {MAX_BACKFILL}."}
    since = str(payload.get("since") or "").strip() or None
    if since:
        try:
            since = date.fromisoformat(since).isoformat()
        except ValueError:
            return HTTPStatus.BAD_REQUEST, {"error": "since is a date like 2026-01-01."}
    try:
        args = ["backfill", "--papers", str(papers)]
        if since:
            args += ["--since", since]
        job = jobs.start(args, {"kind": "backfill", "papers": papers, "since": since or ""})
    except RuntimeError as exc:
        return HTTPStatus.CONFLICT, {"error": str(exc)}
    return HTTPStatus.ACCEPTED, job


def fetch_body(jobs: Jobs, payload: dict, today: date | None = None) -> tuple[HTTPStatus, dict]:
    since = str(payload.get("since") or "").strip()
    if not since:
        return HTTPStatus.BAD_REQUEST, {"error": "since is required."}
    try:
        since = within_last_month(since, today or date.today())
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
    try:
        job = jobs.start(["fetch", "--since", since], {"kind": "fetch", "since": since})
    except RuntimeError as exc:
        return HTTPStatus.CONFLICT, {"error": str(exc)}
    return HTTPStatus.ACCEPTED, job


def classify_body(jobs: Jobs) -> tuple[HTTPStatus, dict]:
    try:
        job = jobs.start(["classify"], {"kind": "classify", "since": ""})
    except RuntimeError as exc:
        return HTTPStatus.CONFLICT, {"error": str(exc)}
    return HTTPStatus.ACCEPTED, job


class Handler(SimpleHTTPRequestHandler):
    jobs: Jobs
    port: int

    def _allowed_host(self) -> bool:
        host = self.headers.get("Host", "")
        return host in {f"{HOST}:{self.port}", f"localhost:{self.port}"}

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        parts = urlsplit(origin)
        return parts.scheme == "http" and parts.netloc in {f"{HOST}:{self.port}", f"localhost:{self.port}"}

    def _send(self, status: HTTPStatus, body: str, content_type: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _json(self, status: HTTPStatus, body: dict | None) -> None:
        self._send(status, json.dumps(body), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if not self._allowed_host():
            self._json(HTTPStatus.FORBIDDEN, {"error": "Unexpected host."})
            return
        path = urlsplit(self.path).path
        if path == "/papers.js":
            connection = connect()
            try:
                migrate(connection)
                self._send(HTTPStatus.OK, build_papers_js(connection), "text/javascript; charset=utf-8")
            finally:
                connection.close()
            return
        if path == "/api/status":
            connection = connect()
            try:
                migrate(connection)
                self._json(HTTPStatus.OK, status_body(connection, self.jobs))
            finally:
                connection.close()
            return
        if path == "/api/paper":
            paper_id = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
            connection = connect()
            try:
                migrate(connection)
                status, body = paper_body(connection, paper_id)
            finally:
                connection.close()
            self._json(status, body)
            return
        if path.startswith("/api/jobs/"):
            job = self.jobs.snapshot()
            if job is None or path != f"/api/jobs/{job['id']}":
                self._json(HTTPStatus.NOT_FOUND, {"error": "No such job."})
            else:
                self._json(HTTPStatus.OK, job)
            return
        if path.startswith("/api/"):
            self._json(HTTPStatus.NOT_FOUND, {"error": "Unknown endpoint."})
            return
        super().do_GET()

    def do_POST(self) -> None:
        if not self._allowed_host() or not self._same_origin():
            self._json(HTTPStatus.FORBIDDEN, {"error": "Only this page may write."})
            return
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Send JSON."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 200_000:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "The body is too large."})
                return
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "The body is not JSON."})
            return
        if not isinstance(payload, dict):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "The body is a JSON object."})
            return
        path = urlsplit(self.path).path
        if path == "/api/triage":
            connection = connect()
            try:
                migrate(connection)
                status, body = triage_body(connection, payload)
            finally:
                connection.close()
            self._json(status, body)
            return
        if path == "/api/summary":
            connection = connect()
            try:
                migrate(connection)
                status, body = summary_body(connection, payload)
            finally:
                connection.close()
            self._json(status, body)
            return
        if path == "/api/file":
            connection = connect()
            try:
                migrate(connection)
                status, body = file_body(connection, payload)
            finally:
                connection.close()
            self._json(status, body)
            return
        if path == "/api/backfill":
            status, body = backfill_body(self.jobs, payload)
            self._json(status, body)
            return
        if path == "/api/fetch":
            status, body = fetch_body(self.jobs, payload)
            self._json(status, body)
            return
        if path == "/api/classify":
            status, body = classify_body(self.jobs)
            self._json(status, body)
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "Unknown endpoint."})

    def log_message(self, format: str, *args) -> None:
        path = urlsplit(self.path).path
        if path != "/api/status" and not path.startswith("/api/jobs/"):
            super().log_message(format, *args)


def serve(port: int = 8766) -> int:
    handler = partial(type("LiteratureHandler", (Handler,), {"jobs": Jobs(), "port": port}), directory=str(WEB_DIR))
    server = ThreadingHTTPServer((HOST, port), handler)
    print(f"Literature app at http://{HOST}:{port}/  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
