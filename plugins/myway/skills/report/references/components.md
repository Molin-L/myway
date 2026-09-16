# Components

Every block below is plain HTML with house classes. Copy the block, fill the text, keep the class names. Do not add inline styles.

## Section

One `<section>` per nav entry. The `id` is the anchor; the `h2` is the nav label.

```html
<section class="rp-section" id="throughput">
  <h2>Throughput</h2>
  <p>One paragraph that states the finding first.</p>
</section>
```

## Stat tiles

A row of headline numbers. Three to five tiles. The delta names the period it compares against. `is-up` means a good change, `is-down` a bad one, whichever direction the number moved.

```html
<div class="rp-tiles">
  <div class="rp-tile">
    <div class="rp-tile__label">Requests served</div>
    <div class="rp-tile__value">1.28M</div>
    <div class="rp-tile__delta is-up">+4.2% vs last week</div>
  </div>
</div>
```

Compact the value by hand: `1,284` / `12.9K` / `$4.2M`.

## Hero figure

The one number a report leads with. At most one per report.

```html
<div class="rp-tile__label">Monthly recurring revenue</div>
<div class="rp-hero">$412K</div>
<div class="rp-tile__delta is-up">+6.1% vs August</div>
```

## Figure (chart holder)

A chart lives in a figure with an `id`. Title says what is plotted, sub says units and window, caption names the source. The runtime inserts the legend and the SVG between the sub and the caption.

```html
<figure class="rp-figure" id="fig-requests">
  <p class="rp-figure__title">Requests per day</p>
  <p class="rp-figure__sub">Last 7 days, thousands</p>
  <figcaption>Source: gateway access logs.</figcaption>
</figure>
```

Then, in the data script at the end of the body:

```html
<script>
  Report.bar("#fig-requests", [{ label: "Mon", value: 212 }, { label: "Tue", value: 231 }], { format: ",.0f" });
</script>
```

Two figures side by side:

```html
<div class="rp-cols">
  <figure class="rp-figure" id="fig-a">…</figure>
  <figure class="rp-figure" id="fig-b">…</figure>
</div>
```

## Table

Numbers right-aligned with `class="num"`. A table is also the accessible fallback for a chart, so every chart with more than a handful of points should have one nearby or in an appendix.

```html
<table class="rp-table">
  <thead><tr><th>Service</th><th>Status</th><th class="num">Requests</th></tr></thead>
  <tbody>
    <tr><td>gateway</td><td><span class="rp-status is-good">healthy</span></td><td class="num">1,284,001</td></tr>
  </tbody>
</table>
```

## Status pill

Colour plus a word, never colour alone. Variants: `is-good`, `is-warning`, `is-serious`, `is-critical`, or none for neutral.

```html
<span class="rp-status is-warning">degraded</span>
```

## Callout

For the finding that needs a box. Variants: default (accent rule), `is-good`, `is-warning`, `is-critical`.

```html
<div class="rp-callout is-warning">
  <p class="rp-callout__title">Latency regressed after the Thursday deploy</p>
  <p>The p99 rose by 11 ms. The cause is the new retry policy. A fix is in review.</p>
</div>
```

## Key–value list

Metadata: window, environment, version, owner.

```html
<dl class="rp-kv">
  <dt>Window</dt><dd>2026-09-08 to 2026-09-14</dd>
  <dt>Environment</dt><dd>production, eu-west-1</dd>
</dl>
```

## Card

A generic surface for prose that should sit apart from the flow.

```html
<div class="rp-card">
  <h3>Method</h3>
  <p>…</p>
</div>
```

## Code

```html
<pre><code>glab api projects/42/pipelines</code></pre>
```

## Footer

Already in the template. It repeats the date and author. Add a link to the source data or the repo if one exists.
