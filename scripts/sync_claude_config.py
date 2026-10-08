"""Generate Claude Code rules from the Cursor configuration.

``.cursor/rules/*.mdc`` is the single source of truth. Each rule becomes
``.claude/rules/<name>.md``: a Cursor ``globs`` value becomes a Claude
``paths`` list, and a rule without globs loads in every session. Bodies are
copied with Cursor tool names and ``.cursor`` file references translated to
their Claude equivalents, and each generated file opens its body with an HTML
comment naming its source.

Run with no arguments to rewrite the generated files and remove generated
files whose source is gone; run with ``--check`` to report drift and exit 1
without writing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_NAME = "scripts/sync_claude_config.py"
HEADER_MARKER = f"by {SCRIPT_NAME}"
# Ordered text substitutions from Cursor vocabulary to Claude vocabulary.
SUBSTITUTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\.cursor/rules/([\w-]+)\.mdc"), r".claude/rules/\1.md"),
    (re.compile(r"`Task`"), "`Agent`"),
    (re.compile(r"\bTask tool\b"), "Agent tool"),
    (re.compile(r"\bTask invocation\b"), "Agent invocation"),
    (re.compile(r"`StrReplace`"), "`Edit`"),
    (re.compile(r"\bCursor/AI agents\b"), "AI agents"),
)


def parse_fields(entries: list[str]) -> dict[str, str]:
    """Parse frontmatter lines into ``key: value`` pairs.

    An indented line (or a lone closing ``]``) continues the previous key's
    value; continuation lines are joined with newlines. Blank and ``#`` comment
    lines are skipped. Any other line that is not ``key: value`` raises
    ``ValueError``.
    """
    fields: dict[str, str] = {}
    key = ""
    for entry in entries:
        stripped = entry.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if entry[0] in " \t" or (key and stripped == "]"):
            if not key:
                raise ValueError(f"unassignable frontmatter line: {stripped!r}")
            fields[key] = f"{fields[key]}\n{stripped}".strip()
            continue
        name, sep, value = entry.partition(":")
        if not sep or not name.strip():
            raise ValueError(f"unassignable frontmatter line: {stripped!r}")
        key = name.strip()
        fields[key] = value.strip()
    return fields


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a leading ``---`` block into raw ``key: value`` pairs and body."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            fields = parse_fields(lines[1:index])
            return fields, "".join(lines[index + 1 :])
    raise ValueError("frontmatter opened with --- but never closed")


def parse_globs(value: str) -> list[str]:
    """Parse a Cursor ``globs`` value into patterns.

    Accepts a bare pattern, a comma-separated string, a YAML flow list (on one
    line or wrapped over several), or a YAML block list of ``- pattern`` lines.
    Commas inside ``{a,b}`` brace groups do not split patterns.
    """
    rows = [row.strip() for row in value.splitlines() if row.strip()]
    if rows and all(row.startswith("-") for row in rows):
        value = ",".join(row[1:] for row in rows)
    else:
        value = " ".join(rows)
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    patterns: list[str] = []
    current: list[str] = []
    depth = 0
    for char in value + ",":
        if char == "," and depth == 0:
            pattern = "".join(current).strip().strip("\"'")
            if pattern:
                patterns.append(pattern)
            current = []
            continue
        depth += {"{": 1, "}": -1}.get(char, 0)
        current.append(char)
    return patterns


def translate(body: str) -> str:
    """Rewrite Cursor tool names and ``.cursor`` file references for Claude."""
    for pattern, replacement in SUBSTITUTIONS:
        body = pattern.sub(replacement, body)
    return body


def header(source: str) -> str:
    """Return the HTML comment that names a generated file's source."""
    return f"<!-- Generated from {source} {HEADER_MARKER}; edit the source. -->\n"


def join_body(source: str, body: str) -> str:
    """Put the source header on the body's first line, above its content."""
    return header(source) + "\n" + translate(body).lstrip("\n")


def render_rule(source: str, text: str) -> str:
    """Render one Cursor rule as a Claude rule file."""
    fields, body = split_frontmatter(text)
    patterns = parse_globs(fields.get("globs", ""))
    if "globs" in fields and not patterns:
        raise ValueError("globs is present but yields no patterns")
    if fields.get("alwaysApply", "").lower() == "true" or not patterns:
        return join_body(source, body)
    paths = "".join(f'  - "{pattern}"\n' for pattern in patterns)
    return f"---\npaths:\n{paths}---\n" + join_body(source, body)


def expected_files(root: Path) -> dict[Path, str]:
    """Map every generated file path under root to its expected content."""
    expected: dict[Path, str] = {}
    for src in sorted((root / ".cursor" / "rules").glob("*.mdc")):
        target = root / ".claude" / "rules" / f"{src.stem}.md"
        source = src.relative_to(root).as_posix()
        try:
            expected[target] = render_rule(source, src.read_text())
        except ValueError as exc:
            raise ValueError(f"{source}: {exc}") from exc
    return expected


def stale_files(root: Path, expected: dict[Path, str]) -> list[Path]:
    """Return generated files whose Cursor source no longer exists."""
    stale: list[Path] = []
    for path in sorted((root / ".claude" / "rules").glob("*.md")):
        if path not in expected and HEADER_MARKER in path.read_text():
            stale.append(path)
    return stale


def sync(root: Path, check: bool) -> int:
    """Write (or, with check, compare) the generated files. Return exit code."""
    expected = expected_files(root)
    drift = [
        path
        for path, content in expected.items()
        if not path.exists() or path.read_text() != content
    ]
    stale = stale_files(root, expected)
    for path in drift + stale:
        print(path.relative_to(root).as_posix())
    if check:
        if drift or stale:
            print(f"out of date; run: python {SCRIPT_NAME}", file=sys.stderr)
            return 1
        return 0
    for path in drift:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected[path])
    for path in stale:
        path.unlink()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the sync CLI."""
    parser = argparse.ArgumentParser(
        description="Generate .claude/rules from .cursor/rules."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report out-of-date generated files and exit 1 without writing",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root (defaults to this script's repository)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point: sync or check the generated Claude configuration."""
    args = build_parser().parse_args(argv)
    try:
        return sync(args.root, args.check)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
