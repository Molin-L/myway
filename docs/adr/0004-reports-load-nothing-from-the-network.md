# Reports load nothing from the network

Reports are read inside private networks where public CDNs are unreachable,
and often blackholed rather than refused. A blackholed CDN is worse than a
missing one: the Google Fonts stylesheet blocks rendering and deferred KaTeX
scripts hold back `DOMContentLoaded`, so the outline and the charts wait for a
TCP timeout before they appear, and the charts then fail outright.

We decided that **a report is self-contained down to its libraries.** Vega,
Vega-Lite, vega-embed, KaTeX with its woff2 fonts, and the Inter font are
vendored in `plugins/myway/skills/report/vendor/` at pinned versions
(`scripts/vendor.sh` fetches them), and `report.py bundle` inlines into each
report what its body uses: Inter always, KaTeX when there is math, Vega when
there are charts.

## Consequences

- A report opens with no network at all. The lint fails on any remote `src`
  or `href`, images included.
- Files grow: about 240 KB with no math or charts, about 1.7 MB with both.
  Inlining only what the body uses keeps prose-only reports small.
- The vendor region must match the body; the lint fails when a chart or math
  is added without re-running `bundle`.
- Upgrading a library is `scripts/vendor.sh` with new pins, a commit of
  `vendor/`, and a re-bundle of the reports that should pick it up.
- Inter is the latin subset only; other scripts fall back to the system font
  glyph by glyph.
- The theory reading page still loads from CDNs; it runs on the author's
  machine, not in the private network.
