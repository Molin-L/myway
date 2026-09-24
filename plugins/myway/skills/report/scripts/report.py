#!/usr/bin/env python3
"""Scaffold and lint house-style HTML reports. Standard library only.

Subcommands:
  new OUT.html --title T [--subtitle S] [--author A] [--date YYYY-MM-DD]
               [--with-example] [--force]
      Copy templates/report.html to OUT.html with the placeholders filled.
      The example sections and the example chart script are dropped unless
      --with-example is given. Refuses to overwrite unless --force.

  lint FILE.html [--allow-remote]
      Check that FILE.html still follows the house style. Exit 1 on any
      error. Warnings do not change the exit code.

  tokens
      Print the token names the template defines (for reference).
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import re
import subprocess
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "templates", "report.html")
D3_SRC = "https://cdn.jsdelivr.net/npm/d3@7"

EXAMPLE_RE = re.compile(r"<!-- EXAMPLE:BEGIN.*?<!-- EXAMPLE:END -->\n?", re.S)
SECTIONS_EMPTY = "<!-- SECTIONS:BEGIN -->\n  <!-- sections go here: <section class=\"rp-section\" id=\"...\"><h2>...</h2>...<h3 id=\"...\">...</h3>...</section> -->\n<!-- SECTIONS:END -->"


def read_template() -> str:
    with open(TEMPLATE, encoding="utf-8") as f:
        return f.read()


def default_author() -> str:
    try:
        out = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, check=False).stdout.strip()
        if out:
            return out
    except OSError:
        pass
    return os.environ.get("USER", "")


# ---------------------------------------------------------------- new

def cmd_new(a: argparse.Namespace) -> int:
    if os.path.exists(a.out) and not a.force:
        print(f"refusing to overwrite {a.out} (use --force)", file=sys.stderr)
        return 1
    text = read_template()
    if not a.with_example:
        text = EXAMPLE_RE.sub("", text)
        text = re.sub(r"<!-- SECTIONS:BEGIN -->.*?<!-- SECTIONS:END -->", SECTIONS_EMPTY, text, flags=re.S)
    subs = {
        "TITLE": a.title,
        "SUBTITLE": a.subtitle or "",
        "AUTHOR": a.author or default_author(),
        "DATE": a.date or dt.date.today().isoformat(),
    }
    for k, v in subs.items():
        text = text.replace("{{" + k + "}}", html.escape(v, quote=True))
    if not subs["SUBTITLE"]:
        text = text.replace('    <p class="rp-header__sub"></p>\n', "")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(a.out)
    return 0


# ---------------------------------------------------------------- lint

HEX = r"#[0-9a-fA-F]{3,8}\b"
COLOR_FUNC = r"\b(?:rgba?|hsla?|oklch|oklab|color)\("
STYLE_ATTR_RE = re.compile(r'style\s*=\s*"([^"]*)"|style\s*=\s*\'([^\']*)\'', re.I)
JS_COLOR_RE = re.compile(r'\.(?:style|attr)\(\s*["\'](?:fill|stroke|color|background[\w-]*)["\']\s*,\s*["\']([^"\']*)["\']')
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")
# An id attribute in a start tag's attribute string: double-, single-, or
# unquoted. The lookbehind keeps data-id and xml:id out.
ID_ATTR_RE = re.compile(r"""(?<![\w:-])id\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>"'=`]+))""", re.I)


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


def is_literal_color(value: str) -> bool:
    return bool(re.search(HEX, value) or re.search(COLOR_FUNC, value))


