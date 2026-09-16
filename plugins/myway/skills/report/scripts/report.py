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

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "templates", "report.html")
D3_SRC = "https://cdn.jsdelivr.net/npm/d3@7"

EXAMPLE_RE = re.compile(r"<!-- EXAMPLE:BEGIN.*?<!-- EXAMPLE:END -->\n?", re.S)
SECTIONS_EMPTY = "<!-- SECTIONS:BEGIN -->\n  <!-- sections go here: <section class=\"rp-section\" id=\"...\"><h2>...</h2>...</section> -->\n<!-- SECTIONS:END -->"


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


def lint_structure(text: str, L: Lint) -> None:
    if 'localStorage.getItem("rp-theme")' not in text:
        L.err("theme bootstrap script is missing (data-theme is not set before paint)")
    if 'id="rp-toggle"' not in text:
        L.err('nav theme toggle is missing (button id="rp-toggle")')
    if 'class="rp-nav"' not in text:
        L.err('sticky nav is missing (nav class="rp-nav")')
    if 'id="rp-nav-links"' not in text:
        L.err('nav link container is missing (id="rp-nav-links")')
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
            L.warn(f"line {line_of(text, sm.start())}: <section> without class rp-section (nav will skip it)")
            continue
        if not re.search(r'\bid="[^"]+"', attrs):
            L.err(f"line {line_of(text, sm.start())}: rp-section without an id (nav needs it)")
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
        idm = re.search(r'\bid="([^"]+)"', attrs)
        if not idm:
            L.err(f"line {ln}: figure without an id (charts are addressed by id)")
        else:
            fig_ids.append((idm.group(1), ln))
        cap = re.search(r"<figcaption\b[^>]*>(.*?)</figcaption>", body, re.S)
        if not cap:
            L.err(f"line {ln}: figure without a <figcaption> (name the source)")
        elif not re.match(r"\s*(Figure|Fig\.)\s+\d+", re.sub(r"<[^>]+>", "", cap.group(1))):
            L.warn(f"line {ln}: figcaption does not start with 'Figure N.' (number every figure so prose can cite it)")
        if "rp-figure__title" not in body:
            L.warn(f"line {ln}: figure without a .rp-figure__title")
        if "rp-figure__sub" not in body:
            L.warn(f"line {ln}: figure without a .rp-figure__sub (state quantity, unit, window, and n)")
    for fid, ln in fig_ids:
        cm = re.search(r"Report\.(\w+)\(\s*[\"']#" + re.escape(fid) + r"[\"']", text)
        if not cm and "<svg" not in text[text.find(f'id="{fid}"'):]:
            L.warn(f"line {ln}: figure #{fid} has no Report.* call and no inline <svg>")
        if cm:
            lint_axis_titles(text, cm, fid, L)
    # tables
    for tm in re.finditer(r"<table\b([^>]*)>", text):
        if "rp-table" not in tm.group(1):
            L.warn(f"line {line_of(text, tm.start())}: <table> without class rp-table")


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
    lint_structure(text, L)
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
