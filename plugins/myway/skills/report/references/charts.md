# Charts

The template ships a small D3 runtime, `window.Report`. It draws three forms with the house mark specs, a legend for two or more series, a hover tooltip, direct labels where they help, and a responsive redraw. Colours go through tokens, so a theme toggle re-colours every mark with no redraw.

## Pick the form first

| The data's job | Form | Call |
|---|---|---|
| A single headline number | stat tile or hero figure, not a chart | HTML, see [components.md](components.md) |
| Magnitude across a few categories | column | `Report.bar` |
| Magnitude across many or long-named categories | horizontal bar | `Report.hbar` |
| Magnitude across categories, two to four series | grouped column | `Report.bar` with `values` |
| Change over time, one to eight series | line | `Report.line` |
| Change over time with a volume feel, one series | area line | `Report.line` with `{ area: true }` |
| Exact values the reader will look up | table | `.rp-table` |

Never a dual axis. Two measures on different scales become two figures side by side in `.rp-cols`, or one indexed to a common base. Never a pie for more than two slices; use a horizontal bar. Never more than eight series; fold the rest into "Other" or split into small multiples.

## `Report.bar(selector, data, opts)`

Single series:

```js
Report.bar("#fig-requests", [
  { label: "Mon", value: 212 }, { label: "Tue", value: 231 }
], { format: ",.0f", yLabel: "Requests (thousands)", xLabel: "Day of week" });
```

Grouped, two to four series. The key order in `values` is the slot order, so write the keys in the order the legend should show:

```js
Report.bar("#fig-by-region", [
  { label: "Q1", values: { EU: 120, US: 98 } },
  { label: "Q2", values: { EU: 131, US: 104 } }
], { yLabel: "Revenue (k EUR)", xLabel: "Quarter (2026)" });
```

| Option | Default | Meaning |
|---|---|---|
| `format` | `",~f"` | a `d3.format` string for ticks, labels, tooltip |
| `yLabel` | none | value-axis title, quantity and unit: `"Latency (ms)"`. Required; the lint warns without it |
| `xLabel` | none | category-axis title: `"Day of week"`, `"Region"`. Omit only when the category labels are self-evident |
| `height` | `280` | SVG height in px |
| `max` | data max | top of the y axis |
| `ticks` | `5` | y gridlines |
| `labels` | auto | `true` / `false` / `"all"`. Auto labels a single series with at most 12 bars |
| `series` | keys of `values` | explicit series order for grouped data |
| `margin` | `{top:12,right:16,bottom:28,left:44}` | override single sides |

## `Report.hbar(selector, data, opts)`

Same single-series data as `bar`. Height grows with the row count. Use it when labels are long or there are more than about eight categories. Sort the data by value before you pass it, unless the categories have a natural order.

Extra option: `labelWidth` (default `140`) for the left margin that holds the category names. The value axis is horizontal, so its title goes in `xLabel`: `{ xLabel: "Build time (s)" }`.

## `Report.line(selector, series, opts)`

```js
var d = function (s) { return new Date(s); };
Report.line("#fig-latency", [
  { name: "p50", values: [{ x: d("2026-09-08"), y: 41 }, { x: d("2026-09-09"), y: 40 }] },
  { name: "p99", values: [{ x: d("2026-09-08"), y: 171 }, { x: d("2026-09-09"), y: 174 }] }
], { format: ",.0f", xFormat: "%b %d", yLabel: "Latency (ms)", xLabel: "Date (UTC)" });
```

`x` is a `Date` for a time axis or a number for a linear axis. All series share one x and one y scale.

| Option | Default | Meaning |
|---|---|---|
| `format` | `",~f"` | y format for ticks, end labels, tooltip |
| `yLabel` | none | y-axis title, quantity and unit: `"Throughput (req/s)"`. Required |
| `xLabel` | none | x-axis title. For time: the resolution and the zone, `"Day (UTC)"`. For a number: quantity and unit, `"Payload size (KiB)"`. Required |
| `xFormat` | `"%b %d"` time / `"~f"` number | a `d3.timeFormat` or `d3.format` string |
| `xTicks` | `6` | x tick count |
| `zero` | `true` | y axis starts at zero. `false` lets it start at the data minimum. Say so in the sub-title |
| `min`, `max` | data | y domain override |
| `area` | `false` | a 10% wash under each line |
| `curve` | `"linear"` | `"smooth"` for a monotone curve |
| `labels` | `true` | end-of-line value labels, shown for at most four series |
| `height`, `margin`, `ticks` | as `bar` | |

## Mark specs the runtime applies

