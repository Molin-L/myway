# Reports share the research reading style

The research workspace (`~/Research/theory`) grew its own reading page for
phase documents: Inter text, a serif title and numerals, a centred column,
an "On this page" outline with a sliding pill, a fixed component vocabulary
(lede, stats, callouts, timeline, cards, numbered blocks, footnotes), KaTeX,
and Vega-Lite charts themed from the page's tokens. The `report` skill had a
different look: system sans, a left outline card, a light/dark toggle, and a
hand-written D3 runtime. Two house styles meant two vocabularies to learn and
figures that could not move between a research document and a report.

We decided that **the `report` template adopts the theory reading style
wholesale**: the same tokens (`--site-*`, `--sf-tone-*`, `--sf-series`), the
same `sf-` components and markup, light only, and charts as Vega-Lite JSON
specs themed by the same `chartConfig()`. This supersedes the dark theme and
the D3 runtime of ADR 0002; its core rule stands, re-stated: the template's
style block is the only place a colour literal may appear, and the series
palette is the same validated eight slots in a fixed order.

## Consequences

- A report body is a fragment in the theory component vocabulary, so a
  section or a figure can be copied between a research document and a report.
- `report.py lint` fails when a report's `#sf-style` or `#sf-runtime`
  differs from the template, instead of hunting for colour literals in CSS,
  and checks the chart specs (inline data, no colours or config, axis titles
  with units, labelled reference lines).
- No dark mode and no toggle. Adding one later is a change to both pages,
  with a dark tone and series set validated like the light one.
- The outline shows `h2` and `h3` only; a third level becomes an `h4` label
  outside the outline.
- A change to the style is made in both places: `site/index.html` in the
  theory workspace and `templates/report.html` here.
- Reports made before this change fail the lint and are re-scaffolded with
  `report.py new`, moving the body over into the new components.
