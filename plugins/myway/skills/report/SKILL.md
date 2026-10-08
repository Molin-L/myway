---
name: report
description: Generate a self-contained HTML report in the house reading style — one template with a centred serif title, roman-numbered sections, an "On this page" outline on the right built from the h2/h3 headings, a fixed component vocabulary (lede, stats, callouts, timeline, cards, decisions, footnotes), KaTeX math, Vega-Lite charts themed from the tokens, and issue/MR/work-item references (#12, !34, ~56) linked to the forge. Every claim stands on a fact with a source the reader can check, and the prose is plain (no machine-prose tells); the lint checks both. Every library is inlined, so a report works offline and in a private network. Use when the user says "report", "html report", "write this up as a page", "make a dashboard page", "generate a report from this data", or wants results, benchmarks, an audit, or a weekly summary as a shareable HTML file. Do NOT use for a Markdown summary in chat, for slides, or for weekly goals on GitLab (that is `weekly-goal`).
---

# Report

A report is one HTML file. It comes from `templates/report.html`, which carries the house style (the reading page of the research workspace, adapted from numbers.sfinterface.com): a translucent top bar with a serif brand, a centred 644px column with a serif title, roman numerals on every section, an "On this page" outline on the right with a sliding pill, and a runtime that renders math, footnotes, forge references, and Vega-Lite charts. Inter, KaTeX, and Vega are vendored in this skill and inlined into the file, so a report loads nothing from the network. The author writes the body from the component vocabulary and supplies the data. The style is not a choice, and neither is the writing: every claim stands on a fact the reader can check, said in plain words.

Paths are relative to this skill directory. Under Claude Code that is `${CLAUDE_PLUGIN_ROOT}/skills/report/`.

| File | Contents |
|---|---|
| `scripts/report.py` | `new` scaffolds a report, `bundle` inlines the libraries it needs, `lint` checks one, `tokens` lists the tokens |
| `scripts/vendor.sh` | Re-fetches `vendor/` at pinned versions; run only to upgrade a library |
| `vendor/` | Vega, Vega-Lite, vega-embed, KaTeX (with its woff2 fonts), and Inter, with their licenses and `VERSIONS` |
| `templates/report.html` | The template: tokens and styles (`#sf-style`), the forge reference config, the vendor region, top bar, header, body, outline, runtime (`#sf-runtime`), an example body |
| [references/house-style.md](references/house-style.md) | Tokens, type, layout, the outline, what may not change |
| [references/components.md](references/components.md) | The body vocabulary: headings, lede, stats, callout, badge, timeline, cards, equation, figure, table, quote, facts, meter, steps, decision, footnotes, forge references |
| [references/charts.md](references/charts.md) | Vega-Lite rules, form choice, reference lines, missing data, figure requirements |
| [references/writing.md](references/writing.md) | Rooting every claim in a fact (the fact sheet, the four kinds of claim, explaining a number, unknowns, the Method section) and the plain-prose rules |

## The arc

### 1. Gather

Settle these before you write. Ask only for what the request and the workspace do not give you.

- **Title, kicker, project, author, date.** The kicker is the word above the title (default `Report`; `Benchmark`, `Audit`, `Weekly`). The project is the name in the top bar (default: the git repo's directory). Date defaults to today, author to `git config user.name`.
- **Forge.** References link to the git remote `origin` (github.com links `#12` to issues; any other host is treated as GitLab: `#12` issue, `!34` merge request, `~56` work item). If the report is written outside the repo it talks about, or `origin` is not the project the references mean, pass `--refs-base <project URL>`.
- **Output path.** Default `reports/<yyyy-mm-dd>-<slug>.html` in the current repo, or the path the user named.
- **Sections.** As many as the content needs; the outline holds them all. The lede and the stat row state the findings before any section. A topic with parts gets `h3` sub-topics under its `h2`, not more sections.
- **Data.** Where it is, and what each figure should say. If a number has to be computed, compute it now and keep the source at hand for the captions.
- **The fact sheet.** List every claim the report will make, with its value, its source (a command or query with its window, a `file:line`, a commit, `#12`, a URL), and its kind: measured, cited, derived, or judgment. Read each number from the system now; never write one from memory or estimate it. Explain each measured number before you use it: what bounds it, and what else it could be measuring. A claim with no source is cut or marked unverified. See [references/writing.md](references/writing.md#root-every-claim-in-a-fact).

### 2. Scaffold

```sh
scripts/report.py new <out.html> --title "<title>" [--kicker K] [--project P] [--author A] [--date YYYY-MM-DD] \
    [--refs-base https://gitlab.example.com/group/repo] [--forge auto|gitlab|github|none]
```

The result has the style, the reference config, the inlined Inter font, the top bar, the header, an empty body between `<!-- BODY:BEGIN -->` and `<!-- BODY:END -->`, the outline, and the runtime. Use `--with-example` only to show the user the style before content exists; the example uses every component once.

### 3. Write the body

Replace the comment between the BODY markers with an HTML fragment written in [references/components.md](references/components.md), in the prose of [references/writing.md](references/writing.md). Rules:

- Open with `p.sf-lede` (the findings in one paragraph), then usually `div.sf-stats` (three to five numbers the report backs). Every number in the opening appears again lower in the page with its source.
- Show each claim the way its kind needs: a measured value with its window, sample, and source; a cited one with a footnote, forge reference, or exact quote; a derived one with its formula; a judgment worded as yours, naming the facts it weighs.
- Say what is unknown once, in its own sentence, instead of hedging every sentence.
- Close with an `h2` Method section: window and time zone, environment, each source with the query or command that read it, run counts, and what the report did not measure.
- `h2` for sections, `h3` for sub-topics. The page numbers the `h2`s (I, II, III) and builds the outline from both, so never number a heading yourself and never write an `h1` (the header has it). Give an `h3` a short `id` when a link to it must stay stable.
- Tone is emphasis: `data-tone="accent|positive|caution|negative"`, most blocks neutral.
- No inline `style`, no `<style>`, no executable `<script>`, no colour anywhere in the body. Charts are JSON specs, not scripts.
- Escape `&`, `<`, `>` in text, including inside math (`\(a &lt; b\)`). Math is `\( \)` inline and `\[ \]` display; never `$`.
- Cite issues, merge requests, pull requests, and work items as `#12`, `!34`, `~56`, or `group/project#12` in plain text; the page links them. Do not wrap them in `<a>` yourself, and put `data-noref` on an element whose `#1` is not a reference (`Ranked <span data-noref>#1</span>`).
- Prose follows [references/writing.md](references/writing.md#write-it-plainly): the answer first, sentence-case headings that carry the point, the plain word, active voice, one idea per sentence, no em dashes, no machine-prose vocabulary, no vague attributions.

### 4. Add the figures

A figure must stand on its own, with no help from the prose. The full requirements are in [references/charts.md](references/charts.md#figure-requirements). For each chart:

- `figure.sf-figure` with an `id`, holding `div.sf-chart` with a `<script type="application/json">` Vega-Lite v5 spec, and a `figcaption`.
- The caption: `<strong>Figure N.</strong>`, then the finding as a sentence, then the quantity, window with time zone, and sample (`n = 7 days`), then `Data:` and the source.
- Axis titles in the spec: quantity and unit in parentheses on every quantitative axis (`"Latency (ms)"`), resolution and zone on a time axis (`"Day (UTC)"`).
- Data inline as `values`. No colours, fonts, or `config`: the page themes every chart.
- A missing value is `null`, never a zero and never a dropped row; the line leaves a gap, and the caption says how many are missing and why.
- A target or SLO is a `rule` layer plus a `text` layer that names it.

Pick the form from the table in [references/charts.md](references/charts.md). One message per figure. One y axis. One unit per quantity across the report. At most eight series, in the same order across the report. A figure with many values also gets a table, with the unit in the column header.

### 5. Read it back

Read the body as the reader, then as a checker ([references/writing.md](references/writing.md#read-it-back)): every lede sentence and every stat maps to a fact-sheet row and to the place in the page that shows its source; every judgment reads as one; the headings alone tell the story.

### 6. Bundle and lint

```sh
scripts/report.py bundle <out.html>
scripts/report.py lint <out.html>
```

`bundle` inlines what the body uses: Inter always (about 240 KB in all), KaTeX when it has math (+550 KB), Vega when it has charts (+800 KB). Re-run it whenever math or charts are added or removed; it is idempotent.

Fix every error. Read every warning and act on it or say why not. The lint checks that the style block and the runtime match the template, that the inlined libraries match what the body needs, the reference config, the shell (top bar, outline, body), placeholders and example markers, any remote resource (none is allowed, images included), styles and scripts in the body, ids, heading levels and hand numbering, tone and step values, decisions with more than one recommended option, figure captions and numbering and sources, every chart spec (valid JSON, inline data, no colours or config, axis titles with units, labelled reference lines, "Illustrative" on generated data), footnote markers against the footnote list, references that will not link because the config has no template for them, stats whose number appears nowhere else in the body, title-case headings, and the prose patterns of [references/writing.md](references/writing.md) (machine-prose words, filler, fancy "is", vague attributions, "not just X, but Y", abstract metaphors, chatbot phrases, stacked hedges, em dashes). Prose checks skip code, quotes, and the source list. A prose warning is fixed by rewriting the sentence, not by swapping one tell for its synonym.

### 7. Look at it

Open the file in a browser if one is available, or screenshot it with headless Chrome (`--virtual-time-budget=15000` so the charts finish drawing; add `--host-resolver-rules="MAP * ~NOTFOUND"` to prove it works with no network). Check: every chart drew (no red error text), legends on multi-series charts, no label collisions, math rendered, footnote markers and references linked to the right forge. Check the outline at a wide window and at a narrow one (below 1180px it becomes a drawer behind the "Contents" button): every `h2` and `h3` is there and the pill follows the scroll. Read each figure with the prose hidden; if you cannot tell the unit, the window, or the sample, fix it. Headless Chrome will not go below a 500px viewport, so a narrower screenshot looks clipped when it is not. If no browser is available, say so in the report to the user.

### 8. Report

Give the user the path, the section list, and the figures with one line each on what they show. Name the claims that are judgment rather than measurement, and any claim you could not verify. Mention anything the lint warned about that you left in place.

## Rules

- **No claim without a fact.** Every number and every statement of fact in the body has a source the reader can open or re-run. Judgment is labelled as judgment. Illustrative data says so and never reaches the opening.

- **Never edit `#sf-style` or `#sf-runtime` in a report.** A new need is a template change in this skill (and in the theory reading page, which shares the style), then a re-scaffold.
- **Never hand-write the outline or number a heading.** The runtime builds both from the `h2` and `h3` headings.
- **Nothing loads from the network.** Data lives in the specs, libraries are inlined by `bundle`, and images are data URIs or inline `<svg>`. A report must open in a private network.
- **Never colour anything yourself.** Series take the palette in order; tone takes the four tone words; a status needs a word beside its colour (a badge does this).
- **Light only.** The house style has no dark theme and no toggle.