def lint_colors(text: str, L: Lint) -> None:
    # Region 1: the first <style> block is the token block; everything else must use tokens.
    m = re.search(r"<style[^>]*>.*?</style>", text, re.S)
    if not m:
        L.err("no <style> block: the house tokens are missing")
        return
    first_end = m.end()
    for extra in re.finditer(r"<style[^>]*>(.*?)</style>", text[first_end:], re.S):
        body = extra.group(1)
        pos = first_end + extra.start()
        L.warn(f"line {line_of(text, pos)}: a second <style> block; prefer the house classes")
        for c in re.finditer(HEX + "|" + COLOR_FUNC, body):
            L.err(f"line {line_of(text, pos + c.start())}: colour literal in a second <style> block; use a token")
    # Inline style attributes (outside the first <style>).
    for sm in STYLE_ATTR_RE.finditer(text):
        if sm.start() < first_end:
            continue
        val = sm.group(1) if sm.group(1) is not None else sm.group(2)
        if is_literal_color(val):
            L.err(f"line {line_of(text, sm.start())}: colour literal in an inline style; use var(--token)")
    # JS colour assignments.
    for jm in JS_COLOR_RE.finditer(text):
        if is_literal_color(jm.group(1)):
            L.err(f"line {line_of(text, jm.start())}: colour literal in a D3 style/attr call; use var(--token) or Report.series[i]")


def call_text(text: str, start: int) -> str:
    """Return the source of one `Report.x(...)` call, from `start` to its closing paren.

    Skips string literals, so a unit such as "Latency (ms)" does not close the call early.
    """
    i = text.find("(", start)
    if i < 0:
        return text[start:]
    depth, quote = 0, None
    j = i
    while j < len(text):
        c = text[j]
        if quote:
            if c == "\\":
                j += 1
            elif c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
        j += 1
    return text[start:]


def lint_axis_titles(text: str, cm: re.Match, fid: str, L: Lint) -> None:
    """Every value axis carries a title with the quantity and its unit, e.g. `yLabel: "Latency (ms)"`."""
    form = cm.group(1)
    src = call_text(text, cm.start())
    ln = line_of(text, cm.start())
    value_axis = "xLabel" if form == "hbar" else "yLabel"
    if not re.search(r"\b" + value_axis + r"\s*:", src):
        L.warn(f"line {ln}: figure #{fid}: Report.{form} without {value_axis} (title the value axis with quantity and unit, e.g. \"Latency (ms)\")")
    else:
        lm = re.search(value_axis + r"\s*:\s*([\"'`])(.*?)\1", src)
        if lm and not re.search(r"\([^)]+\)|%", lm.group(2)):
            L.warn(f"line {ln}: figure #{fid}: {value_axis} \"{lm.group(2)}\" has no unit in parentheses (write \"Requests (count)\" or \"Share (%)\")")
    if form == "line" and not re.search(r"\bxLabel\s*:", src):
        L.warn(f"line {ln}: figure #{fid}: Report.line without xLabel (name the x quantity and its unit or time zone, e.g. \"Day (UTC)\")")


def lint_rule_labels(text: str, cm: re.Match, fid: str, L: Lint) -> None:
    """A reference line is a mark; the house style gives every mark a word. Each `rule` entry needs a `label`."""
    src = call_text(text, cm.start())
    rm = re.search(r"\brule\s*:\s*", src)
    if not rm:
        return
    seg = src[rm.end():]
    values = len(re.findall(r"\bvalue\s*:", seg))
    labels = len(re.findall(r"\blabel\s*:", seg))
    if values and labels < values:
        ln = line_of(text, cm.start())
        L.warn(f"line {ln}: figure #{fid}: a reference line has no label (name it, e.g. label: \"SLO 200 ms\")")


