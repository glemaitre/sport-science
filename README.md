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
