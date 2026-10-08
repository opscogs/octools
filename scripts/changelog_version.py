"""Gate release tags against the top CHANGELOG.md entry.

CHANGELOG.md is the official record of released versions. This script
parses its ``## [X.Y.Z] - <date-or-Unreleased>`` headings and supports two
modes: printing the latest (top) entry's version, and checking that a git
tag matches that top entry. A final tag ``X.Y.Z`` must equal the top entry's
version and that entry must carry a real release date. A pre-release tag
``X.Y.ZaN``, ``X.Y.ZbN`` or ``X.Y.ZrcN`` must name the top entry's version as
its base; that entry may still read ``Unreleased``.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
HEADING_RE = re.compile(r"^## \[(?P<version>[^\]]+)\] - (?P<date>.+)$")
PRERELEASE_RE = re.compile(r"(?P<base>\d+\.\d+\.\d+)(?:a|b|rc)\d+")


@dataclass
class ChangelogEntry:
    """A single parsed CHANGELOG.md heading entry."""

    version: str
    date: str


def parse_top_entry(changelog_path: Path) -> ChangelogEntry:
    """Return the topmost changelog heading entry.

    Raises ValueError if the file is missing or no heading matches.
    """
    if not changelog_path.exists():
        raise ValueError(f"changelog not found: {changelog_path}")
    for line in changelog_path.read_text().splitlines():
        match = HEADING_RE.match(line.strip())
        if match:
            return ChangelogEntry(match.group("version"), match.group("date").strip())
    raise ValueError(f"no changelog entry heading found in {changelog_path}")


def is_release_date(value: str) -> bool:
    """Return True if value is a valid YYYY-MM-DD date string."""
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the changelog-version CLI."""
    parser = argparse.ArgumentParser(
        description="Inspect and validate CHANGELOG.md release entries."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--latest",
        action="store_true",
        help="print the version of the top changelog entry and exit",
    )
    mode.add_argument(
        "--check-tag",
        metavar="TAG",
        help="verify TAG matches the top changelog entry (dated, for a final)",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        default=DEFAULT_CHANGELOG,
        help="path to CHANGELOG.md (defaults to the repo root file)",
    )
    return parser


def cli(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments into a fully validated namespace."""
    args = build_parser().parse_args(argv)
    if args.check_tag is not None and args.check_tag.startswith("v"):
        args.check_tag = args.check_tag[1:]
    return args


def run_latest(changelog_path: Path) -> int:
    """Print the top entry's version. Return a process exit code."""
    try:
        entry = parse_top_entry(changelog_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(entry.version)
    return 0


def run_check_tag(tag_version: str, changelog_path: Path) -> int:
    """Check tag_version against the top changelog entry.

    A final tag fails unless it equals the top entry's version and the entry
    is dated (not "Unreleased"). A pre-release tag fails unless its base
    version equals the top entry's version, dated or not. Return a process
    exit code.
    """
    try:
        entry = parse_top_entry(changelog_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    prerelease = PRERELEASE_RE.fullmatch(tag_version)
    expected = prerelease.group("base") if prerelease else tag_version
    if entry.version != expected:
        print(
            f"error: tag version {tag_version!r} does not match top "
            f"changelog entry version {entry.version!r}",
            file=sys.stderr,
        )
        return 1
    if prerelease is None and not is_release_date(entry.date):
        print(
            f"error: top changelog entry for {entry.version} is not dated "
            f"(found {entry.date!r}); date it before tagging a release",
            file=sys.stderr,
        )
        return 1
    print(f"changelog entry {entry.version} ({entry.date}) matches tag {tag_version}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point: dispatch to the requested changelog check."""
    args = cli(argv)
    if args.latest:
        return run_latest(args.changelog)
    return run_check_tag(args.check_tag, args.changelog)


if __name__ == "__main__":
    sys.exit(main())
