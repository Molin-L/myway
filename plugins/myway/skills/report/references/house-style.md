# House style

One template, one token block, one look. Every report is a single self-contained HTML file built from `templates/report.html`. The template carries the tokens, the layout, the nav with the theme toggle, and the chart runtime. A report author writes sections and data, nothing else.

## What may not change

| Part | Rule |
|---|---|
| Token block | The first `<style>` in the file. The only place a colour literal may appear. Do not add, remove, or rename tokens in a report; change the template instead. |
| Theme mechanism | `data-theme` on `<html>`, set before paint from `localStorage` (`rp-theme`) or the OS preference. The nav button toggles it. Do not add a second mechanism. |
| Nav | Sticky, built at load from every `section.rp-section[id] > h2`. Do not hand-write nav links. |
| Chart runtime | `Report.bar`, `Report.hbar`, `Report.line` (see [charts.md](charts.md)). Extend the runtime in the template if a new form is needed; do not paste a one-off D3 snippet with its own colours. |
| Typeface | System sans (`--font`). No web fonts, no display face, no serif. |
| Remote resources | D3 from `https://cdn.jsdelivr.net/npm/d3@7` only. For an offline report, save `d3.min.js` next to the file and change the `src`; `report.py lint` accepts either. |

`scripts/report.py lint` enforces these. A colour literal outside the token block is an error, not a warning.

## Tokens

Both themes are **selected** values, not an automatic inversion. The values come from the validated dataviz palette: every adjacent categorical pair clears the colour-vision-deficiency (CVD) floor in both modes.

### Planes and ink

| Token | Role | Light | Dark |
|---|---|---|---|
| `--plane` | page background | `#f9f9f7` | `#0d0d0d` |
| `--surface` | cards, figures, nav, tooltips | `#fcfcfb` | `#1a1a19` |
| `--border` | hairline ring | `rgba(11,11,11,.10)` | `rgba(255,255,255,.10)` |
| `--ink-1` | primary text | `#0b0b0b` | `#ffffff` |
| `--ink-2` | secondary text, legend, labels | `#52514e` | `#c3c2b7` |
| `--ink-3` | muted: axis ticks, captions, meta | `#898781` | `#898781` |
| `--grid` | hairline gridlines | `#e1e0d9` | `#2c2c2a` |
| `--axis` | baseline, crosshair, reference line | `#c3c2b7` | `#383835` |
| `--delta-up` | a good change, as text | `#006300` | `#0ca30c` |
| `--accent` | links, callout rule | `var(--series-1)` | `var(--series-1)` |

### Categorical series (fixed order)

| Token | Hue | Light | Dark |
|---|---|---|---|
| `--series-1` | blue | `#2a78d6` | `#3987e5` |
| `--series-2` | orange | `#eb6834` | `#d95926` |
| `--series-3` | aqua | `#1baf7a` | `#199e70` |
| `--series-4` | yellow | `#eda100` | `#c98500` |
| `--series-5` | magenta | `#e87ba4` | `#d55181` |
| `--series-6` | green | `#008300` | `#008300` |
| `--series-7` | violet | `#4a3aa7` | `#9085e9` |
| `--series-8` | red | `#e34948` | `#e66767` |

The order is the safety mechanism. Slot 1 is always the first series, slot 2 the second. Never cycle, never re-sort by value, never skip a slot. A ninth series folds into "Other" or the chart becomes small multiples. For scatter and other all-pairs forms, stop at three series.

### Sequential and diverging

`--seq-1` (lightest, near zero) to `--seq-7` (darkest). One hue, blue. In dark mode the steps reverse so that `--seq-1` is still the step nearest the surface. Diverging: `--series-1` (blue) and `--series-8` (red) as the poles, `--div-mid` as the neutral midpoint.

### Status (reserved)

`--good`, `--warning`, `--serious`, `--critical`. The same values in both modes. Never use a status token as a series colour. Never use a status colour alone: pair it with a label (`.rp-status` does this) or an icon.

## Type and rhythm

| Element | Spec |
|---|---|
| Body | 16px / 1.55, `--ink-1` |
| `h1` | 2rem, weight 650 |
| `h2` | 1.4rem, one per section, the nav label |
| `h3` | 1.1rem, sub-topics inside a section |
| Measure | `--measure` = 72rem, centred |
| Radius | `--radius` = 6px on cards, figures, tables, tooltips |
| Figures in text | proportional. `tabular-nums` only in table columns and axis ticks |

Text never wears a series colour. Identity comes from a swatch, a dot, or a mark beside the text.

## Theme toggle

The button in the nav (`#rp-toggle`) flips `data-theme` between `light` and `dark` and stores the choice under `rp-theme` in `localStorage`. The bootstrap script in `<head>` reads the stored value before first paint, so the page never flashes. With no stored value the OS preference wins.

Charts need no redraw on a toggle. Every mark sets its colour through `var(--series-n)` or `var(--surface)`, so the browser re-resolves the tokens when `data-theme` changes.

## Print

The nav becomes static and the toggle hides. Figures, tiles, and cards do not break across pages. The printed theme is whatever the screen showed. Toggle to light before you print.
