#!/usr/bin/env python3
"""Lint docs/cognition topic files. Exit 1 on format error. Print [pending] lines."""
import re
import sys
from pathlib import Path

CAP = 50
SECTIONS = ["## Believes", "## Decided", "## Unknown"]
LINE_RE = re.compile(r"^- ([BDU])(\d+) (.+)$")


def lint_file(path: Path):
    errors, pending = [], []
    text = path.read_text(encoding="utf-8").splitlines()

    for s in SECTIONS:
        if s not in text:
            errors.append(f"missing section {s!r}")

    ids = set()
    section = None
    content = 0
    for n, raw in enumerate(text, 1):
        line = raw.rstrip()
        if line in SECTIONS:
            section = line[3]  # B, D, U
            continue
        if not line.startswith("- "):
            continue
        content += 1
        m = LINE_RE.match(line)
        if not m:
            errors.append(f"{n}: bad line format: {line}")
            continue
        kind, num, body = m.groups()
        if section and kind != section:
            errors.append(f"{n}: {kind}{num} is under section {section}")
        if (kind, num) in ids:
            errors.append(f"{n}: duplicate id {kind}{num}")
        ids.add((kind, num))
        if kind == "D" and "ref:" not in body:
            errors.append(f"{n}: D{num} has no ref:")
        if "[pending]" in body:
            pending.append(f"{path.name}:{n} {kind}{num} {body}")

    if content > CAP:
        errors.append(f"{content} content lines, cap is {CAP}")
    return errors, pending


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/cognition")
    if not root.is_dir():
        print(f"{root} not found", file=sys.stderr)
        return 1
    readme = root / "README.md"
    if not readme.exists() or "updated-through:" not in readme.read_text(encoding="utf-8"):
        print("README.md missing or has no updated-through", file=sys.stderr)

    rc = 0
    all_pending = []
    for f in sorted(root.glob("*.md")):
        if f.name == "README.md":
            continue
        errors, pending = lint_file(f)
        all_pending += pending
        for e in errors:
            print(f"{f.name}: {e}", file=sys.stderr)
            rc = 1

    if all_pending:
        print("pending:")
        for p in all_pending:
            print(f"  {p}")
    else:
        print("pending: none")
    return rc


if __name__ == "__main__":
    sys.exit(main())