def lint_structure(text: str, tags: "_Tags", L: Lint) -> None:
    if 'localStorage.getItem("rp-theme")' not in text:
        L.err("theme bootstrap script is missing (data-theme is not set before paint)")
    ids = {i for i, _ in tags.ids}
    if "rp-toggle" not in ids:
        L.err('theme toggle is missing (button id="rp-toggle")')
    if "rp-nav" not in tags.classes:
        L.err('sticky top bar is missing (class="rp-nav")')
    if "rp-outline" not in ids:
        hint = "; this file predates the outline, so re-scaffold it with `report.py new` and move the sections over" if "rp-nav-links" in ids else ""
        L.err(f'outline container is missing (nav id="rp-outline"){hint}')
    if "rp-outline-toggle" not in ids:
        L.err('outline button for narrow screens is missing (button id="rp-outline-toggle")')
    if "rp-layout" not in tags.classes:
        L.err('layout wrapper is missing (div class="rp-layout" around the outline and <main>)')
    if ":root[data-theme=\"dark\"]" not in text:
        L.err("dark token block is missing (:root[data-theme=\"dark\"])")
    if not re.search(r"<h1[^>]*>\s*\S", text):
        L.err("no <h1> title")
    for pm in PLACEHOLDER_RE.finditer(text):
        L.err(f"line {line_of(text, pm.start())}: unfilled placeholder {pm.group(0)}")
    if "<!-- EXAMPLE:BEGIN" in text:
        L.warn("example content is still present (EXAMPLE:BEGIN marker); replace it with the report's own sections")
    # sections
    for sm in re.finditer(r"<section\b([^>]*)>", text):
        attrs = sm.group(1)
        if "rp-section" not in attrs:
            L.warn(f"line {line_of(text, sm.start())}: <section> without class rp-section (the outline skips it)")
            continue
        if not ID_ATTR_RE.search(attrs):
            L.err(f"line {line_of(text, sm.start())}: rp-section without an id (the outline links to it)")
        rest = text[sm.end():sm.end() + 400]
        if not re.search(r"<h2\b", rest):
            L.err(f"line {line_of(text, sm.start())}: rp-section does not start with an <h2>")
    # figures
    fig_ids = []
    for fm in re.finditer(r"<figure\b([^>]*)>(.*?)</figure>", text, re.S):
        attrs, body = fm.group(1), fm.group(2)
        ln = line_of(text, fm.start())
        if "rp-figure" not in attrs:
            L.warn(f"line {ln}: <figure> without class rp-figure")
        idm = ID_ATTR_RE.search(attrs)
        if not idm:
            L.err(f"line {ln}: figure without an id (charts are addressed by id)")
        else:
            fig_ids.append((idm.group(1) or idm.group(2) or idm.group(3), ln, fm.start()))
        cap = re.search(r"<figcaption\b[^>]*>(.*?)</figcaption>", body, re.S)
        if not cap:
            L.err(f"line {ln}: figure without a <figcaption> (name the source)")
        elif not re.match(r"\s*(Figure|Fig\.)\s+\d+", re.sub(r"<[^>]+>", "", cap.group(1))):
            L.warn(f"line {ln}: figcaption does not start with 'Figure N.' (number every figure so prose can cite it)")
        if "rp-figure__title" not in body:
            L.warn(f"line {ln}: figure without a .rp-figure__title")
        if "rp-figure__sub" not in body:
            L.warn(f"line {ln}: figure without a .rp-figure__sub (state quantity, unit, window, and n)")
    for fid, ln, pos in fig_ids:
        cm = re.search(r"Report\.(\w+)\(\s*[\"']#" + re.escape(fid) + r"[\"']", text)
        if not cm and "<svg" not in text[pos:]:
            L.warn(f"line {ln}: figure #{fid} has no Report.* call and no inline <svg>")
        if cm:
            lint_axis_titles(text, cm, fid, L)
            lint_rule_labels(text, cm, fid, L)
    # tables
    for tm in re.finditer(r"<table\b([^>]*)>", text):
        if "rp-table" not in tm.group(1):
            L.warn(f"line {line_of(text, tm.start())}: <table> without class rp-table")


