"""Test scripts/deliver_upstream_requests.py."""

import json
from pathlib import Path

import pytest

from scripts.tests.support import load_script, unload_script


@pytest.fixture(scope="module")
def deliver_upstream_requests():
    """Load the deliver script under a private module name."""
    name, module = load_script("deliver_upstream_requests.py")
    yield module
    unload_script(name)


CHANGELOG = """# Changelog

## [1.0.0] - 2026-09-26

### Added 1.0.0

- OCI-1 a duration kind (DEMO-UR-0001)

## [0.9.0] - 2026-09-01

- OCI-0 an older change (DEMO-UR-0003)
"""

CITED = {"number": 1, "title": "DEMO-UR-0001 Add a duration kind"}
UNCITED = {"number": 2, "title": "DEMO-UR-0002 Add a uuid kind"}
OLDER = {"number": 3, "title": "DEMO-UR-0003 Cited only in an older release"}
NO_ID = {"number": 4, "title": "Add a date kind"}


class FakeGh:
    """Records gh calls and answers the issue list with fixed issues."""

    def __init__(self, issues: list[dict]) -> None:
        self.issues = issues
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> str:
        self.calls.append(argv)
        return json.dumps(self.issues) if argv[:3] == ["gh", "issue", "list"] else ""

    def writes(self) -> list[list[str]]:
        return [call for call in self.calls if call[:3] != ["gh", "issue", "list"]]


@pytest.fixture
def changelog(tmp_path: Path) -> Path:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(CHANGELOG, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.0.0", "DEMO-UR-0001"),
        ("0.9.0", "DEMO-UR-0003"),
    ],
)
def test_changelog_section_is_one_entry(
    deliver_upstream_requests, version: str, expected: str
) -> None:
    """Test a section holds its own entry and stops at the next heading."""
    section = deliver_upstream_requests.changelog_section(CHANGELOG, version)
    assert expected in section
    assert "## [" not in section


def test_changelog_section_missing_version(deliver_upstream_requests) -> None:
    """Test a version with no entry yields an empty section."""
    assert deliver_upstream_requests.changelog_section(CHANGELOG, "2.0.0") == ""


def test_main_delivers_cited_requests_only(
    deliver_upstream_requests, changelog: Path, capsys
) -> None:
    """Test only the request cited in the tag's entry is relabelled and commented."""
    gh = FakeGh([CITED, UNCITED, OLDER, NO_ID])
    code = deliver_upstream_requests.main(
        ["v1.0.0", "--changelog", str(changelog)], runner=gh
    )
    assert code == 0
    listing = gh.calls[0]
    assert listing[listing.index("--milestone") + 1] == "1.0.0"
    assert "ur:planned" in listing
    assert gh.writes() == [
        [
            "gh",
            "issue",
            "edit",
            "1",
            "--repo",
            "opscogs/octools",
            "--add-label",
            "ur:delivered",
            "--remove-label",
            "ur:planned",
        ],
        [
            "gh",
            "issue",
            "comment",
            "1",
            "--repo",
            "opscogs/octools",
            "--body",
            (
                "Delivered in 1.0.0; CHANGELOG cites DEMO-UR-0001. "
                "Closes at the consumer floor bump."
            ),
        ],
    ]
    out = capsys.readouterr().out
    assert "::warning::#2 DEMO-UR-0002 is not cited" in out
    assert "::warning::#3 DEMO-UR-0003 is not cited" in out
    assert "::warning::#4 has no upstream-request id" in out
    assert "1 of 4 planned request(s) delivered in 1.0.0" in out


def test_main_with_nothing_planned(
    deliver_upstream_requests, changelog: Path, capsys
) -> None:
    """Test a release with no planned requests writes nothing and succeeds."""
    gh = FakeGh([])
    assert (
        deliver_upstream_requests.main(
            ["1.0.0", "--changelog", str(changelog)], runner=gh
        )
        == 0
    )
    assert gh.writes() == []
    assert "0 of 0" in capsys.readouterr().out
