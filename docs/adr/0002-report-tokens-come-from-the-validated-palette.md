# Report colours are tokens from one validated palette

Reports that share a look need the same colours, the same type, and the same
chart marks in every file, in both light and dark mode. Left to each report,
colours drift: a chart picks its own hex, dark mode becomes an inverted light
mode, and the fourth series lands on a hue a colour-blind reader cannot tell
from the third.

We decided that **the `report` skill's template carries one token block, and
that block is the only place a colour literal may appear.** The values are the
validated dataviz palette: eight categorical slots in a fixed order that clear
the colour-vision floors in both modes, a sequential ramp, a diverging pair,
a reserved status set, and the ink and plane roles. Light and dark are both
selected values. Charts set colour through `var(--token)`, never through a
hex, so a theme toggle re-colours every mark with no redraw.

## Consequences

- A report author writes sections and data, not style. `report.py lint`
  fails on a colour literal outside the token block.
- A new colour need is a template change in the skill, with both themes
  stepped and the palette re-validated, not a per-report tweak.
- A theme toggle is cheap: one attribute on `<html>`, no chart redraw, no
  duplicate chart code per theme.
- The series order is fixed and meaningful. A ninth series has no slot; it
  folds into "Other" or the chart becomes small multiples.
- Swapping the house palette later is one block in one file, plus a re-run of
  the validator. Nothing in the reports changes.
