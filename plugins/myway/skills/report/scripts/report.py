#!/usr/bin/env python3
"""Scaffold and lint house-style HTML reports. Standard library only.

Subcommands:
  new OUT.html --title T [--kicker K] [--project P] [--author A]
               [--date YYYY-MM-DD] [--forge F] [--refs-base URL]
               [--with-example] [--force]
      Copy templates/report.html to OUT.html with the placeholders filled,
      then bundle it. The forge references (#12, !34, ~56) link to the git
      remote `origin` unless --refs-base names the project URL. The example
      body is dropped unless --with-example is given. Refuses to overwrite
      unless --force.

  bundle FILE.html
      Inline the vendored libraries the body needs into the VENDOR region:
      Inter always, KaTeX when the body has math, Vega when it has charts.
      Run it after writing the body; it is idempotent.

  lint FILE.html
      Check that FILE.html still follows the house style. Exit 1 on any
      error. Warnings do not change the exit code.

  tokens
      Print the token names the template defines (for reference).
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "templates", "report.html")

EXAMPLE_RE = re.compile(r"<!-- EXAMPLE:BEGIN.*?<!-- EXAMPLE:END -->\n?", re.S)
BODY_RE = re.compile(r"<!-- BODY:BEGIN -->(.*?)<!-- BODY:END -->", re.S)
BODY_EMPTY = "<!-- BODY:BEGIN -->\n<!-- the report body goes here: <p class=\"sf-lede\">, <h2>, <h3>, and the components in references/components.md -->\n<!-- BODY:END -->"
STYLE_RE = re.compile(r'<style id="sf-style">.*?</style>', re.S)
RUNTIME_RE = re.compile(r'<script id="sf-runtime">.*?</script>', re.S)

VENDOR = os.path.join(HERE, "..", "vendor")
VENDOR_RE = re.compile(r"<!-- VENDOR:BEGIN -->.*?<!-- VENDOR:END -->", re.S)

# A forge reference in prose: #12, !34, ~56, or group/project#12. Kept in step with linkRefs() in the runtime.
REF_RE = re.compile(r"(?:^|(?<=[\s(\[{,;:]))((?:[\w.-]+(?:/[\w.-]+)+)?)([#!~])(\d+)(?![\w-])")
REF_TEMPLATES = {
    "gitlab": {"#": "{base}/{project}/-/issues/{id}", "!": "{base}/{project}/-/merge_requests/{id}", "~": "{base}/{project}/-/work_items/{id}"},
    "github": {"#": "{base}/{project}/issues/{id}"},
}
TONES = {"accent", "positive", "caution", "negative"}
STEP_STATES = {"done", "current", "next", "skip"}
MARKS = {"line", "bar", "point", "area", "rule", "text", "tick"}


def read_template() -> str:
    with open(TEMPLATE, encoding="utf-8") as f:
        return f.read()


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=False).stdout.strip()
    except OSError:
        return ""


def default_author() -> str:
    return git("config", "user.name") or os.environ.get("USER", "")


def default_project() -> str:
    top = git("rev-parse", "--show-toplevel")
    return os.path.basename(top or os.getcwd())


# ---------------------------------------------------------------- forge references

def parse_remote(url: str) -> tuple[str, str] | None:
    """Return (web base, project path) for a git remote URL, or None.

    https://host[:port]/group/repo(.git) keeps the scheme and port; an SSH remote
    (git@host:group/repo.git, ssh://git@host:2222/group/repo.git) maps to https://host.
    """
    url = url.strip()
    m = re.match(r"^(https?)://(?:[^@/]+@)?([^/]+)/(.+?)(?:\.git)?/?$", url)
    if m:
        return f"{m.group(1)}://{m.group(2)}", m.group(3)
    m = re.match(r"^(?:ssh://)?(?:[^@/]+@)?([^:/]+)(?::\d+/|:|/)(.+?)(?:\.git)?/?$", url)
    if m:
        return f"https://{m.group(1)}", m.group(2)
    return None


def refs_config(forge: str, refs_base: str | None) -> dict:
    """The JSON for <meta name="sf-refs">: link templates per sigil, with the project filled in."""
    if forge == "none":
        return {}
    parsed = parse_remote(refs_base) if refs_base else parse_remote(git("remote", "get-url", "origin"))
    if not parsed:
        return {}
    base, project = parsed
    if forge == "auto":
        forge = "github" if base.endswith("://github.com") else "gitlab"
    out: dict = {"project": project}
    for sigil, tmpl in REF_TEMPLATES[forge].items():
        out[sigil] = tmpl.replace("{base}", base)
    return out


# ---------------------------------------------------------------- bundle

def vendor_read(rel: str, binary: bool = False):
    with open(os.path.join(VENDOR, rel), "rb" if binary else "r", **({} if binary else {"encoding": "utf-8"})) as f:
        return f.read()


def data_uri(rel: str, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(vendor_read(rel, binary=True)).decode("ascii")


def inline_script(ident: str, *rels: str) -> str:
    parts = []
    for rel in rels:
        src = vendor_read(rel)
        if re.search(r"</script|<!--", src, re.I):
            raise SystemExit(f"vendor/{rel} contains </script or <!--; it cannot be inlined as is")
        parts.append(f"/* vendor/{rel} */\n{src.strip()}")
    return f'<script id="{ident}">\n' + "\n".join(parts) + "\n</script>"


def body_needs(text: str) -> tuple[bool, bool]:
    """(math, charts): what the body uses, ignoring code samples and chart specs."""
    m = BODY_RE.search(text)
    body = m.group(1) if m else ""
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    charts = 'class="sf-chart"' in body
    prose = re.sub(r"<(pre|code|script)\b.*?</\1>", "", body, flags=re.S | re.I)
    math = bool(re.search(r"\\[(\[]", prose))
    return math, charts


def vendor_block(text: str) -> str:
    math, charts = body_needs(text)
    fonts = "".join(
        f"@font-face{{font-family:\"Inter\";font-style:{style};font-display:swap;font-weight:100 900;"
        f"src:url({data_uri(f'inter/inter-latin-opsz-{style}.woff2', 'font/woff2')}) format(\"woff2\");"
        "unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,"
        "U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD}\n"
        for style in ("normal", "italic")
    )
    parts = ['<style id="sf-vendor-fonts">\n/* vendor/inter: Inter, SIL Open Font License 1.1 */\n' + fonts + "</style>"]
    if math:
        css = vendor_read("katex/katex.min.css")
        # Keep only the woff2 source of each KaTeX font, as a data URI.
        css = re.sub(r'src:url\((fonts/[^)]+\.woff2)\) format\("woff2"\)[^;}]*',
                     lambda m: f'src:url({data_uri("katex/" + m.group(1), "font/woff2")}) format("woff2")', css)
        if "url(fonts/" in css:
            raise SystemExit("vendor/katex/katex.min.css still references fonts/ after inlining; re-run scripts/vendor.sh")
        parts.append('<style id="sf-vendor-katex">\n/* vendor/katex: KaTeX, MIT License */\n' + css.strip() + "\n</style>")
        parts.append(inline_script("sf-vendor-katex-js", "katex/katex.min.js", "katex/auto-render.min.js"))
    if charts:
        parts.append(inline_script("sf-vendor-vega", "vega/vega.min.js", "vega/vega-lite.min.js", "vega/vega-embed.min.js"))
    return "<!-- VENDOR:BEGIN -->\n" + "\n".join(parts) + "\n<!-- VENDOR:END -->"


def bundle(text: str) -> str:
    if not VENDOR_RE.search(text):
        raise SystemExit("no VENDOR:BEGIN / VENDOR:END region; re-scaffold the file with `report.py new`")
    block = vendor_block(text)
    return VENDOR_RE.sub(lambda _: block, text, count=1)


def cmd_bundle(a: argparse.Namespace) -> int:
    with open(a.file, encoding="utf-8") as f:
        text = f.read()
    out = bundle(text)
    with open(a.file, "w", encoding="utf-8") as f:
        f.write(out)
    math, charts = body_needs(out)
    print(f"{a.file}: Inter" + (", KaTeX" if math else "") + (", Vega" if charts else "") + f" ({len(out.encode()) // 1024} KB)")
    return 0


# ---------------------------------------------------------------- new

def cmd_new(a: argparse.Namespace) -> int:
    if os.path.exists(a.out) and not a.force:
        print(f"refusing to overwrite {a.out} (use --force)", file=sys.stderr)
        return 1
    text = read_template()
    if not a.with_example:
        text = EXAMPLE_RE.sub("", text)
        text = BODY_RE.sub(lambda _: BODY_EMPTY, text)
    path = os.path.relpath(os.path.abspath(a.out))
    subs = {
        "TITLE": a.title,
        "KICKER": a.kicker,
        "PROJECT": a.project or default_project(),
        "AUTHOR": a.author or default_author(),
        "DATE": a.date or dt.date.today().isoformat(),
        "PATH": path if not path.startswith("..") else os.path.basename(a.out),
        "REFS": json.dumps(refs_config(a.forge, a.refs_base), separators=(",", ":")),
    }
    for k, v in subs.items():
        text = text.replace("{{" + k + "}}", html.escape(v, quote=True))
    text = bundle(text)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(a.out)
    return 0


# ---------------------------------------------------------------- lint

HEX = r"#[0-9a-fA-F]{3,8}\b"
COLOR_FUNC = r"\b(?:rgba?|hsla?|oklch|oklab|color-mix)\("
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")
FOOTNOTE_REF_RE = re.compile(r"\[\^(\d+)\]")


class Lint:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


class Body(HTMLParser):
    """Walk the report body (between the BODY markers) and record what the lint checks.

    A parser, not a regex: `id="…"` inside a code sample or a chart spec is text,
    not an attribute, and must not count.
    """

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self, offset: int) -> None:
        super().__init__(convert_charrefs=True)
        self.base = offset                        # line number of the body's first line, minus one
        self.stack: list[tuple[str, list[str]]] = []
        self.ids: list[tuple[str, int]] = []
        self.headings: list[tuple[int, int, str]] = []   # (level, line, text)
        self.heading: list | None = None
        self.styles: list[int] = []
        self.inline_styles: list[int] = []
        self.scripts: list[int] = []                     # executable scripts
        self.charts: list[dict] = []                     # {line, spec text}
        self.chart: dict | None = None
        self.figures: list[dict] = []
        self.figure: dict | None = None
        self.caption: list[str] | None = None
        self.tones: list[tuple[str, int]] = []
        self.states: list[tuple[str, int]] = []
        self.decisions: list[dict] = []
        self.footnote_ids: list[tuple[str, int]] = []
        self.in_footnotes = 0
        self.text: list[str] = []                        # prose text outside scripts and code, for [^n]
        self.skip_text = 0
        self.ref_text: list[str] = []                    # prose a forge reference could link from
        self.noref: list[str] = []                       # open tags that stop reference linking (a, data-noref)

    def line(self) -> int:
        return self.base + self.getpos()[0]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        ln = self.line()
        if a.get("id"):
            self.ids.append((a["id"], ln))
        if "style" in a:
            self.inline_styles.append(ln)
        if a.get("data-tone") is not None:
            self.tones.append((a["data-tone"] or "", ln))
        if "data-state" in a:
            self.states.append((a["data-state"] or "", ln))
        if tag == "style":
            self.styles.append(ln)
        if tag == "script":
            kind = (a.get("type") or "").lower()
            in_chart = any("sf-chart" in c for _, c in self.stack)
            if kind == "application/json" and in_chart:
                self.chart = {"line": ln, "text": []}
            else:
                self.scripts.append(ln)
            self.skip_text += 1
        if tag in ("code", "pre"):
            self.skip_text += 1
        if re.fullmatch(r"h[1-6]", tag):
            self.heading = [int(tag[1]), ln, []]
        if tag == "figure" and "sf-figure" in cls:
            self.figure = {"line": ln, "id": a.get("id"), "caption": None, "charts": 0, "svg": False, "img": False}
        if self.figure is not None:
            if tag == "svg":
                self.figure["svg"] = True
            if tag == "img":
                self.figure["img"] = True
            if "sf-chart" in cls:
                self.figure["charts"] += 1
            if tag == "figcaption":
                self.caption = []
        if "sf-decision" in cls:
            self.decisions.append({"line": ln, "id": a.get("id"), "recommended": 0})
        if tag == "li" and "data-recommended" in a and self.decisions and any("sf-options" in c for _, c in self.stack):
            self.decisions[-1]["recommended"] += 1
        if tag == "section" and "footnotes" in cls:
            self.in_footnotes += 1
        if self.in_footnotes and tag == "li":
            self.footnote_ids.append((a.get("id") or "", ln))
        if tag == "a" or "data-noref" in a:
            self.noref.append(tag)
        if tag not in self.VOID:
            self.stack.append((tag, cls))

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            if self.chart is not None:
                self.chart["text"] = "".join(self.chart["text"])
                self.charts.append(self.chart)
                if self.figure is not None:
                    self.figure.setdefault("specs", []).append(self.chart)
                self.chart = None
            self.skip_text = max(0, self.skip_text - 1)
        if tag in ("code", "pre"):
            self.skip_text = max(0, self.skip_text - 1)
        if self.heading and tag == f"h{self.heading[0]}":
            self.headings.append((self.heading[0], self.heading[1], " ".join("".join(self.heading[2]).split())))
            self.heading = None
        if tag == "figcaption" and self.caption is not None and self.figure is not None:
            self.figure["caption"] = " ".join("".join(self.caption).split())
            self.caption = None
        if tag == "figure" and self.figure is not None:
            self.figures.append(self.figure)
            self.figure = None
        if tag == "section" and self.in_footnotes:
            self.in_footnotes -= 1
        if self.noref and self.noref[-1] == tag:
            self.noref.pop()
        # Pop to the matching open tag; tolerate unclosed <p>/<li>.
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data: str) -> None:
        if self.chart is not None:
            self.chart["text"].append(data)
            return
        if self.heading:
            self.heading[2].append(data)
        if self.caption is not None:
            self.caption.append(data)
        if not self.skip_text and not self.in_footnotes:
            self.text.append(data)
        if not self.skip_text and not self.noref:
            self.ref_text.append(data)


# ---- chart specs

def walk_spec(spec, path="spec"):
    """Yield (path, node) for every dict in a Vega-Lite spec (layers, concats, facets)."""
    if isinstance(spec, dict):
        yield path, spec
        for k, v in spec.items():
            yield from walk_spec(v, f"{path}.{k}")
    elif isinstance(spec, list):
        for i, v in enumerate(spec):
            yield from walk_spec(v, f"{path}[{i}]")


def has_unit(title: str) -> bool:
    return bool(re.search(r"\([^)]+\)|%", title))


def lint_chart(spec_text: str, ln: int, caption: str, L: Lint) -> None:
    where = f"line {ln}"
    try:
        spec = json.loads(spec_text)
    except json.JSONDecodeError as e:
        L.err(f"{where}: chart spec is not valid JSON ({e.msg} at line {e.lineno} of the spec)")
        return
    if not isinstance(spec, dict):
        L.err(f"{where}: chart spec is not a JSON object")
        return
    if "config" in spec:
        L.err(f"{where}: chart spec sets config; the page themes every chart, so drop it")
    marks = []
    has_rule = has_text = False
    generated = False
    for path, node in walk_spec(spec):
        data = node.get("data") if isinstance(node.get("data"), dict) else None
        if data and "url" in data:
            L.err(f"{where}: chart loads data from a URL ({data['url']}); data lives in the spec as values")
        if data and "sequence" in data:
            generated = True
        mark = node.get("mark")
        if mark is not None:
            kind = mark if isinstance(mark, str) else mark.get("type") if isinstance(mark, dict) else None
            marks.append(kind)
            if kind == "rule":
                has_rule = True
            if kind == "text":
                has_text = True
            if kind and kind not in MARKS:
                L.warn(f"{where}: mark \"{kind}\" is outside the house forms (line, bar, point, area; rule and text for reference lines)")
        # A colour is a string under color/fill/stroke/background, or the "value" of an encoding on one of them.
        colour_channel = re.search(r"\.(?:color|fill|stroke)$", path)
        for key, value in node.items():
            if (key in ("color", "fill", "stroke", "background") or (key == "value" and colour_channel)) and isinstance(value, str) and re.search(HEX + "|" + COLOR_FUNC, value):
                L.err(f"{where}: colour literal {value!r} in the chart spec ({path}.{key}); the page assigns colours")
            if key == "scheme" or (key == "range" and path.endswith("scale")):
                L.err(f"{where}: chart spec sets its own colour scale ({path}.{key}); the page assigns the series palette")
        enc = node.get("encoding")
        if isinstance(enc, dict):
            for ch in ("x", "y"):
                e = enc.get(ch)
                if not isinstance(e, dict) or "field" not in e:
                    continue
                kind = e.get("type")
                title = e.get("title")
                if kind == "quantitative":
                    if not title:
                        L.warn(f"{where}: quantitative {ch} \"{e['field']}\" has no title (write quantity and unit, e.g. \"Latency (ms)\")")
                    elif not has_unit(str(title)):
                        L.warn(f"{where}: {ch} title \"{title}\" has no unit in parentheses (write \"Requests (count)\" or \"Share (%)\")")
                elif kind == "temporal" and not title:
                    L.warn(f"{where}: temporal {ch} \"{e['field']}\" has no title (name the resolution and zone, e.g. \"Day (UTC)\")")
    if has_rule and not has_text:
        L.warn(f"{where}: a reference line (rule) has no text label; add a text layer that names it, e.g. \"SLO 180 ms\"")
    if marks.count("arc"):
        L.warn(f"{where}: a pie or donut; use a bar chart")
    if generated and "illustrative" not in caption.lower():
        L.warn(f"{where}: the chart generates its data (sequence); its caption must say \"Illustrative\" and name the formula")


# ---- the whole file

def lint_shell(text: str, name: str, L: Lint) -> dict:
    """Check everything outside the body; return the parsed forge reference config."""
    refs: dict = {}
    tmpl = read_template()
    for part, rx in (("style block (#sf-style)", STYLE_RE), ("runtime script (#sf-runtime)", RUNTIME_RE)):
        mine, theirs = rx.search(text), rx.search(tmpl)
        if not mine:
            hint = "; this file predates the current house style, so re-scaffold it with `report.py new` and move the body over" if "rp-section" in text or "Report." in text else ""
            L.err(f"the {part} is missing{hint}")
        elif theirs and mine.group(0) != theirs.group(0):
            L.err(f"line {line_of(text, mine.start())}: the {part} differs from the template; a report never edits it (re-scaffold, or change the template in the skill)")
    for needle, what in (
        ('class="sf-topbar"', "top bar (header.sf-topbar)"),
        ('id="contents"', "outline (nav#contents)"),
        ('id="contents-list"', "outline list (#contents-list)"),
        ('id="contents-toggle"', "outline button for narrow screens (#contents-toggle)"),
        ('id="body"', "body container (div.sf-body#body)"),
    ):
        if needle not in text:
            L.err(f"the {what} is missing")
    if not re.search(r'<h1 class="sf-doc-title">\s*\S', text):
        L.err("no title (h1.sf-doc-title)")
    for pm in PLACEHOLDER_RE.finditer(text):
        L.err(f"line {line_of(text, pm.start())}: unfilled placeholder {pm.group(0)}")
    if "<!-- EXAMPLE:BEGIN" in text:
        L.warn("example content is still present (EXAMPLE:BEGIN marker); replace it with the report's own body")
    for rm in re.finditer(r'<(?:script|link|img|iframe|source)\b[^>]*?(?:src|href)="((?:https?:)?//[^"]+)"', text):
        L.err(f"line {line_of(text, rm.start())}: remote resource {rm.group(1)} (a report loads nothing from the network; inline it)")
    vm = VENDOR_RE.search(text)
    if not vm:
        L.err("the VENDOR:BEGIN / VENDOR:END region is missing; re-scaffold with `report.py new` and move the body over")
    elif vm.group(0) != vendor_block(text):
        math, charts = body_needs(text)
        need = "Inter" + (", KaTeX" if math else "") + (", Vega" if charts else "")
        L.err(f"line {line_of(text, vm.start())}: the inlined libraries are out of date for this body (it needs {need}); run `report.py bundle {name}`")
    rm = re.search(r'<meta name="sf-refs" content="([^"]*)"', text)
    if not rm:
        L.err('the forge reference config (<meta name="sf-refs">) is missing')
    else:
        try:
            cfg = json.loads(html.unescape(rm.group(1)))
            if not isinstance(cfg, dict):
                raise ValueError
            refs = cfg
        except ValueError:
            L.err(f"line {line_of(text, rm.start())}: <meta name=\"sf-refs\"> is not a JSON object")
    return refs


def lint_body(text: str, refs: dict, L: Lint) -> None:
    m = BODY_RE.search(text)
    if not m:
        L.err("the BODY:BEGIN / BODY:END markers are missing; the lint cannot find the report body")
        return
    src = m.group(1)
    b = Body(line_of(text, m.start(1)) - 1)
    b.feed(src)
    b.close()

    if not re.search(r"<(p|h2|div|aside|table|figure)\b", re.sub(r"<!--.*?-->", "", src, flags=re.S)):
        L.err("the report body is empty")
    elif not re.search(r'class="sf-lede"', src):
        L.warn("no lede (p.sf-lede): open with one paragraph that states the findings")

    for ln in b.styles:
        L.err(f"line {ln}: <style> in the body; use the house components")
    for ln in b.inline_styles:
        L.err(f"line {ln}: inline style attribute; use the house components")
    for ln in b.scripts:
        L.err(f"line {ln}: executable <script> in the body; charts are Vega-Lite JSON in div.sf-chart")

    # ids
    seen: dict[str, int] = {}
    shell_ids = {"top", "body", "contents", "contents-list", "contents-toggle", "pill", "scrim"}
    for ident, ln in b.ids:
        if ident in shell_ids:
            L.err(f"line {ln}: id \"{ident}\" is taken by the page itself")
        elif ident in seen:
            L.err(f"line {ln}: duplicate id \"{ident}\" (first on line {seen[ident]}); links go to the first one")
        else:
            seen[ident] = ln

    # headings
    prev = 1
    for level, ln, words in b.headings:
        if level == 1:
            L.err(f"line {ln}: <h1> in the body; the page header carries the title")
        elif level >= 5:
            L.warn(f"line {ln}: <h{level}>; the body uses h2 and h3 (h4 at most, as a small label)")
        elif level == 3 and prev < 2:
            L.warn(f"line {ln}: <h3> before any <h2> (the outline nests h3 under the h2 before it)")
        elif level == 4:
            L.warn(f"line {ln}: <h4> is not in the outline; prefer an h3, or a bold lead-in")
        if level in (2, 3) and re.match(r"^\s*(?:[IVXLC]+|\d+(?:\.\d+)*)[.)]\s", words):
            L.warn(f"line {ln}: heading \"{words}\" is numbered by hand; the page numbers sections")
        if level == 2:
            prev = 2
        elif level == 3:
            prev = max(prev, 2)

    # tones and states
    for tone, ln in b.tones:
        if tone not in TONES:
            L.err(f"line {ln}: data-tone=\"{tone}\" (use accent, positive, caution, or negative; omit it for neutral)")
    for state, ln in b.states:
        if state not in STEP_STATES:
            L.err(f"line {ln}: data-state=\"{state}\" (use done, current, next, or skip)")
    for d in b.decisions:
        if not d["id"]:
            L.warn(f"line {d['line']}: sf-decision without an id (d1, d2, …) so it can be linked")
        if d["recommended"] > 1:
            L.err(f"line {d['line']}: decision marks {d['recommended']} options data-recommended; mark at most one")

    # figures
    number = 0
    for f in b.figures:
        ln = f["line"]
        cap = f["caption"]
        if cap is None:
            L.err(f"line {ln}: figure without a <figcaption> (the message, the window, n, and the source)")
            cap = ""
        else:
            nm = re.match(r"(?:Figure|Fig\.)\s+(\d+)\.", cap)
            if not nm:
                L.warn(f"line {ln}: figcaption does not start with \"Figure N.\" (number every figure so prose can cite it)")
            else:
                number += 1
                if int(nm.group(1)) != number:
                    L.warn(f"line {ln}: figure numbered {nm.group(1)}, expected {number} (number figures in document order)")
            if not re.search(r"\b(?:Data|Source)s?\s*:", cap):
                L.warn(f"line {ln}: figcaption names no source (end with \"Data: …\")")
        if not f["charts"] and not f["svg"] and not f["img"]:
            L.warn(f"line {ln}: figure has no chart (div.sf-chart), <svg>, or <img>")
        for spec in f.get("specs", []):
            lint_chart(spec["text"], spec["line"], cap, L)
    in_figures = {id(s) for f in b.figures for s in f.get("specs", [])}
    for c in b.charts:
        if id(c) not in in_figures:
            L.warn(f"line {c['line']}: chart outside a figure.sf-figure (it needs a numbered caption)")
            lint_chart(c["text"], c["line"], "", L)

    # forge references
    unlinked = sorted({m.group(2) for m in REF_RE.finditer("".join(b.ref_text))} - set(k for k, v in refs.items() if isinstance(v, str) and k in "#!~"))
    if unlinked:
        L.warn(f"references with {', '.join(unlinked)} will not link: <meta name=\"sf-refs\"> has no template for them "
               "(re-scaffold with --refs-base, or edit the meta; wrap a non-reference in data-noref)")

    # footnotes
    refs = {int(n) for n in FOOTNOTE_REF_RE.findall("".join(b.text))}
    items = b.footnote_ids
    for i, (ident, ln) in enumerate(items, start=1):
        if ident != f"fn{i}":
            L.err(f"line {ln}: footnote item {i} has id \"{ident}\", expected \"fn{i}\" (items are numbered by position)")
    missing = sorted(n for n in refs if n > len(items) or n < 1)
    if missing:
        L.err(f"citation marker(s) {', '.join(f'[^{n}]' for n in missing)} have no item in <section class=\"footnotes\">")
    unused = [i for i in range(1, len(items) + 1) if i not in refs]
    if unused:
        L.warn(f"footnote item(s) {', '.join(map(str, unused))} are never cited with [^n]")


def cmd_lint(a: argparse.Namespace) -> int:
    with open(a.file, encoding="utf-8") as f:
        text = f.read()
    L = Lint()
    refs = lint_shell(text, a.file, L)
    lint_body(text, refs, L)
    for w in L.warnings:
        print(f"warning: {w}")
    for e in L.errors:
        print(f"error: {e}")
    print(f"{a.file}: {len(L.errors)} error(s), {len(L.warnings)} warning(s)")
    return 1 if L.errors else 0


# ---------------------------------------------------------------- tokens

def cmd_tokens(_: argparse.Namespace) -> int:
    text = read_template()
    m = re.search(r":root \{(.*?)\n\}", text, re.S)
    if not m:
        print("token block not found", file=sys.stderr)
        return 1
    for name in re.findall(r"(--[\w-]+)\s*:", m.group(1)):
        print(name)
    return 0


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="scaffold a report from the template")
    n.add_argument("out")
    n.add_argument("--title", required=True)
    n.add_argument("--kicker", default="Report", help="the word above the title and in the brand (default: Report)")
    n.add_argument("--project", help="the name in the top bar (default: the git repo's directory name)")
    n.add_argument("--forge", choices=["auto", "gitlab", "github", "none"], default="auto",
                   help="link style for #12 / !34 / ~56 (default: github for github.com, else gitlab)")
    n.add_argument("--refs-base", help="the project's web URL, e.g. https://gitlab.example.com/group/repo (default: the origin remote)")
    n.add_argument("--author")
    n.add_argument("--date")
    n.add_argument("--with-example", action="store_true")
    n.add_argument("--force", action="store_true")
    n.set_defaults(fn=cmd_new)

    b = sub.add_parser("bundle", help="inline the vendored libraries the body needs")
    b.add_argument("file")
    b.set_defaults(fn=cmd_bundle)

    l = sub.add_parser("lint", help="check a report against the house style")
    l.add_argument("file")
    l.set_defaults(fn=cmd_lint)

    t = sub.add_parser("tokens", help="list the token names")
    t.set_defaults(fn=cmd_tokens)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
