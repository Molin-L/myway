#!/usr/bin/env bash
# Fetch the libraries a report inlines (Vega, KaTeX, Inter) into ../vendor/, at pinned versions.
# Reports never load them from a CDN: `report.py bundle` inlines them, so a report works offline
# and in a private network. Re-run only to upgrade; then commit vendor/ and re-bundle the reports.
# curl honours https_proxy / HTTPS_PROXY if the network needs one.
set -euo pipefail

VEGA=5.30.0
VEGA_LITE=5.21.0
VEGA_EMBED=6.26.0
KATEX=0.16.22
INTER=5.3.0   # @fontsource-variable/inter

CDN=https://cdn.jsdelivr.net/npm
OUT="$(cd "$(dirname "$0")/.." && pwd)/vendor"

fetch() {  # fetch <url> <dest>
  mkdir -p "$(dirname "$2")"
  curl -fsSL --retry 2 -o "$2" "$1"
  echo "  $2" | sed "s#$OUT/##"
}

rm -rf "$OUT"
echo "vendor/:"
fetch "$CDN/vega@$VEGA/build/vega.min.js" "$OUT/vega/vega.min.js"
fetch "$CDN/vega-lite@$VEGA_LITE/build/vega-lite.min.js" "$OUT/vega/vega-lite.min.js"
fetch "$CDN/vega-embed@$VEGA_EMBED/build/vega-embed.min.js" "$OUT/vega/vega-embed.min.js"
fetch "$CDN/vega@$VEGA/LICENSE" "$OUT/vega/LICENSE"

fetch "$CDN/katex@$KATEX/dist/katex.min.js" "$OUT/katex/katex.min.js"
fetch "$CDN/katex@$KATEX/dist/contrib/auto-render.min.js" "$OUT/katex/auto-render.min.js"
fetch "$CDN/katex@$KATEX/dist/katex.min.css" "$OUT/katex/katex.min.css"
fetch "$CDN/katex@$KATEX/LICENSE" "$OUT/katex/LICENSE"
# Only the woff2 fonts: `report.py bundle` rewrites the stylesheet to use them as data URIs.
for font in $(grep -o 'fonts/KaTeX_[A-Za-z0-9_-]*\.woff2' "$OUT/katex/katex.min.css" | sort -u); do
  fetch "$CDN/katex@$KATEX/dist/$font" "$OUT/katex/$font"
done

for style in normal italic; do
  fetch "$CDN/@fontsource-variable/inter@$INTER/files/inter-latin-opsz-$style.woff2" "$OUT/inter/inter-latin-opsz-$style.woff2"
done
fetch "$CDN/@fontsource-variable/inter@$INTER/LICENSE" "$OUT/inter/LICENSE"

cat > "$OUT/VERSIONS" <<EOF
vega $VEGA
vega-lite $VEGA_LITE
vega-embed $VEGA_EMBED
katex $KATEX
@fontsource-variable/inter $INTER (latin subset, opsz + wght axes)
EOF
echo "  VERSIONS"
