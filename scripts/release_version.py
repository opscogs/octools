"""Map a release tag to the PyPI and npm versions it publishes.

A release tag is a final ``X.Y.Z`` or a PEP 440 pre-release ``X.Y.ZaN``,
``X.Y.ZbN`` or ``X.Y.ZrcN``, with no ``v`` prefix. The PyPI version is the
tag itself. The npm version is the matching semver (``X.Y.Z``,
``X.Y.Z-alpha.N``, ``X.Y.Z-beta.N`` or ``X.Y.Z-rc.N``) and the npm dist-tag is
``latest`` for a final and ``next`` for a pre-release. ``--dev SHA`` gives the
mapping a non-tag build packages under: ``0.0.0+SHA`` and npm ``0.0.0``.

The mapping prints as ``key=value`` lines, ready to append to
``$GITHUB_OUTPUT``. ``--check`` also asserts that the Python ``VERSION`` file
and the TypeScript ``package.json`` carry the mapped versions, the lockstep
gate a tag build passes before either package publishes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VERSION_FILE = ROOT / "python" / "src" / "octools" / "VERSION"
DEFAULT_PACKAGE_JSON = ROOT / "typescript" / "package.json"
TAG_RE = re.compile(
    r"(?P<base>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))"
    r"(?:(?P<pre>a|b|rc)(?P<num>0|[1-9]\d*))?"
)
SHA_RE = re.compile(r"[0-9a-f]{7,40}")
NPM_PRE_LABELS = {"a": "alpha", "b": "beta", "rc": "rc"}


@dataclass(frozen=True)
class ReleaseVersions:
    """The versions and npm dist-tag one build publishes or packages."""

    pypi_version: str
    npm_version: str
    npm_dist_tag: str
    prerelease: bool

    def lines(self) -> list[str]:
        """Return the mapping as ``key=value`` lines."""
        return [
            f"pypi_version={self.pypi_version}",
            f"npm_version={self.npm_version}",
            f"npm_dist_tag={self.npm_dist_tag}",
            f"prerelease={str(self.prerelease).lower()}",
        ]


def map_tag(tag: str) -> ReleaseVersions:
    """Return the versions a release tag publishes.

    Raises ValueError for anything other than ``X.Y.Z`` or ``X.Y.Z{a,b,rc}N``.
    """
    match = TAG_RE.fullmatch(tag)
    if match is None:
        raise ValueError(
            f"invalid release tag {tag!r}: expected X.Y.Z, X.Y.ZaN, X.Y.ZbN "
            "or X.Y.ZrcN with no 'v' prefix"
        )
    base, pre = match.group("base"), match.group("pre")
    if pre is None:
        return ReleaseVersions(tag, base, "latest", prerelease=False)
    npm_version = f"{base}-{NPM_PRE_LABELS[pre]}.{match.group('num')}"
    return ReleaseVersions(tag, npm_version, "next", prerelease=True)


def map_dev(sha: str) -> ReleaseVersions:
    """Return the versions a non-tag build packages under for commit ``sha``.

    The npm version drops the commit, since npm discards semver build
    metadata. Raises ValueError unless ``sha`` is 7 to 40 lowercase hex digits.
    """
    if SHA_RE.fullmatch(sha) is None:
        raise ValueError(f"invalid commit sha {sha!r}: expected 7-40 hex digits")
    return ReleaseVersions(f"0.0.0+{sha}", "0.0.0", "", prerelease=True)


def manifest_mismatches(
    versions: ReleaseVersions, version_file: Path, package_json: Path
) -> list[str]:
    """Return one message per manifest whose version differs from the mapping."""
    problems: list[str] = []
    if not version_file.exists():
        problems.append(f"{version_file} is missing")
    else:
        found = version_file.read_text(encoding="utf-8").strip()
        if found != versions.pypi_version:
            problems.append(
                f"{version_file} holds {found!r}, expected {versions.pypi_version!r}"
            )
    try:
        npm_found = json.loads(package_json.read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        problems.append(f"cannot read the version in {package_json}: {exc!r}")
    else:
        if npm_found != versions.npm_version:
            problems.append(
                f"{package_json} holds {npm_found!r}, expected {versions.npm_version!r}"
            )
    return problems


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the release-version CLI."""
    parser = argparse.ArgumentParser(
        description="Map a release tag to its PyPI and npm versions."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("tag", nargs="?", help="release tag, e.g. 1.2.0 or 1.2.0rc1")
    source.add_argument(
        "--dev", metavar="SHA", help="map a non-tag build of commit SHA instead"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail unless the VERSION file and package.json carry the versions",
    )
    parser.add_argument("--version-file", type=Path, default=DEFAULT_VERSION_FILE)
    parser.add_argument("--package-json", type=Path, default=DEFAULT_PACKAGE_JSON)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point: print the mapping and, with ``--check``, gate the manifests."""
    args = build_parser().parse_args(argv)
    try:
        versions = map_dev(args.dev) if args.dev is not None else map_tag(args.tag)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.check:
        problems = manifest_mismatches(versions, args.version_file, args.package_json)
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        if problems:
            return 1
    print("\n".join(versions.lines()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
