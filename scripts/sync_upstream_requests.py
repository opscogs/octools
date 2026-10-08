"""Sync the upstream-request JSONL mirror from GitHub issues.

``opscogs/octools`` GitHub issues labelled ``upstream-request`` are the
canonical record of a consumer's shared-tool ask. This script mirrors that
issue list into ``docs/dev/upstream/requests.jsonl`` for offline review, and
for finding the ``<PREFIX>-UR-NNNN`` id to cite in ``CHANGELOG.md``.
Regenerate it when a release is planned and when a release is cut (see
``docs/dev/upstream_requests.md``, "Mirror"); it is never wired into CI.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "dev" / "upstream" / "requests.jsonl"

GH_LIST_ARGS = [
    "gh",
    "issue",
    "list",
    "--repo",
    "opscogs/octools",
    "--label",
    "upstream-request",
    "--state",
    "all",
    "--json",
    "number,title,labels,milestone,createdAt,closedAt,state",
    "--limit",
    "500",
]

STATE_LABELS = frozenset(
    {"filed", "accepted", "planned", "delivered", "declined", "withdrawn"}
)

ID_RE = re.compile(r"^(?P<id>[A-Z][A-Z0-9]*-UR-\d{4})\s*(?P<rest>.*)$")

Runner = Callable[[list[str]], str]


def default_runner(argv: list[str]) -> str:
    """Run argv as a subprocess and return its captured stdout."""
    return subprocess.run(argv, capture_output=True, text=True, check=True).stdout


def label_names(issue: dict[str, object]) -> list[str]:
    """Return the label names on a raw gh issue dict."""
    labels = issue.get("labels", [])
    return [label["name"] for label in labels] if isinstance(labels, list) else []


def label_value(names: list[str], prefix: str) -> str | None:
    """Return the suffix of the first label starting with prefix, or None."""
    for name in names:
        if name.startswith(prefix):
            return name[len(prefix) :]
    return None


def derive_state(names: list[str]) -> str | None:
    """Return the suffix of the issue's ``ur:`` state label, or None.

    The state labels are ``ur:filed``, ``ur:accepted``, ``ur:planned``,
    ``ur:delivered`` and ``ur:declined``; the stateless ``ur:blocking`` is
    ignored. GitHub's open/closed state is reported separately as
    ``issue_state``.
    """
    for name in names:
        if name.startswith("ur:") and name[3:] in STATE_LABELS:
            return name[3:]
    return None


def build_record(issue: dict[str, object], today: date) -> dict[str, object] | None:
    """Build one mirror record from a raw gh issue dict.

    Returns None (after printing a warning to stderr) when the title carries
    no ``<PREFIX>-UR-NNNN`` id or the issue carries no ``ur:`` state label.
    """
    number = issue.get("number")
    title = str(issue.get("title", ""))
    match = ID_RE.match(title.strip())
    if match is None:
        print(
            f"warning: issue #{number} title has no <PREFIX>-UR-NNNN id, skipping",
            file=sys.stderr,
        )
        return None
    names = label_names(issue)
    state = derive_state(names)
    if state is None:
        print(
            f"warning: issue #{number} missing a ur: state label, skipping",
            file=sys.stderr,
        )
        return None
    milestone = issue.get("milestone")
    milestone_title = milestone.get("title") if isinstance(milestone, dict) else None
    created_at = str(issue.get("createdAt") or "")
    filed = created_at.split("T")[0] if created_at else None
    return {
        "id": match.group("id"),
        "issue": number,
        "consumer": label_value(names, "consumer:"),
        "title": match.group("rest").strip(),
        "state": state,
        "issue_state": str(issue.get("state", "")).lower(),
        "milestone": milestone_title,
        "filed": filed,
        "synced": today.isoformat(),
    }


def build_records(
    issues: list[dict[str, object]], today: date
) -> list[dict[str, object]]:
    """Build every mirror record, sorted by filed date then id, newest last."""
    records = [
        record
        for record in (build_record(issue, today) for issue in issues)
        if record is not None
    ]
    return sorted(records, key=lambda record: (record["filed"], record["id"]))


def render_jsonl(records: list[dict[str, object]]) -> str:
    """Render records as one compact JSON object per line."""
    if not records:
        return ""
    return "\n".join(json.dumps(record) for record in records) + "\n"


def render_markdown(records: list[dict[str, object]]) -> str:
    """Render records as a markdown table for --markdown."""
    header = (
        "| id | issue | consumer | title | state | issue_state | milestone | filed |"
    )
    separator = "| --- | --- | --- | --- | --- | --- | --- | --- |"
    rows = [
        "| {id} | {issue} | {consumer} | {title} | {state} | {issue_state} | "
        "{milestone} | {filed} |".format(
            id=record["id"],
            issue=record["issue"],
            consumer=record["consumer"] or "",
            title=record["title"],
            state=record["state"],
            issue_state=record["issue_state"],
            milestone=record["milestone"] or "",
            filed=record["filed"],
        )
        for record in records
    ]
    return "\n".join([header, separator, *rows])


def strip_synced(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return records with the synced field removed, for staleness comparison."""
    return [{k: v for k, v in record.items() if k != "synced"} for record in records]


def read_existing(path: Path) -> list[dict[str, object]]:
    """Read the mirror file on disk, if any, into a list of records."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def is_up_to_date(fresh: list[dict[str, object]], path: Path) -> bool:
    """Return True if the file on disk matches fresh, ignoring synced dates."""
    return strip_synced(read_existing(path)) == strip_synced(fresh)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the upstream-request sync CLI."""
    parser = argparse.ArgumentParser(
        description="Sync docs/dev/upstream/requests.jsonl from GitHub issues."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the mirror on disk is stale (ignoring the synced date)",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="print a markdown table to stdout and write nothing",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="path to the JSONL mirror file",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    runner: Runner = default_runner,
    today: date | None = None,
) -> int:
    """Entry point: fetch issues, build records, and dispatch by mode."""
    args = build_parser().parse_args(argv)
    today_value = today if today is not None else datetime.now(UTC).date()
    issues = json.loads(runner(GH_LIST_ARGS))
    records = build_records(issues, today_value)
    if args.markdown:
        print(render_markdown(records))
        return 0
    if args.check:
        if is_up_to_date(records, args.output):
            print(f"{args.output} is up to date")
            return 0
        print(
            f"error: {args.output} is stale; run scripts/sync_upstream_requests.py",
            file=sys.stderr,
        )
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_jsonl(records), encoding="utf-8")
    print(f"wrote {len(records)} record(s) to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
