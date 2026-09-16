---
name: report
description: Generate a self-contained HTML report in the house style — one template, light/dark theme with a toggle in the nav bar, D3 charts through a fixed token palette. Use when the user says "report", "html report", "write this up as a page", "make a dashboard page", "generate a report from this data", or wants results, benchmarks, an audit, or a weekly summary as a shareable HTML file. Do NOT use for a Markdown summary in chat, for slides, or for weekly goals on GitLab (that is `weekly-goal`).
---

# Report

A report is one HTML file. It comes from `templates/report.html`, which carries the house tokens for both themes, a sticky nav with the theme toggle, and a D3 runtime that draws charts in the house marks. The author supplies the title, the sections, and the data. The style is not a choice.

Paths are relative to this skill directory. Under Claude Code that is `${CLAUDE_PLUGIN_ROOT}/skills/report/`.

| File | Contents |
|---|---|
| `scripts/report.py` | `new` scaffolds a report, `lint` checks one, `tokens` lists the tokens |
| `templates/report.html` | The template: tokens, nav, toggle, components, chart runtime, an example body |
| [references/house-style.md](references/house-style.md) | Tokens, type, layout, the theme mechanism, what may not change |
| [references/components.md](references/components.md) | HTML blocks: section, tiles, hero, figure, table, status, callout, key–value |
| [references/charts.md](references/charts.md) | `Report.bar` / `hbar` / `line` API, form choice, mark specs, author rules |

## The arc

### 1. Gather

Settle these before you write. Ask only for what the request and the workspace do not give you.

- **Title, subtitle, author, date.** Date defaults to today. Author defaults to `git config user.name`.
- **Output path.** Default `reports/<yyyy-mm-dd>-<slug>.html` in the current repo, or the path the user named.
- **Sections.** Three to six. The first is a summary that states the findings before any chart.
- **Data.** Where it is, and what each figure should say. If a number has to be computed, compute it now and keep the source at hand for the captions.

### 2. Scaffold

```sh
scripts/report.py new <out.html> --title "<title>" --subtitle "<sub>" [--author A] [--date YYYY-MM-DD]
```

The result has the tokens, the nav, the header, an empty `SECTIONS` region, and the runtime. Use `--with-example` only to show the user the style before content exists.

### 3. Write the sections

Replace the comment between `<!-- SECTIONS:BEGIN -->` and `<!-- SECTIONS:END -->` with `section.rp-section` blocks from [references/components.md](references/components.md). Rules:

- Every section has an `id` and starts with an `h2`. The nav builds itself from them.
- Lead with the finding. Tiles or a callout first, then the figures, then the table, then the detail.
- Use house classes only. No inline `style`, no second `<style>` block, no colour literal.
- Prose follows the same rules as any writing for the user: short sentences, the answer first.

### 4. Add the figures

A figure must stand on its own, with no help from the prose. The full requirements are in [references/charts.md](references/charts.md#figure-requirements). For each chart:

- `figure.rp-figure` with an `id`.
- `.rp-figure__title`: the finding as a sentence.
- `.rp-figure__sub`: the quantity, the unit, the window with time zone, the sample size, and the statistic (`median`, `p99`).
- `figcaption`: `Figure N.` first, then the source and the method.
- A `Report.*` call in a `<script>` after the runtime, with the data as literals.
- `yLabel` (`xLabel` for `hbar`) on the value axis: quantity and unit in parentheses, `"Latency (ms)"`, `"Requests (count)"`, `"Share (%)"`.
- `xLabel` on the category or time axis: `"Region"`, `"Day (UTC)"`. Required on every line chart.

Pick the form from the table in [references/charts.md](references/charts.md). One message per figure. No dual axis. One unit per quantity across the whole report. At most eight series, in a fixed order that holds across the whole report.

A figure with many values also gets a table, with the unit in the column header.

### 5. Lint

```sh
scripts/report.py lint <out.html>
```

Fix every error. Read every warning and act on it or say why not. The lint checks the theme bootstrap, the toggle, the nav container, section ids and headings, figure ids and captions, figure numbers, the sub line, axis titles and their units, unfilled placeholders, colour literals outside the token block, and remote resources other than the D3 CDN.

### 6. Look at it

Open the file in a browser if one is available, or screenshot it with a headless one. Check both themes with the toggle: label collisions, overflow, a legend for every multi-series figure, a caption on every figure, and a titled value axis with a unit on every chart. Read each figure with the prose hidden. If you cannot tell the unit, the window, or the sample, fix the figure. If no browser is available, say so in the report to the user, and syntax-check the inline scripts with `node --check` instead.

### 7. Report

Give the user the path, the section list, and the figures with one line each on what they show. Mention anything the lint warned about that you left in place.

## Rules

- **Never change the tokens in a report.** A colour need becomes a template change in this skill, with both themes stepped and the palette re-validated.
- **Never hand-write the nav.** It comes from the `h2`s.
- **Never fetch data at view time.** The file is self-contained; only D3 loads from the CDN. For an offline reader, save `d3.min.js` beside the file and point the `src` at it.
- **Never use a status colour as a series colour**, and never a colour without a word beside it.
- **Do not add a web font.** The house type is the system sans.
