"""Mark the upstream requests a release delivers as ``ur:delivered``.

Run by the release job after a tag's GitHub release is published. Every open
``opscogs/octools`` issue labelled ``upstream-request`` and ``ur:planned`` in
the milestone named after the tag moves to ``ur:delivered`` and gains a
delivery comment, provided the tag's ``CHANGELOG.md`` entry cites its
``<PREFIX>-UR-NNNN`` id. An uncited or unidentifiable request is left as it is
and reported as a warning, so a release is never failed after publishing.
The issue stays open; it closes when the consumer raises its floor
(``docs/dev/upstream_requests.md``).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

REPO = "opscogs/octools"
DEFAULT_CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
HEADING_RE = re.compile(r"^## \[(?P<version>[^\]]+)\] - ")
ID_RE = re.compile(r"^(?P<id>[A-Z][A-Z0-9]*-UR-\d{4})\b")

Runner = Callable[[list[str]], str]


def default_runner(argv: list[str]) -> str:
    """Run argv as a subprocess and return its captured stdout."""
    return subprocess.run(argv, capture_output=True, text=True, check=True).stdout


def changelog_section(text: str, version: str) -> str:
    """Return the body of the ``## [version]`` entry, or "" when it is absent."""
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        match = HEADING_RE.match(line.strip())
        if match:
            if inside:
                break
            inside = match.group("version") == version
            continue
        if inside:
            lines.append(line)
    return "\n".join(lines)


def planned_issues(version: str, runner: Runner) -> list[dict[str, object]]:
    """Return the open ``ur:planned`` upstream requests in milestone ``version``."""
    argv = [
        "gh",
        "issue",
        "list",
        "--repo",
        REPO,
        "--label",
        "upstream-request",
        "--label",
        "ur:planned",
        "--milestone",
        version,
        "--state",
        "open",
        "--json",
        "number,title",
        "--limit",
        "500",
    ]
    return list(json.loads(runner(argv)))


def deliver(
    issue: dict[str, object], version: str, section: str, runner: Runner
) -> bool:
    """Relabel and comment one issue when the changelog cites it; return True if so."""
    number = str(issue["number"])
    match = ID_RE.match(str(issue["title"]))
    if match is None:
        print(f"::warning::#{number} has no upstream-request id in its title")
        return False
    request_id = match.group("id")
    if request_id not in section:
        print(
            f"::warning::#{number} {request_id} is not cited in the {version} "
            "CHANGELOG entry; left planned"
        )
        return False
    labels = ["--add-label", "ur:delivered", "--remove-label", "ur:planned"]
    runner(["gh", "issue", "edit", number, "--repo", REPO, *labels])
    body = (
        f"Delivered in {version}; CHANGELOG cites {request_id}. "
        "Closes at the consumer floor bump."
    )
    runner(["gh", "issue", "comment", number, "--repo", REPO, "--body", body])
    print(f"#{number} {request_id}: delivered in {version}")
    return True


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the delivery CLI."""
    parser = argparse.ArgumentParser(
        description="Move a release's planned upstream requests to ur:delivered."
    )
    parser.add_argument("tag", help="release tag, e.g. 1.0.0 or v1.0.0")
    parser.add_argument(
        "--changelog",
        type=Path,
        default=DEFAULT_CHANGELOG,
        help="path to CHANGELOG.md (defaults to the repo root file)",
    )
    return parser


def main(argv: list[str] | None = None, *, runner: Runner = default_runner) -> int:
    """Entry point: deliver every cited planned request in the tag's milestone."""
    args = build_parser().parse_args(argv)
    version = args.tag.removeprefix("v")
    section = changelog_section(args.changelog.read_text(encoding="utf-8"), version)
    issues = planned_issues(version, runner)
    delivered = sum(deliver(issue, version, section, runner) for issue in issues)
    print(f"{delivered} of {len(issues)} planned request(s) delivered in {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
