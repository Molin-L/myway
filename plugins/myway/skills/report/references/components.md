# Components

The report body, between `<!-- BODY:BEGIN -->` and `<!-- BODY:END -->`, is an **HTML fragment**: no `<h1>`, `<style>`, inline `style=""`, or executable `<script>`. The template supplies all styling. Use only the elements and classes below; if the report needs something this list cannot express, use plain prose or a table, and tell the user which component was missing so it can be added to the template.

This is the same vocabulary as the research workspace's `components.md`, minus its research-only wiring (review answers, citation checking). `report.py new --with-example` renders every component once.

## Page structure

- No `<h1>`: the header shows the title.
- `<h2>` for sections. The page numbers them (I, II, III) and lists them in the outline, so never number headings yourself.
- `<h3>` for sub-topics, also in the outline. An `<h4>` is a small uppercase label, not in the outline; use it sparingly. No `<h5>`/`<h6>`, and no heading inside a component.
- Prose: `<p>`, `<ul>`, `<ol>`, `<strong>`, `<em>`, `<a href>`, `<code>`, `<pre>`, `<blockquote>`, `<hr>`, and `<table>` with `<thead>`/`<tbody>` (the page styles tables and wraps code).
- Escape `&`, `<` and `>` in text as `&amp;`, `&lt;`, `&gt;`, including inside `\( \)` and `\[ \]` math: a bare `<` starts an HTML tag before KaTeX sees it.

## Tones

Components that take `data-tone` accept `accent` (blue: key idea, current), `positive` (green: recommended, healthy, good change), `caution` (amber: risk, degraded, needs a decision), `negative` (red: refuted, blocker, bad change). Omit it for neutral. Tone is emphasis, so most blocks should be neutral. The lint rejects any other value.

## Lede and stats: the opening

```html
<p class="sf-lede">One paragraph that tells the reader what this report concludes.</p>
<div class="sf-stats">
  <p class="sf-stat"><span class="sf-stat-value">1.28M</span><span class="sf-stat-label">requests served</span><span class="sf-stat-delta" data-tone="positive">+4.2% vs last week</span></p>
  <p class="sf-stat"><span class="sf-stat-value">184 ms</span><span class="sf-stat-label">p99 latency</span><span class="sf-stat-delta" data-tone="negative">+11 ms vs last week</span></p>
</div>
```

Three to five stats, each a number the report backs. Compact values by hand (`1,284` / `12.9K` / `$4.2M`) and keep the unit in the value. `sf-stat-delta` is optional; it names the period it compares against, and its tone says whether the change is good (`positive`) or bad (`negative`), whichever way the number moved. A delta with no tone reads as neutral (`no change`).

## Callout: a key finding, caveat, or risk

```html
<aside class="sf-callout" data-tone="caution">
  <p class="sf-label">Regression</p>
  <p>The p99 rose by 11 ms after the Thursday deploy.</p>
</aside>
```

## Badge and tags

```html
<span class="sf-badge" data-tone="positive">healthy</span>
<ul class="sf-tags"><li>deploy</li><li>latency</li></ul>
```

A badge is a short status word, the house status pill: colour plus a word, never colour alone. Tags classify a card.

## Table

```html
<table>
  <thead><tr><th>Service</th><th>Status</th><th class="num">Requests</th><th class="num">p99 (ms)</th></tr></thead>
  <tbody>
    <tr><td>gateway</td><td><span class="sf-badge" data-tone="positive">healthy</span></td><td class="num">1,284,001</td><td class="num">184</td></tr>
  </tbody>
</table>
```

`class="num"` right-aligns a numeric column with tabular figures; put it on the `th` and every `td` of the column. The unit goes in the header. A table is also the accessible fallback for a chart.

## Timeline: dated history

```html
<ol class="sf-timeline">
  <li data-tone="accent">
    <time>Thu</time>
    <div>
      <p><strong>Feed adapter 4.2 deployed</strong></p>
      <p>One or two sentences: what changed, and why it mattered.</p>
    </div>
  </li>
</ol>
```

Oldest first. Put `data-tone="accent"` on the few turning points only.

## Cards

```html
<div class="sf-cards">
  <article class="sf-card">
    <p class="sf-card-title">Retry budget fix</p>
    <p>One or two sentences.</p>
    <ul class="sf-tags"><li>fix</li></ul>
  </article>
</div>
```

Cards always sit inside `sf-cards` (a two-column grid). For a paper or other published work, use the paper card:

