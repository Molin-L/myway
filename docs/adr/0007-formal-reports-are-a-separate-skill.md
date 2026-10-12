# Formal reports are a separate skill

ADR 0003 moved the `report` skill to the research reading style, and ADRs 0004
and 0005 added inlined libraries, fact sheets, and prose lint on top. The
result suits a record or a page shared outside the team, but it is heavy for
the everyday case: a quick write-up of a page read, a benchmark, or a weekly
summary. In use, the earlier house style (system sans, a floating left outline
with three heading levels, a light/dark toggle, stat tiles, D3 charts) read
more clearly for that case.

We decided that **there are two report skills.** `report` is the house style
again, restored as it was at `15cddbe` (v0.4.0). `formal-report` is the
research reading style with everything ADRs 0003 to 0005 describe, moved
unchanged from `report` apart from its name and description.

## Consequences

- `/report` gives the house-style page: light and dark, a left outline down to
  `h4`, D3 from its CDN, and the lint of ADR 0002.
- `/formal-report` gives the reading-style page: light only, Vega-Lite and
  KaTeX inlined, claims on sourced facts, a Method section, and the prose lint.
- The descriptions point at each other, so a plain "report" goes to `report`
  and a "formal report" or a request for the reading style goes to
  `formal-report`.
- ADRs 0003, 0004, and 0005 now apply to `formal-report`. ADR 0002 applies to
  `report` in full again, dark theme included.
- `bench` hands its results to `formal-report`, because its write-up needs the
  Method section and the session manifests that skill asks for.
- A change to the shared figure rules (axis units, numbered captions, labelled
  reference lines, `null` for missing data) is made in both skills.
- Reports made with `report` between v0.5.0 and this change are reading-style
  files; they pass `formal-report`'s lint and need no change.
