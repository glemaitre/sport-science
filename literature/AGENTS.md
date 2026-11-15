# Literature job

A daily alert for a data scientist at a professional cycling team. It is not a lecture. Do not add it to `nav`, and do not edit the lecture notes from here.

What counts as a useful paper is [interest_brief.md](interest_brief.md). The first pass is `SCREEN_SYSTEM` in `classify.py`. It does not read the brief. If the interest changes, change both, or the screen will drop papers the brief would have kept.

## What to keep

Q1 and Q2 of SCImago Sports Science, area `3600`, category `3699`. The quartile is the Sports Science one in that download. Do not go back to Q1 only. Physiology from a similar continuous endurance sport counts when the mechanism would transfer to the bike. Biomechanics and aerodynamics count when the task is cycling, or when the method applies directly to the bike.

`Experimental Physiology` is not in this category. Adding it means a separate source, not a looser quartile.

## How a run works

`pixi run literature-journals` refreshes `journals`. `pixi run literature` fetches new OpenAlex works, classifies them, and rewrites `literature/web/papers.js`.

- Do not scrape journal sites or PDFs. Rankings come from SCImago. The download that returns the CSV is `journalrank.php` with `out=xls`. `format=csv` returns HTML. A script often gets a Cloudflare check. On that failure, keep the stored rows and use `pixi run python -m literature journals --csv PATH`.
- Papers come from the OpenAlex works API. Rebuild the abstract from the inverted index. A missing abstract is classified from the title.
- SQLite is `literature/data/literature.sqlite`, in DELETE journal mode. One file. Do not commit a `-wal` or `-shm`. The abstract stays in the database and stays out of `papers.js`.
- The watermark moves only through papers that were classified. A failed model call must not skip them. Keep is `score >= 6` in Python. Do not trust the model's keep flag.
- `literature/config.toml` holds the model (`~deepseek/deepseek-flash-latest`), a 7-day first lookback, the threshold of 6, and a cap of 200 papers per run. `OPENROUTER_MODEL` overrides the model. `OPENROUTER_API_KEY` is required to classify. `OPENALEX_MAILTO` is optional and only puts the calls in the polite pool.
- Do not run `pixi run literature` without a key. It fetches first, then stops, and leaves unclassified rows for the next run.

## The page

Plain HTML, CSS, and JavaScript in `literature/web/`. No npm build. `papers.js` is `window.PAPERS`. Search, kind, sport, journal, latest run, saved, hide seen, minimum score, date range, and sort all run in the browser.

Kinds are `cycling`, `endurance`, and `physiology`. There is no lecture field and no link to the notes. Saved and seen stay in `localStorage`, keyed by OpenAlex id. The page cannot write them back.

Colors match the figures: paper `#f7f4ee`, ink `#1e2930`, teal `#1f6f6a`, orange `#c2410c` for the score. The page is English only. `hooks/copy_literature.py` copies `literature/web` to `site/literature` and skips the French build.

## Daily job

`.github/workflows/literature.yml` runs at 06:00 UTC and commits `literature/web/papers.js` and `literature/data/literature.sqlite`. The secret is `OPENROUTER_API_KEY`. `OPENALEX_MAILTO` is optional. A push with `GITHUB_TOKEN` does not start `pages.yml`, so that workflow also listens with `workflow_run`. Both deploys share the `pages` concurrency group.

Tests are `pixi run python -m unittest discover -s tests`.
