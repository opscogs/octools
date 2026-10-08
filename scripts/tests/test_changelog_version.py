"""Test scripts/changelog_version.py."""

from pathlib import Path

import pytest

from scripts.tests.support import load_script, unload_script


@pytest.fixture(scope="module")
def changelog_version():
    """Load the changelog script under a private module name."""
    name, module = load_script("changelog_version.py")
    yield module
    unload_script(name)


VALID_CHANGELOG = """# Changelog

## [1.2.3] - 2026-08-29

- Did a thing

## [1.2.2] - 2026-08-01

- Did an earlier thing
"""

UNRELEASED_CHANGELOG = """# Changelog

## [1.2.3] - Unreleased

- Did a thing
"""

MALFORMED_CHANGELOG = """# Changelog

Nothing here matches a heading.
"""


@pytest.fixture
def changelog_file(tmp_path: Path) -> Path:
    """Return a helper that writes given text to a temp CHANGELOG.md."""

    def _write(text: str) -> Path:
        path = tmp_path / "CHANGELOG.md"
        path.write_text(text)
        return path

    return _write


def test_parse_top_entry(changelog_version, changelog_file) -> None:
    """Test parsing returns the topmost entry, not a later one."""
    path = changelog_file(VALID_CHANGELOG)
    entry = changelog_version.parse_top_entry(path)
    assert entry.version == "1.2.3"
    assert entry.date == "2026-08-29"


def test_parse_top_entry_missing_file(changelog_version, tmp_path: Path) -> None:
    """Test parsing raises ValueError when the changelog file is absent."""
    missing = tmp_path / "CHANGELOG.md"
    with pytest.raises(ValueError, match="changelog not found"):
        changelog_version.parse_top_entry(missing)


def test_parse_top_entry_malformed(changelog_version, changelog_file) -> None:
    """Test parsing raises ValueError when no heading matches."""
    path = changelog_file(MALFORMED_CHANGELOG)
    with pytest.raises(ValueError, match="no changelog entry heading found"):
        changelog_version.parse_top_entry(path)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-29", True),
        ("Unreleased", False),
        ("2026-13-40", False),
    ],
)
def test_is_release_date(changelog_version, value: str, expected: bool) -> None:
    """Test date validation accepts YYYY-MM-DD and rejects everything else."""
    assert changelog_version.is_release_date(value) is expected


def test_run_latest_prints_version(
    changelog_version, changelog_file, capsys: pytest.CaptureFixture
) -> None:
    """Test --latest mode prints the top version and exits 0."""
    path = changelog_file(VALID_CHANGELOG)
    exit_code = changelog_version.run_latest(path)
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "1.2.3"


def test_run_latest_missing_file(
    changelog_version, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Test --latest mode fails clearly when the changelog is missing."""
    exit_code = changelog_version.run_latest(tmp_path / "CHANGELOG.md")
    assert exit_code != 0
    assert "error" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("body", "tag"),
    [
        (VALID_CHANGELOG, "1.2.3"),
        (VALID_CHANGELOG, "v1.2.3"),
        (VALID_CHANGELOG, "1.2.3rc1"),
        (UNRELEASED_CHANGELOG, "1.2.3a1"),
        (UNRELEASED_CHANGELOG, "1.2.3b2"),
        (UNRELEASED_CHANGELOG, "v1.2.3rc10"),
    ],
)
def test_run_check_tag_success(
    changelog_version,
    changelog_file,
    capsys: pytest.CaptureFixture,
    body: str,
    tag: str,
) -> None:
    """Test --check-tag passes a dated final, and a pre-release dated or not."""
    path = changelog_file(body)
    args = changelog_version.cli(["--check-tag", tag, "--changelog", str(path)])
    exit_code = changelog_version.run_check_tag(args.check_tag, args.changelog)
    assert exit_code == 0
    assert "matches tag" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("body", "tag", "err_snippet"),
    [
        (VALID_CHANGELOG, "9.9.9", "does not match"),
        (UNRELEASED_CHANGELOG, "1.2.3", "not dated"),
        (UNRELEASED_CHANGELOG, "1.2.4rc1", "does not match"),
        (VALID_CHANGELOG, "1.2.2rc1", "does not match"),
        (UNRELEASED_CHANGELOG, "1.2.3.dev1", "does not match"),
        (None, "1.2.3", "error"),
    ],
)
def test_run_check_tag_failure(
    changelog_version,
    changelog_file,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    body: str | None,
    tag: str,
    err_snippet: str,
) -> None:
    """Test --check-tag fails for a mismatch, an undated final or no changelog."""
    path = changelog_file(body) if body is not None else tmp_path / "CHANGELOG.md"
    exit_code = changelog_version.run_check_tag(tag, path)
    assert exit_code != 0
    assert err_snippet in capsys.readouterr().err


def test_cli_strips_leading_v(changelog_version) -> None:
    """Test cli() strips an optional leading v from --check-tag."""
    args = changelog_version.cli(["--check-tag", "v1.2.3"])
    assert args.check_tag == "1.2.3"


def test_cli_requires_a_mode(changelog_version) -> None:
    """Test cli() exits nonzero when neither --latest nor --check-tag given."""
    with pytest.raises(SystemExit):
        changelog_version.cli([])


def test_main_latest(changelog_version, changelog_file) -> None:
    """Test main() dispatches to the latest-version path."""
    path = changelog_file(VALID_CHANGELOG)
    assert changelog_version.main(["--latest", "--changelog", str(path)]) == 0


def test_main_check_tag(changelog_version, changelog_file) -> None:
    """Test main() dispatches to the check-tag path."""
    path = changelog_file(VALID_CHANGELOG)
    exit_code = changelog_version.main(
        ["--check-tag", "1.2.3", "--changelog", str(path)]
    )
    assert exit_code == 0
