"""Test scripts/release_version.py."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.tests.support import load_script, unload_script

SCRIPT = Path(__file__).resolve().parents[1] / "release_version.py"


@pytest.fixture(scope="module")
def release_version():
    """Load the release-version script under a private module name."""
    name, module = load_script("release_version.py")
    yield module
    unload_script(name)


@pytest.fixture
def manifests(tmp_path: Path):
    """Return a helper writing a VERSION file and a package.json into tmp_path."""

    def _write(pypi: str | None, npm: object) -> list[str]:
        version_file = tmp_path / "VERSION"
        package_json = tmp_path / "package.json"
        if pypi is not None:
            version_file.write_text(pypi)
        package_json.write_text(
            npm if isinstance(npm, str) else json.dumps(npm), encoding="utf-8"
        )
        return [
            "--version-file",
            str(version_file),
            "--package-json",
            str(package_json),
        ]

    return _write


@pytest.mark.parametrize(
    ("tag", "npm_version", "dist_tag", "prerelease"),
    [
        ("1.2.0", "1.2.0", "latest", False),
        ("0.0.1", "0.0.1", "latest", False),
        ("10.20.30", "10.20.30", "latest", False),
        ("1.2.0a1", "1.2.0-alpha.1", "next", True),
        ("1.2.0b0", "1.2.0-beta.0", "next", True),
        ("1.2.0rc12", "1.2.0-rc.12", "next", True),
    ],
)
def test_map_tag(
    release_version, tag: str, npm_version: str, dist_tag: str, prerelease: bool
) -> None:
    """Test a tag maps to itself on PyPI and to the semver form on npm."""
    versions = release_version.map_tag(tag)
    assert versions == release_version.ReleaseVersions(
        tag, npm_version, dist_tag, prerelease
    )


@pytest.mark.parametrize(
    "tag",
    [
        "v1.2.0",
        "1.2",
        "1.2.0.0",
        "01.2.0",
        "1.2.0-rc.1",
        "1.2.0rc",
        "1.2.0c1",
        "1.2.0rc01",
        "1.2.0.dev1",
        "1.2.0.post1",
        "1.2.0+local",
        "1.2.0\n",
        "",
    ],
)
def test_map_tag_rejects(release_version, tag: str) -> None:
    """Test anything but a final or an a/b/rc pre-release is rejected."""
    with pytest.raises(ValueError, match="invalid release tag"):
        release_version.map_tag(tag)


def test_map_dev(release_version) -> None:
    """Test a non-tag build packages as 0.0.0 with the commit as local label."""
    versions = release_version.map_dev("abc1234")
    assert versions.lines() == [
        "pypi_version=0.0.0+abc1234",
        "npm_version=0.0.0",
        "npm_dist_tag=",
        "prerelease=true",
    ]


@pytest.mark.parametrize("sha", ["abc12", "ABC1234", "abc123g", "a" * 41])
def test_map_dev_rejects(release_version, sha: str) -> None:
    """Test --dev accepts only a 7-40 digit lowercase hex sha."""
    with pytest.raises(ValueError, match="invalid commit sha"):
        release_version.map_dev(sha)


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (
            ["1.2.0"],
            [
                "pypi_version=1.2.0",
                "npm_version=1.2.0",
                "npm_dist_tag=latest",
                "prerelease=false",
            ],
        ),
        (
            ["1.2.0rc1"],
            [
                "pypi_version=1.2.0rc1",
                "npm_version=1.2.0-rc.1",
                "npm_dist_tag=next",
                "prerelease=true",
            ],
        ),
    ],
)
def test_main_prints_mapping(
    release_version, capsys: pytest.CaptureFixture, argv: list[str], expected
) -> None:
    """Test main() prints the mapping as key=value lines."""
    assert release_version.main(argv) == 0
    assert capsys.readouterr().out.splitlines() == expected


@pytest.mark.parametrize(
    ("argv", "pypi", "npm"),
    [
        (["1.2.0"], "1.2.0", {"version": "1.2.0"}),
        (["1.2.0b3"], "1.2.0b3\n", {"version": "1.2.0-beta.3"}),
        (["--dev", "abc1234"], "0.0.0+abc1234", {"version": "0.0.0"}),
    ],
)
def test_main_check_passes(
    release_version, manifests, argv: list[str], pypi: str, npm: dict
) -> None:
    """Test --check passes when both manifests carry the mapped versions."""
    assert release_version.main([*argv, "--check", *manifests(pypi, npm)]) == 0


@pytest.mark.parametrize(
    ("tag", "pypi", "npm", "err_snippet"),
    [
        ("1.2.0", "1.2.1", {"version": "1.2.0"}, "expected '1.2.0'"),
        ("1.2.0rc1", "1.2.0rc1", {"version": "1.2.0rc1"}, "expected '1.2.0-rc.1'"),
        ("1.2.0", None, {"version": "1.2.0"}, "is missing"),
        ("1.2.0", "1.2.0", {"name": "x"}, "cannot read the version"),
        ("1.2.0", "1.2.0", "{not json", "cannot read the version"),
        ("1.2.0", "1.2.0", ["1.2.0"], "cannot read the version"),
        ("v1.2.0", "1.2.0", {"version": "1.2.0"}, "invalid release tag"),
    ],
)
def test_main_check_fails(
    release_version,
    manifests,
    capsys: pytest.CaptureFixture,
    tag: str,
    pypi: str | None,
    npm: object,
    err_snippet: str,
) -> None:
    """Test --check fails, printing nothing to stdout, on any mismatch."""
    assert release_version.main([tag, "--check", *manifests(pypi, npm)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert err_snippet in captured.err


def test_main_check_missing_package_json(
    release_version, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Test --check reports an absent package.json instead of raising."""
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.2.0")
    argv = ["1.2.0", "--check", "--version-file", str(version_file)]
    argv += ["--package-json", str(tmp_path / "package.json")]
    assert release_version.main(argv) == 1
    assert "cannot read the version" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [[], ["1.2.0", "--dev", "abc1234"]])
def test_main_requires_one_source(release_version, argv: list[str]) -> None:
    """Test exactly one of a tag or --dev is required."""
    with pytest.raises(SystemExit):
        release_version.main(argv)


def test_script_runs_standalone() -> None:
    """Test the script runs as a file, as CI invokes it."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "1.2.0a2"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "npm_version=1.2.0-alpha.2" in result.stdout.splitlines()
