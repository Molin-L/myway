# Writing

A report is a set of claims a reader will act on. Two rules carry it: every claim stands on a fact the reader can check, and the prose says that fact in plain words. The first part of this file is about the facts, the second about the words.

The tone rules adapt the `unslop` and `technical-writing` skills, and the number rules adapt `principle-explain-the-number`, all from [pstack](https://github.com/backnotprop/pstack) (MIT, Lauren Tan). `report.py lint` checks the patterns a script can find and warns on each one.

## Root every claim in a fact

### Build the fact sheet first

Before you write a sentence, list what the report will claim. Keep the list in your working notes, not in the report. One row per claim:

| Claim | Value | Source | Kind |
|---|---|---|---|
| p99 rose after the Thursday deploy | 173 ms to 190 ms | `promql: histogram_quantile(0.99, …)`, 2026-09-07 to 09-13 UTC | measured |
| The retry policy causes it | bisect lands on !482 | `git bisect` log, load test run 3 of 3 | measured |
| Keep 4.2 rather than roll back | | weighs D1's two options | judgment |

A source is something the reader could open or re-run: a command or query with its window, a `file:line`, a commit, an issue or merge request, a dashboard URL, a document with its section. "The logs" is not a source. "Gateway access logs, 2026-09-07 to 09-13 UTC" is.

Write only the claims that have a row. A claim with no source is either cut, or moved to a section that says it is unverified.

### Four kinds of claim, each shown its own way

| Kind | What it is | How the page shows it |
|---|---|---|
| Measured | A number or state you read from a system | The value, the window with time zone, the sample (`n = 7 days`), and the source: in a figure caption, a table, a `sf-facts` list, or a footnote |
| Cited | Someone else's statement or result | A footnote `[^n]` to the document, a forge reference (`#12`, `!34`), or the exact words in `sf-quote` or `<q>` |
| Derived | Computed from other facts | The formula (an `sf-equation` or one sentence) and the inputs, each of which is itself measured or cited |
| Judgment | Your recommendation or reading of the facts | Said as yours, in a decision, a callout, or a sentence that starts from the facts it weighs ("Because the budget lands within days, keep 4.2.") |

Judgment is welcome. Hiding it is not. Never write a judgment in the grammar of a measurement ("the rollback is too risky") when you mean "we judge the rollback too risky because …".

### Explain the number before you print it

A run that went wrong still prints a plausible number. Before a number goes in the lede, a stat, or a figure:

- **Ask why it is not twice as good, or half.** Name what bounds it: a core, a lock, the disk, the network, the load generator, the sample size. If you cannot name it, say the limit is unknown.
- **Rule out that it measured something else.** The usual suspects are failed requests counted as fast ones, cached or skipped work, a side left on default settings, a window that includes a deploy or an outage, and run-to-run noise. Say in the method which ones you checked.
- **Keep the evidence with the number.** The run count and the spread go next to a measured result (`median of 5 runs, range 181 to 192 ms`). One run is one run; say so.
- **Compare like with like.** Same window length, same environment, same percentile, same unit. A delta names what it is against (`+11 ms vs last week`).

### Say what is unknown, once and plainly

A gap in the data is a fact too. Write it as one: "Wednesday has no data: the metrics scrape failed from 00:00 to 23:59 UTC." Do not spread doubt across every sentence with "may", "might", "potentially", and "seems". State what you know without hedging, and state what you do not know in its own sentence. A missing chart value is `null` and the caption counts it ([charts.md](charts.md#missing-data)).

### The opening carries only proven claims

The lede and the stat row are what most readers will read. Every number in them must appear again lower in the page, in a section, table, figure, or footnote that shows where it comes from. `report.py lint` warns on a stat whose number appears nowhere else in the body. A compacted stat (`1.28M`) is backed by the full figure (`1,284,001`) in a table.

### Close with a Method section

End the body, before the footnotes, with an `h2` Method section: the window and time zone, the environment, every data source with the query or command that read it, the run count, and what the report did not measure. A reader who doubts a number starts here.

### Illustrative data is labelled

Data you made up to show a shape, not to report a result, says "Illustrative" in its caption and never reaches the lede or the stats.

## Write it plainly

The reader is a busy engineer or manager reading once. Each rule below removes something that makes them work harder or trust the page less.

### Put the answer first

- The lede states the findings and the decision needed, in that order. No preamble ("This report examines …").
- A heading carries the point, not just the topic, when the section has one point: "p99 rose after the Thursday deploy", not "Latency". A heading over a reference section (Method, Services) stays a noun.
- Headings are in sentence case: "What changed", not "What Changed".
- The first sentence of each section is that section's conclusion. The evidence follows.

### Say what it does, with the number

- Name the mechanism or the measurement, not a feeling. Not "latency was significantly impacted" but "p99 rose 17 ms, from 173 ms to 190 ms".
- Cut an adverb that props up a weak verb. "Improved significantly" becomes the delta.
- If a sentence could appear unchanged in another team's report, it says nothing about this one. Cut it.
- No generic conclusions. "The outlook is positive" becomes the next step and its date.

### Use the plain word

| Write | Not |
|---|---|
| use | utilize, leverage |
| help | facilitate |
| many | numerous |
| is, has | serves as, stands as, boasts, features |
| to | in order to |
| because | due to the fact that |
| if | in the event that |
| (nothing) | it is important to note that, it is worth noting that |
| base, way, goal | substrate, vector, north star, paradigm, landscape |

Avoid the words that mark machine prose: additionally, crucial, delve, enduring, enhance, foster, garner, interplay, intricate, pivotal, robust, seamless, showcase, tapestry, testament, underscore, vibrant. Each has a plainer word, or the sentence did not need it.

### One idea per sentence, active voice

- Split a sentence the reader has to read twice. About 25 words is the limit.
- Name who did it: "the adapter retries the call", not "the call is retried". Passive is fine only when the actor is unknown or does not matter.
- Write whole sentences, with articles and verbs. "Parser rejects bad date → exit 2" becomes "The parser rejects a bad date and exits with code 2."
- Call one thing by one name throughout. If it is "the feed adapter" in the lede, it is not "the ingest service" in section III.
- Make every "it", "this", and "they" point at one obvious noun. Repeat the noun when in doubt.

### Drop the tells

- No em dashes. End the sentence, or use a comma.
- Colons only before a list, an example, or a label (`Data:`). Not as a hinge in the middle of a sentence.
- No "not just X, but Y". State Y.
- No forced groups of three. Use the number of items there are.
- No vague attributions ("experts say", "studies show", "it is widely known"). Name the source with a footnote, or cut the claim.
- No "-ing" tails that pretend to add meaning ("…, highlighting the need for…", "…, ensuring stability").
- No chatbot phrases in a report: "I hope this helps", "Let me know if", "Great question", "Certainly".
- Bold only a lead-in or the one phrase a reader must not miss, never every term.
- No emoji in headings, labels, or lists.

### Vary the rhythm

Rules applied blindly produce clipped, sterile prose. Mix short sentences that land a point with longer ones that carry a fact with its condition. Where the report weighs a decision, have a view and say it. When a rule makes a sentence worse, fix the sentence another way.

## Before and after

Before:

> This report delves into the latency landscape of the gateway — a pivotal component of our platform. Latency was significantly impacted following the recent deployment, highlighting the crucial need for robust retry handling. Experts agree that retries can potentially cause issues.

After:

> p99 latency rose 10%, from 173 ms to 190 ms, after feed adapter 4.2 deployed on Thursday (Figure 2). The adapter now retries a timed-out upstream call three times, which triples the load on a slow upstream. A retry budget that caps retries at 10% of calls is in review as !497.[^1]

The second version is shorter, names the cause, gives the number with its baseline, and points at the change and the source. Every claim in it has a row in the fact sheet.

## Read it back

Before you bundle, read the body once as the reader and once as a checker:

1. For each sentence in the lede and each stat, find its row in the fact sheet and the place lower in the page that shows the source. No row, no sentence.
2. For each judgment, check that it is worded as one and names the facts it weighs.
3. Run `report.py lint` and read every prose warning. Rewrite the sentence, or keep it and say why in your note to the user (a quoted source, a product name).
4. Read the headings alone, in order. They should tell the story of the report.