class _Tags(HTMLParser):
    """Collect ids, classes, and the outline's headings from real start tags only.

    A parser, not a regex: `id="…"` inside a code sample, a comment, or a
    script is text, not an attribute, and must not count as an id. The
    contents of <template> and <noscript> are not part of the live page.
    """

    INERT = ("template", "noscript")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[tuple[str, int]] = []        # (id, line)
        self.classes: set[str] = set()
        self.outline: list[tuple[int, int]] = []    # (level, line); level 0 starts a section.rp-section
        self.hand_written: list[int] = []           # lines of entries written into the outline
        self.sections: list[bool] = []              # open <section>s: is it an rp-section?
        self.outline_depth = 0                      # nav depth inside nav#rp-outline
        self.inert = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.INERT:
            self.inert += 1
        if self.inert:
            return
        line = self.getpos()[0]
        ident = next((v for k, v in attrs if k == "id"), None)   # the first one wins, as in a browser; "" names nothing
        cls = (next((v for k, v in attrs if k == "class" and v), "") or "").split()
        if ident:
            self.ids.append((ident, line))
        self.classes.update(cls)
        if tag == "section":
            self.sections.append("rp-section" in cls)
            if "rp-section" in cls:
                self.outline.append((0, line))
        elif any(self.sections) and re.fullmatch(r"h[2-6]", tag):
            self.outline.append((int(tag[1]), line))
        if tag == "nav" and (self.outline_depth or ident == "rp-outline"):
            self.outline_depth += 1
        elif self.outline_depth and tag in ("a", "ol", "ul", "li"):
            self.hand_written.append(line)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.INERT and self.inert:
            self.inert -= 1
        elif self.inert:
            return
        elif tag == "section" and self.sections:
            self.sections.pop()
        elif tag == "nav" and self.outline_depth:
            self.outline_depth -= 1


def parse_tags(text: str) -> _Tags:
    tags = _Tags()
    tags.feed(text)
    tags.close()
    return tags


def lint_outline(tags: _Tags, L: Lint) -> None:
    """The outline nests h2 > h3 > h4 and links to ids, so the levels and the ids must be sound."""
    seen: dict[str, int] = {}
    for ident, ln in tags.ids:
        if ident in seen:
            L.err(f"line {ln}: duplicate id \"{ident}\" (first on line {seen[ident]}); the outline and every link to it go to the first one")
        else:
            seen[ident] = ln
    if tags.hand_written:
        L.err(f"line {tags.hand_written[0]}: entries are hand-written inside nav#rp-outline; delete them, the runtime builds the outline from the headings")
    prev = 1
    for level, ln in tags.outline:
        if level == 0:  # a new section: its first heading must be an h2
            prev = 1
            continue
        if level > 4:
            L.warn(f"line {ln}: <h{level}> is not in the outline (it shows h2 to h4); use an h4 or a bold lead-in")
        elif level > prev + 1:
            L.warn(f"line {ln}: <h{level}> follows <h{prev}> with no <h{prev + 1}> between (the outline nests by level)")
        prev = min(level, 4)


def lint_remote(text: str, L: Lint, allow_remote: bool) -> None:
    if 'src="' + D3_SRC + '"' not in text and "d3.min.js" not in text and "d3.v7" not in text:
        L.err("D3 is not loaded (expected " + D3_SRC + " or a vendored d3.min.js)")
    for rm in re.finditer(r'<(?:script|link)\b[^>]*?(?:src|href)="(https?://[^"]+)"', text):
        url = rm.group(1)
        if url.startswith(D3_SRC):
            continue
        msg = f"line {line_of(text, rm.start())}: remote resource {url}"
        (L.warn if allow_remote else L.err)(msg + ("" if allow_remote else " (only the D3 CDN is allowed; use --allow-remote to accept)"))


def cmd_lint(a: argparse.Namespace) -> int:
    with open(a.file, encoding="utf-8") as f:
        text = f.read()
    L = Lint()
    tags = parse_tags(text)
    lint_structure(text, tags, L)
    lint_outline(tags, L)
    lint_colors(text, L)
    lint_remote(text, L, a.allow_remote)
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
    n.add_argument("--subtitle")
    n.add_argument("--author")
    n.add_argument("--date")
    n.add_argument("--with-example", action="store_true")
    n.add_argument("--force", action="store_true")
    n.set_defaults(fn=cmd_new)

    l = sub.add_parser("lint", help="check a report against the house style")
    l.add_argument("file")
    l.add_argument("--allow-remote", action="store_true")
    l.set_defaults(fn=cmd_lint)

    t = sub.add_parser("tokens", help="list the token names")
    t.set_defaults(fn=cmd_tokens)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
