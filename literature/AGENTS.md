# Literature job

A daily alert for a data scientist at a professional cycling team. It is not a lecture. Do not add it to `nav`, and do not edit the lecture notes from here.

What counts as a useful paper is [interest_brief.md](interest_brief.md). The first pass is `SCREEN_SYSTEM` in `classify.py`. It does not read the brief. If the interest changes, change both, or the screen will drop papers the brief would have kept.

## What to keep

Q1 and Q2 of SCImago Sports Science, area `3600`, category `3699`. The quartile is the Sports Science one in that download. Do not go back to Q1 only. Physiology from a similar continuous endurance sport counts when the mechanism would transfer to the bike. Biomechanics and aerodynamics count when the task is cycling, or when the method applies directly to the bike.

The score bands are written in both the screen prompt and the brief. 8–10 is a direct cycling finding. 6–7 is an endurance or mechanism finding that transfers to the bike. 5 or below is general exercise science with no endurance link: strength training, body composition, team sports, sport psychology, coaching, and general health. The first run, before these bands, kept ice hockey, rugby, and resistance-training papers at 6–7. Do not loosen the bands back.

`Experimental Physiology` is not in this category. Adding it means a separate source, not a looser quartile.

## Dates and caching

There is no single watermark any more. `journal_progress` stores, per ISSN, the publication dates already read from OpenAlex.

- `start_date` in `config.toml` (2026-01-01) is how far back the library reaches.
- Each run reads forward from each journal's `fetched_through` minus `overlap_days` (14), with no upper date, so late-indexed papers and issues dated ahead of today are caught. Then it reads backward one calendar month at a time toward `start_date`, and records each completed month. A run stopped by `fetch_cap` keeps the months it finished.
- A journal added later starts with no progress and gets the full range.
- Fetching and classifying are separate. Unclassified papers wait in the database. The queue is newest publication first, so daily arrivals go before the backlog. `max_papers` (200) is the daily model budget.
- Each screen and note stores a version: the first 12 hex digits of a sha256 over the prompt, the brief, and the model. A paper is not sent again for the same version. After changing the prompt, the brief, or the model, run `pixi run python -m literature rescreen`. It queues the kept papers with an older screen. `--all` queues the dropped ones too, which costs a full re-screen.

## How a run works

- `pixi run literature-journals` refreshes `journals`. `pixi run literature` fetches and classifies up to 200. `pixi run literature-backfill --papers N [--since DATE]` classifies N, and `--since` first reads back to a date before `start_date`. The local Fetch panel does not use that budget. `pixi run python -m literature fetch --since DATE` reads only from that date through today. The date has to fall in the last month. It does not classify, and it does not move `journal_progress`. `pixi run python -m literature classify` screens every paper still waiting, and does nothing when the queue is empty.
- Do not scrape journal sites or PDFs. Rankings come from SCImago. The download that returns the CSV is `journalrank.php` with `out=xls`. `format=csv` returns HTML. A script often gets a Cloudflare check. On that failure, keep the stored rows and use `pixi run python -m literature journals --csv PATH`.
- Papers come from the OpenAlex works API. Rebuild the abstract from the inverted index. A missing abstract is classified from the title.
- SQLite is `literature/data/literature.sqlite`, in DELETE journal mode. One file. Do not commit a `-wal` or `-shm`. The abstract stays in the database and stays out of `papers.js`.
- Keep is `score >= 6` in Python. Do not trust the model's keep flag. A kept paper is not classified until its note is written. A failed call leaves the paper in the queue.
- `OPENROUTER_MODEL` overrides the model. `OPENROUTER_API_KEY` is required to classify. `OPENALEX_MAILTO` is optional and only puts the calls in the polite pool.

## Statuses and triage

The job status is computed, not stored: `unclassified` (no screen yet, or kept without a note), `discarded` (score below 6), `of-interest` (kept with a note). `papers.js` has every fetched paper. Unclassified rows carry no score or reason.

Your triage is the `triage` table: `to-read`, `read`, `useful`, `not-relevant`. It is separate from `papers`, so a re-screen does not wipe it. `useful` on a discarded paper puts it back under "Of interest" on the page.

Your summary is the `summary` table: markdown that belongs to one paper. It is yours, not the model's learning note. A re-screen must not wipe it. The same row holds `file_url`, an http or https link to where you keep the paper. Clearing one leaves the other. The text and the link are in `papers.js`, so a later commit publishes them. The abstract stays in the database and stays off that file. Write both from the paper page in the local app. The published paper page only shows them.

Write triage from the local app, `pixi run literature-app`, at `http://127.0.0.1:8766/`. It serves `literature/web`, builds `papers.js` from the database on each request, and has `GET /api/status`, `GET /api/paper`, `POST /api/triage`, `POST /api/summary`, `POST /api/file`, `POST /api/fetch`, `POST /api/classify`, `POST /api/backfill`, and `GET /api/jobs/<id>`. It binds to 127.0.0.1, checks the Host header, and accepts only same-origin JSON POSTs. The Fetch panel asks for a date in the last month, filled with the same day one month ago. Fetch reads that window and reports how many papers need classification. Classify stays disabled until that count is above zero, then classifies every waiting paper. One job runs at a time. The library counts and the coverage dates sit at the bottom of the Fetch panel, behind More, and start closed. Less closes them again. A backfill still runs the same CLI as the workflow.

The published page has no API. Triage marks made there stay in `localStorage` until "Export triage" downloads `triage.json`, and `pixi run python -m literature triage PATH` loads it. Its backfill link opens the workflow on GitHub.

The daily job commits the SQLite file. Pull before triaging locally, and push soon after, or the binary file will conflict with the bot's next commit.

## The page

Plain HTML, CSS, and JavaScript in `literature/web/`. No npm build. `papers.js` sets `window.PAPERS`, `window.LATEST_RUN_ID`, and `window.LIBRARY` (status counts and the date range read). It is written one paper per line. Filters run in the browser. The list shows 10 cards per page, with page numbers above and below the cards. "Latest run" is the newest run that kept at least one paper, so a small backfill that keeps nothing does not empty the default view. It does not apply to unclassified papers, which belong to no run.

Kinds are `cycling`, `endurance`, and `physiology`. There is no lecture field and no link to the notes. The old Saved and Seen marks in `localStorage` are offered once as To read and Read.

Colors match the figures: paper `#f7f4ee`, ink `#1e2930`, teal `#1f6f6a`, orange `#c2410c` for the score. The page is English only. `hooks/copy_literature.py` copies `literature/web` to `site/literature` and skips the French build.

## Daily job

`.github/workflows/literature.yml` runs at 06:00 UTC and commits `literature/web/papers.js` and `literature/data/literature.sqlite`. A manual dispatch takes `papers` (up to 3000, about two seconds each, inside the 150-minute timeout) and an optional `since`, and runs `backfill`. The secret is `OPENROUTER_API_KEY`. `OPENALEX_MAILTO` is optional. A push with `GITHUB_TOKEN` does not start `pages.yml`, so that workflow also listens with `workflow_run`. Both deploys share the `pages` concurrency group.

Tests are `pixi run python -m unittest discover -s tests`.
