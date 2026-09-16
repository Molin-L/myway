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
], { format: ",.0f" });
```

Grouped, two to four series. The key order in `values` is the slot order, so write the keys in the order the legend should show:

```js
Report.bar("#fig-by-region", [
  { label: "Q1", values: { EU: 120, US: 98 } },
  { label: "Q2", values: { EU: 131, US: 104 } }
]);
```

| Option | Default | Meaning |
|---|---|---|
| `format` | `",~f"` | a `d3.format` string for ticks, labels, tooltip |
| `height` | `280` | SVG height in px |
| `max` | data max | top of the y axis |
| `ticks` | `5` | y gridlines |
| `labels` | auto | `true` / `false` / `"all"`. Auto labels a single series with at most 12 bars |
| `series` | keys of `values` | explicit series order for grouped data |
| `margin` | `{top:12,right:16,bottom:28,left:44}` | override single sides |

## `Report.hbar(selector, data, opts)`

Same single-series data as `bar`. Height grows with the row count. Use it when labels are long or there are more than about eight categories. Sort the data by value before you pass it, unless the categories have a natural order.

Extra option: `labelWidth` (default `140`) for the left margin that holds the category names.

## `Report.line(selector, series, opts)`

```js
var d = function (s) { return new Date(s); };
Report.line("#fig-latency", [
  { name: "p50", values: [{ x: d("2026-09-08"), y: 41 }, { x: d("2026-09-09"), y: 40 }] },
  { name: "p99", values: [{ x: d("2026-09-08"), y: 171 }, { x: d("2026-09-09"), y: 174 }] }
], { format: ",.0f", xFormat: "%b %d" });
```

`x` is a `Date` for a time axis or a number for a linear axis. All series share one x and one y scale.

| Option | Default | Meaning |
|---|---|---|
| `format` | `",~f"` | y format for ticks, end labels, tooltip |
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
- Legend above the plot for two or more series. None for one series: the figure title names it.
- Tooltip on hover: per bar, or a crosshair with every series at that x on a line chart.
- Text in `--ink-2` / `--ink-3`, never a series colour.

## Rules for the author

- **One figure, one message.** Put the message in `.rp-figure__title`, units and window in `.rp-figure__sub`, the source in `figcaption`.
- **Data lives in the file.** Write it as JavaScript literals in the data script at the end of the body. No fetches, no external JSON.
- **Series order is meaning.** The first series is the one the story is about. Keep the same series in the same slot across every figure in the report.
- **Numbers in a table too.** A figure with more than about twelve values gets a table nearby or in an appendix; the runtime does not build one.
- **Status colours stay out of series.** A "failed" series is still a series slot; a status dot beside the label carries the state.

## A new form

Extend the runtime in `templates/report.html`, not the report. Reuse `frame`, `yGrid`, `legend`, `tooltip`, `observe`, and `SERIES`. Colour every mark with `SERIES[i]` or a `var(--token)`. Then update this file and the lint if the new form needs a new check. A raw D3 snippet inside a report with its own hex colours fails `report.py lint`.
