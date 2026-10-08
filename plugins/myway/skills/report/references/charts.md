# Charts

A chart is a Vega-Lite v5 spec, written as JSON inside the body. `report.py bundle` inlines Vega, Vega-Lite, and vega-embed from `vendor/` when the body has a chart (nothing loads from a CDN), and the runtime draws each spec with `vega-embed` at the column's width and 240px high (a spec may set `height`), and themes it from the tokens: Inter, muted axes, hairline grid with no vertical lines, the series palette in fixed order, a legend on top, tooltips on every mark, 2px lines, rounded bar ends, and dashed muted reference lines.

```html
<figure class="sf-figure" id="fig-latency">
  <div class="sf-chart"><script type="application/json">
  { …Vega-Lite spec… }
  </script></div>
  <figcaption><strong>Figure 2.</strong> The message. Quantity, window, n. Data: source.</figcaption>
</figure>
```

## Pick the form first

| The data's job | Form | Spec |
|---|---|---|
| A single headline number | a stat, not a chart | `div.sf-stats`, see [components.md](components.md) |
| Magnitude across a few categories | column | `"mark": "bar"`, nominal or ordinal x |
| Magnitude across many or long-named categories | horizontal bar | `"mark": "bar"`, the category on y, sorted by value unless the order is natural (`"sort": "-x"`) |
| Magnitude across categories, two to four series | grouped column | bar with `"xOffset": {"field": "series"}` and `"color": {"field": "series"}` |
| Change over time, one to eight series | line | `"mark": "line"` with a temporal x and a `color` field |
| Change over time with a volume feel, one series | area | `"mark": "area"` |
| Relation between two measures | scatter | `"mark": "point"`, at most three series |
| Exact values the reader will look up | table | `<table>` with `class="num"` columns |
| A measure against a target or an SLO | the same form plus a reference line | a `layer` with `rule` and `text`, see below |

Never a dual axis: two measures on different scales become two figures, or one indexed to a common base. Never a pie or donut (`arc`); use a bar. Never more than eight series; fold the rest into "Other" or split the figure. Use only `line`, `bar`, `point`, `area`, plus `rule` and `text` for reference lines; the lint warns on other marks.

## What the author writes, and what not

- **Data inline** as `"data": {"values": [...]}`. Never `"url"`: the lint fails on it. The file is self-contained.
- **No colours, fonts, or config.** No `"config"`, no `"scheme"`, no scale `"range"`, no hex or `rgb()` anywhere in the spec: the lint fails on each. Series get the palette by the order of their first appearance in `values`, so write the series the story is about first, and keep each series in the same slot across every figure.
- **Long-form data.** One row per point with a series column (`{"day": …, "pct": "p99", "ms": 184}`), encoded as `"color": {"field": "pct", "type": "nominal", "title": null}`. The legend then shows the series names; `"title": null` drops the redundant legend title.
- **Category order.** Vega-Lite sorts categories alphabetically. Write `"sort": null` to keep the data order (days of the week, quarters).
- **Time.** Dates as ISO strings with `"type": "temporal"`. For a daily axis add `"timeUnit": "utcyearmonthdate"` and an axis format (`"axis": {"format": "%a %d"}`) so ticks fall on days in UTC.

## Reference lines

A target, an SLO, a budget, or last quarter's level is a reference line, not a series. Write it as two extra layers, a `rule` and a `text` that names it. The theme draws the rule as a muted 5–4 dash and the text in muted 11px; set no colour.

```json
{"data": {"values": [ … ]},
 "layer": [
   {"mark": {"type": "line", "point": true}, "encoding": { … }},
   {"mark": "rule", "encoding": {"y": {"datum": 180}}},
   {"mark": {"type": "text", "align": "left", "dx": 4, "dy": -7},
    "encoding": {"y": {"datum": 180}, "x": {"value": 0}, "text": {"value": "SLO 180 ms"}}}
 ]}
```

Put the label where the data is not (here the left end, `"x": {"value": 0}`; `"x": {"value": "width"}` with `"align": "right"` for the right end). The lint warns on a `rule` with no `text` layer.