```html
<article class="sf-paper">
  <p class="sf-paper-meta"><span>2011</span><span>Tóth, Lemperière, Deremble et al.</span></p>
  <p class="sf-paper-title"><a href="https://arxiv.org/abs/1105.1694">Full title</a></p>
  <p class="sf-paper-venue">Venue</p>
  <p>Its contribution in one or two sentences.</p>
</article>
```

## Facts: key/value pairs

```html
<dl class="sf-facts"><dt>Window</dt><dd>2026-09-07 to 2026-09-13, UTC</dd><dt>Environment</dt><dd>production, eu-west-1</dd></dl>
```

For metadata (window, environment, version, owner), on its own or inside a card or numbered block.

## Equation

```html
<figure class="sf-equation" data-label="1">
  \[ B = (1 - o)\,N \]
  <figcaption>\(o\): the availability objective; \(N\): requests in the window.</figcaption>
</figure>
```

Math is KaTeX: `\[ ... \]` for display and `\( ... \)` inline, anywhere in the body. Never `$`, since prices use it. `data-label` and `<figcaption>` are optional.

## Figure and chart

```html
<figure class="sf-figure" id="fig-requests">
  <div class="sf-chart"><script type="application/json">
  {"data": {"values": [{"day": "Mon", "requests": 212}, {"day": "Tue", "requests": 231}]},
   "mark": "bar",
   "encoding": {
     "x": {"field": "day", "type": "ordinal", "sort": null, "title": "Day of week (UTC)"},
     "y": {"field": "requests", "type": "quantitative", "title": "Requests (thousands)"}}}
  </script></div>
  <figcaption><strong>Figure 1.</strong> Weekend traffic is half the weekday level. Requests per day, 2026-09-07 to 2026-09-13, UTC; n = 7 days. Data: gateway access logs.</figcaption>
</figure>
```

The spec is Vega-Lite v5 JSON; [charts.md](charts.md) has the rules. An image or inline `<svg>` can go in `sf-figure` instead of a chart, with the same caption. Two charts never share a figure.

## Quotation: a source's exact words

```html
<blockquote class="sf-quote"><p>Exact words from the source.</p><cite>Incident review 2026-09-12, §4</cite></blockquote>
```

Inline, use `<q>exact words</q>`. Never paraphrase inside either; use `...` for an omission.

## Meter: a 0–5 score

```html
<span class="sf-meter" data-value="4" aria-label="4 of 5"></span>
```

Mainly in table cells. Always keep the `aria-label`.

## Steps: a plan

```html
<ol class="sf-steps">
  <li data-state="done"><p class="sf-step-title">Find the cause</p><p>What it produced.</p></li>
  <li data-state="current"><p class="sf-step-title">Ship the fix</p><p>Where it stands.</p></li>
  <li><p class="sf-step-title">Confirm recovery</p><p>What done means.</p></li>
  <li data-state="skip"><p class="sf-step-title">Backfill</p><p>Why it is skipped.</p></li>
</ol>
```

`data-state` is `done`, `current`, `next` (or omitted), or `skip`.

## Numbered blocks: question, hypothesis, decision

A question to answer, a claim with its test, or a choice for the reader. Each has an `id` and an `sf-id` label.

```html
<div class="sf-hypothesis" id="h1">
  <p class="sf-head"><span class="sf-id">H1</span>The claim, stated so it can fail.</p>
  <dl class="sf-facts"><dt>Test</dt><dd>…</dd><dt>Pass if</dt><dd>…</dd><dt>Fail if</dt><dd>…</dd></dl>
</div>

<div class="sf-decision" id="d1">
  <p class="sf-head"><span class="sf-id">D1</span>The question for the reader?</p>
  <p>What depends on this choice.</p>
  <ul class="sf-options">
    <li data-recommended><strong>Option A</strong>: consequence.</li>
    <li><strong>Option B</strong>: consequence.</li>
  </ul>
</div>
```

Questions are `<ol class="sf-questions">` of `<li class="sf-question" id="q1">` with the same `sf-head` and an optional badge at the end of the head. In a decision, mark at most one option `data-recommended` (the lint fails on two). For a decision already taken, mark the chosen option `data-chosen` and end it with `<span class="sf-badge" data-tone="accent">Chosen</span>`.

## Footnotes

Cite with `[^n]` in the text; the page turns each marker into a link. End the body with:

```html
<section class="footnotes">
<ol class="footnotes-list">
<li id="fn1" class="footnote-item"><a href="URL">Title</a></li>
</ol>
</section>
```

Items are numbered by position, so item `n` must have `id="fn{n}"` and appear in order. The page heads the list "Sources" and adds it to the outline. The lint fails on a marker with no item and warns on an item never cited.