- Bars at most 24px thick, 4px rounded data-end, square at the baseline, a surface gap between neighbours from band padding.
- Lines 2px with round joins. End dots 8px with a 2px `--surface` ring.
- Gridlines hairline, `--grid`. Baseline `--axis`. No axis domain path.
- Axis titles in `--ink-2`, 12px, centred on the axis. The y title is rotated 90°. Each title adds 18px of margin on its side.
- Legend above the plot for two or more series. None for one series: the figure title names it.
- Tooltip on hover: per bar, or a crosshair with every series at that x on a line chart.
- Text in `--ink-2` / `--ink-3`, never a series colour.

## Figure requirements

A figure must stand on its own. A reader who sees only the figure, with no prose, must be able to name the quantity, its unit, the window, the sample, and the source. Fill every part below; the lint warns on the ones it can see.

| Part | Where | Content | Example |
|---|---|---|---|
| Number | start of `figcaption` | `Figure N.` in document order. Prose cites the number, never "the chart below" | `Figure 3.` |
| Message | `.rp-figure__title` | The finding as a sentence, not the variable name | `p99 latency rose 10% after the Thursday deploy` |
| Quantity, unit, window, n | `.rp-figure__sub` | What is plotted, the unit, the time window with zone, the sample size, and any aggregation | `Latency (ms) per percentile, daily median of hourly samples. 2026-09-07 to 2026-09-13, UTC. n = 168 h.` |
| Value-axis title | `yLabel` (`xLabel` for `hbar`) | Quantity and unit in parentheses | `Latency (ms)`, `Requests (count)`, `Share (%)` |
| Category or x-axis title | `xLabel` | What the positions are. For time: resolution and zone | `Day (UTC)`, `Region`, `Payload size (KiB)` |
| Source and method | `figcaption` after the number | Where the data came from, how it was reduced, and any caveat | `Source: gateway metrics, Prometheus 5 m scrape, median per day.` |

### Units

- **Every value axis has a unit.** Write the quantity, then the unit in parentheses: `Latency (ms)`. A count is a unit too: `Requests (count)`. A ratio is `(%)` or `(ratio)`; say which base.
- **Use SI units and SI prefixes** where they exist: `ms`, `s`, `MB`, `GiB`, `req/s`. Do not mix `MB` and `MiB` in one report.
- **Put a scale factor on the axis, not in prose.** Write `Requests (thousands)` and plot `212`, or plot `212000` with `format: ",.0f"`. Never plot scaled numbers under an unscaled title.
- **One unit per quantity across the report.** If latency is in `ms` in Figure 1, it is in `ms` in every figure and table.
- **Tick format matches the unit's precision.** Milliseconds as integers, ratios to one decimal, money to the cent only in a table.
- **Time axes state the zone and the resolution** in `xLabel` or the sub: `Hour (UTC)`, `Day (Europe/Paris)`. Never leave a date axis with an unstated zone.
- **Rates carry both units:** `Throughput (req/s)`, `Cost (USD/day)`.

### Scales and sample

- **The y axis starts at zero** for bars always and for lines by default. If a line uses `zero: false`, the sub says `y axis starts at <min>`.
- **State the sample.** `n = 7 days`, `n = 1 240 requests`, `3 runs per point`. If a point is an aggregate, name the statistic: `median`, `mean`, `p99`.
- **State uncertainty when it exists.** The runtime draws no error bars, so give the spread in the sub or the caption: `mean of 3 runs, range ±4%`, and put per-run values in a table.
- **No truncated or broken axes, no log scale without `(log)` in the axis title,** and no secondary axis at all.

### Rules for the author

- **One figure, one message.** Put the message in `.rp-figure__title`, units and window in `.rp-figure__sub`, the source in `figcaption`.
- **Data lives in the file.** Write it as JavaScript literals in the data script at the end of the body. No fetches, no external JSON.
- **Series order is meaning.** The first series is the one the story is about. Keep the same series in the same slot across every figure in the report.
- **Numbers in a table too.** A figure with more than about twelve values gets a table nearby or in an appendix; the runtime does not build one.
- **Status colours stay out of series.** A "failed" series is still a series slot; a status dot beside the label carries the state.

## A new form

Extend the runtime in `templates/report.html`, not the report. Reuse `frame`, `yGrid`, `legend`, `tooltip`, `observe`, and `SERIES`. Colour every mark with `SERIES[i]` or a `var(--token)`. Then update this file and the lint if the new form needs a new check. A raw D3 snippet inside a report with its own hex colours fails `report.py lint`.