## Missing data

A missing point is a row with `null` for the value. Write it; do not drop the row and do not write a zero.

- A line or area breaks and leaves a gap; it does not join across the hole and does not fall to zero. A bar is simply absent.
- The null stays out of the axis domain, so one hole does not move the scale.
- **Say it in the caption:** `n = 7 days, 1 missing (Wednesday scrape gap)`. The gap is visible; the reason is not.

## Log scales and illustrative curves

- A log y axis on a line: `"scale": {"type": "log"}` and say `(log)` in the title, `"Latency (ms, log)"`. A value at or below zero drops out.
- A log-scale bar chart also needs `"stack": null` and `"scale": {"type": "log", "zero": false}` on y plus `"y2": {"datum": <axis floor>}`; otherwise the bars start at zero and are not drawn.
- A curve computed from a model (`"data": {"sequence": …}` with `calculate` transforms) must say "Illustrative" in the caption and name the formula. The lint warns otherwise.

## Figure requirements

A figure must stand on its own. A reader who sees only the figure, with no prose, must be able to name the quantity, its unit, the window, the sample, and the source.

| Part | Where | Content | Example |
|---|---|---|---|
| Number | start of `figcaption`, in `<strong>` | `Figure N.` in document order. Prose cites the number, never "the chart below" | `<strong>Figure 3.</strong>` |
| Message | caption, first sentence | The finding as a sentence, not the variable name | `p99 latency rose 10% after the Thursday deploy.` |
| Window, n, statistic | caption, next | The time window with zone, the sample size, any aggregation | `Daily median of hourly percentiles, 2026-09-07 to 2026-09-13, UTC; n = 7 days.` |
| Source | caption, last, after `Data:` | Where the data came from, how it was reduced, any caveat | `Data: gateway metrics, Prometheus 5 m scrape.` |
| Value-axis title | `"title"` on the quantitative encoding | Quantity and unit in parentheses | `"Latency (ms)"`, `"Requests (count)"`, `"Share (%)"` |
| Category or time-axis title | `"title"` on the other encoding | What the positions are. For time: resolution and zone | `"Day (UTC)"`, `"Region"`, `"Payload size (KiB)"` |

The lint warns on a missing `Figure N.`, numbers out of order, a caption with no `Data:`, a quantitative axis with no title or no unit, and a temporal axis with no title.

### Units

- **Every value axis has a unit.** Quantity, then the unit in parentheses: `Latency (ms)`. A count is a unit too: `Requests (count)`. A ratio is `(%)` or `(ratio)`; say which base.
- **SI units and prefixes** where they exist: `ms`, `s`, `MB`, `GiB`, `req/s`. Do not mix `MB` and `MiB` in one report.
- **A scale factor goes on the axis.** Write `Requests (thousands)` and plot `212`, never scaled numbers under an unscaled title. Or plot `212000` with `"axis": {"format": "~s"}`.
- **One unit per quantity across the report.** If latency is in `ms` in Figure 1, it is in `ms` in every figure and table.
- **Time axes state the zone and the resolution:** `Hour (UTC)`, `Day (Europe/Paris)`.
- **Rates carry both units:** `Throughput (req/s)`, `Cost (USD/day)`.

### Scales and sample

- **The y axis starts at zero** for bars always and for lines by default (Vega-Lite's default). If a line uses `"scale": {"zero": false}`, the caption says where the axis starts.
- **State the sample.** `n = 7 days`, `n = 1 240 requests`, `3 runs per point`. If a point is an aggregate, name the statistic: median, mean, p99.
- **State uncertainty when it exists.** Give the spread in the caption (`mean of 3 runs, range ±4%`), or draw it with an `errorband` / `errorbar` layer, and put per-run values in a table.
- **A figure with more than about twelve values gets a table** nearby or in an appendix.

## A new form or a theme change

Change the template in this skill, not the report: `chartConfig()` in `#sf-runtime` holds the theme. Keep it in step with the theory reading page, which shares it. Then update this file and the lint if the change needs a new check.
