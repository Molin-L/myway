# House style

One template, one style block, one look. Every report is a single self-contained HTML file built from `templates/report.html`. The style is the reading page of the research workspace (`~/Research/theory/site/index.html`), itself adapted from numbers.sfinterface.com: same token names, same `sf-` class prefix, same components. A report author writes the body and the data, nothing else.

## What may not change

| Part | Rule |
|---|---|
| Style block | `<style id="sf-style">`, the only place a colour literal may appear. `report.py lint` fails when it differs from the template by a single byte. |
| Runtime | `<script id="sf-runtime">`: math, footnotes, section numerals, the outline, and the charts. Same rule: identical to the template. |
| Top bar | `header.sf-topbar`: the file path on the left (the "Contents" button on narrow screens), the brand in the centre (kicker in italic serif over the project name in spaced capitals), the date on the right. No section links. |
| Outline | `nav#contents`, built at load from the `h2` and `h3` headings in the body plus the Sources list. Never hand-written. |
| Typeface | Inter (vendored, latin subset, variable weight and optical size) for text, the system serif stack (Iowan Old Style, Palatino, Georgia) for the title, the brand, numerals, stat values, and dates, the system monospace for paths and code. |
| Theme | Light only. The background is a flat colour, no grain, no dark mode. |
| Remote resources | None. Inter, KaTeX, and Vega are vendored in `vendor/` and inlined by `report.py bundle` into the VENDOR region in `<head>`, so a report opens offline and in a private network. The lint fails on any remote `src` or `href` in a script, link, image, iframe, or source. |
| Vendor region | Between `<!-- VENDOR:BEGIN -->` and `<!-- VENDOR:END -->`, written only by `bundle`: the Inter `@font-face` rules always, KaTeX (stylesheet with woff2 fonts as data URIs, and scripts) when the body has math, Vega when it has charts. The lint fails when it does not match what the body needs. |
| Reference config | `<meta name="sf-refs">`, a JSON object written by `new`: the default `project` and one link template per sigil (`#`, `!`, `~`) with `{project}` and `{id}`. The one part of the head a report may edit by hand, to point references elsewhere. |

## Tokens

### Planes and ink

| Token | Value | Role |
|---|---|---|
| `--site-bg` | `#fdfdfc` | page background |
| `--site-surface` | `#ffffff` | cards, charts, stat cells, code |
| `--site-fg` | `#1c1c21` | titles, headings, strong text |
| `--site-prose` | `#2f2f2d` | body text |
| `--site-muted` | `#6f6f6c` | secondary text, captions, axis labels |
| `--site-subtle` | `#9a9a96` | numerals, table headers, labels, reference lines |
| `--site-line` | `rgba(17,17,17,.09)` | hairlines, gridlines, rules |
| `--site-pill` | `rgba(17,17,17,.05)` | the outline pill, tags, footnote markers |
| `--site-ring` | two-layer shadow | the ring around every surface |

### Tones

Components that take `data-tone` resolve it to `--tone`:

| Tone | Token | Value | Meaning |
|---|---|---|---|
| (none) | `--sf-tone-neutral` | `#6f6f6c` | the default; most blocks |
| `accent` | `--sf-tone-accent` | `#036ee6` | key idea, current, turning point |
| `positive` | `--sf-tone-positive` | `#1a7f4b` | recommended, healthy, a good change |
| `caution` | `--sf-tone-caution` | `#a86400` | risk, degraded, needs a decision |
| `negative` | `--sf-tone-negative` | `#c4321c` | refuted, blocker, a bad change |

Tone is emphasis, never identity: it marks a state, and a word beside it says which.

### Chart series

`--sf-series` is the validated categorical palette, in fixed order: blue `#2a78d6`, orange `#eb6834`, aqua `#1baf7a`, yellow `#eda100`, magenta `#e87ba4`, green `#008300`, violet `#4a3aa7`, red `#e34948`. The runtime hands it to Vega-Lite as the category range, so the first series is always blue, the second orange. Never cycle, never re-sort by value, never skip a slot. A ninth series folds into "Other" or the chart splits.

## Type and rhythm

| Element | Spec |
|---|---|
| Body | Inter 14px / 1.55, `--site-prose`, letter-spacing −0.011em, measure 62ch |
| Title (`h1.sf-doc-title`) | serif 40px (34px below 760px), weight 400 with a hairline stroke |
| Kicker (`.sf-doc-group`) | 13px, `--site-subtle`, above the title |
| Meta line | path in mono, date in italic, author muted |
| Lede | 16px / 1.6, `--site-fg`, measure 60ch |
| `h2` | 17px, weight 540, 56px above; a serif roman numeral in front |
| `h3` | 14.5px, weight 540, 32px above |
| `h4` | 11px uppercase label, `--site-subtle`; not in the outline |
| Column | `--site-content` = 644px, centred |
| Radius | 12px on surfaces, full pills on badges, tags, and the outline pill |

## Outline

| Behaviour | Rule |
|---|---|
| Entries | One per `h2` (with its numeral) and `h3` in the body, in document order, then "Sources" when the body has footnotes. |
| Ids | An author's `id` is kept; otherwise the runtime makes one from the text (`Error budget` becomes `error-budget`). Write a short `id` on an `h3` that others will link to. |
| Current entry | The last heading above a line just under the top bar; at the end of the page, the last entry. A grey pill slides to it, and the rail scrolls to keep it in view. |
| Width | Fixed at 186px, 44px right of the column. Long names end in an ellipsis; the full name is the link's title. |
| Narrow screens | Below 1180px the rail leaves the page and the "Contents" button replaces the path in the top bar. It opens the outline as a drawer from the left; a click on an entry, the scrim, or `Escape` closes it. |
| No headings | The outline and its button hide. |

## Print

The top bar, the outline, and the drawer hide. Figures, equations, cards, callouts, numbered blocks, and timeline entries do not break across pages, and a heading stays with the block after it.
