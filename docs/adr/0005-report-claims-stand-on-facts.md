# Report claims stand on facts, in plain prose

A report is read once by someone who will act on it. Generated reports had two
failure modes the style checks could not see: numbers in the lede and the stat
row that nothing lower in the page backed, and prose with the tells of machine
writing (pivotal, robust, delve, em dashes, "experts agree", "not just X, but
Y"). Both cost the reader's trust, and the second costs their time.

We decided that **every claim in a report stands on a fact the reader can
check, and the prose says it plainly.** `references/writing.md` sets the rules.
The fact rules adapt `principle-explain-the-number`, and the prose rules adapt
`unslop` and `technical-writing`, from
[pstack](https://github.com/backnotprop/pstack) (MIT).

## Consequences

- The author builds a fact sheet in the Gather step: claim, value, source,
  kind (measured, cited, derived, judgment). It stays in the working notes.
- Every report closes with a Method section: window, environment, sources with
  their queries, run counts, and what was not measured.
- `report.py lint` warns on a stat whose number appears nowhere else in the
  body, on title-case headings, and on the prose patterns a regex can find.
  These are warnings, not errors: a quoted source or a product name may
  legitimately trip them, and the author says why it stays.
- Prose checks skip code, quotes, and the source list, so a source's exact
  words are never rewritten.
- A pattern a regex cannot find (an "-ing" tail, a forced group of three,
  synonym cycling) is left to the read-back step.
