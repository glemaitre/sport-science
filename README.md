# Sport science notes

Lecture notes, rendered as a small website so they are easy to browse. Pixi installs the site generator and runs it.

```bash
pixi run serve
```

Then open [http://127.0.0.1:8765/sport-science/](http://127.0.0.1:8765/sport-science/). The pages reload when a note changes. The `/sport-science/` prefix matches the GitHub Pages address, so the language switcher points at the same paths locally and online.

```bash
pixi run build
```

writes the static site into `site/`. That folder is generated. The notes themselves live in `lectures/`.

The same notes exist in French, as files ending in `.fr.md`. The site language switcher links the two versions of a page.

Pushing `main` to [github.com/glemaitre/sport-science](https://github.com/glemaitre/sport-science) runs `.github/workflows/pages.yml`, which builds the site with pixi and publishes it to GitHub Pages at [glemaitre.github.io/sport-science](https://glemaitre.github.io/sport-science/). In the repository settings, Pages has to use GitHub Actions as its source.

## Literature

New papers from Q1 and Q2 Sports Science journals are collected in `literature/`. With the site running, the page is at [literature/index.html](http://127.0.0.1:8765/sport-science/literature/index.html). The same path is on GitHub Pages. It is not in the lecture navigation.

```bash
pixi run literature-journals
pixi run literature
```

`literature-journals` downloads the SCImago Sports Science ranking and keeps the Q1 and Q2 journals. If SCImago answers with a browser check instead of the file, use the Download link on that ranking page and run `pixi run python -m literature journals --csv PATH`. `literature` asks OpenAlex for new articles and reviews, then asks the model which ones are worth reading. Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`. The model is in `literature/config.toml`. On GitHub, the same key is the Actions secret `OPENROUTER_API_KEY`. The job runs every day at 06:00 UTC, then the site is published again.
