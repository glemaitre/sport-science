# Sport science notes

Lecture notes on cycling physiology, published as a bilingual static site. The reader is learning the physiology. They do not already know the vocabulary. Define a term in plain language the first time a lecture uses it, in both languages.

How to write a lecture, and the physiology later notes must stay consistent with, is in [lectures/AGENTS.md](lectures/AGENTS.md). That file is excluded from the site (`exclude_docs`), because `docs_dir` is `lectures/`.

## Site

- `pixi run serve` previews at `http://127.0.0.1:8765/sport-science/`. The `/sport-science/` prefix comes from `site_url` and must stay, or the language switcher will not match GitHub Pages.
- `pixi run build` is `mkdocs build --strict`. French is `mkdocs-static-i18n`: unsuffixed `.md` is English, `.fr.md` is French. Keep both in step. Links between lectures stay unsuffixed; the plugin rewrites them.
- `use_directory_urls: false`, so links are `index.html` and work from `file://`.
- Do not turn `navigation.instant` back on. It conflicts with the language switcher and `--strict` aborts on that warning.
- `theme.icon.logo` is `material/bike`. Do not also set `theme.logo` or `theme.favicon` to that icon.
- Mermaid is drawn by `lectures/javascripts/mermaid.js`, loaded after the Material bundle. Material's own theme leaves the labels near-black, so diagrams vanish on the dark page. Keep that script.
- Pages: `.github/workflows/pages.yml` on push to `main`, and again after a successful literature run. The GitHub Pages source is the workflow, not the branch root. `site/` is gitignored.
- Do not commit or push unless asked.

## Literature

How the literature job works, and the decisions a later change must stay consistent with, is in [literature/AGENTS.md](literature/AGENTS.md). It is not a lecture. Do not add it to `nav`. `docs_dir` is `lectures/`, so that file is not on the site.

## Figures

Original drawings only. Do not copy a textbook or Wikimedia figure into the notes.

- SVG, viewBox around 960–980. Paper `#f7f4ee`, ink `#1e2930`, membrane teal `#1f6f6a`, ATP `#c2410c`.
- French labels live in a sibling `*.fr.svg`, referenced explicitly from the `.fr.md`.
- Write real UTF-8. A stray cp1252 byte (a `?` where an en dash or a middle dot was) makes the XML invalid and the image disappears.
- If an SVG is rewritten with ElementTree, strip the `ns0:` prefix and restore the default `xmlns`. Check it parses.
