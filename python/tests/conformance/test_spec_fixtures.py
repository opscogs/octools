"""Every fixture under spec/fixtures/ passes against the Python implementation."""

import json
from pathlib import Path

import pytest

from tests.conformance.runners import RUNNERS, run

SPEC = Path(__file__).resolve().parents[3] / "spec"
FIXTURES = SPEC / "fixtures"
FIXTURE_PATHS = sorted(FIXTURES.glob("*/*.json"))
FIXTURE_KEYS = {"description", "input", "expected"}


def fixture_id(path: Path) -> str:
    return path.relative_to(FIXTURES).as_posix()


def test_fixtures_exist_for_every_runner_and_only_as_files():
    operations = {path.name for path in FIXTURES.iterdir() if path.is_dir()}
    assert operations == set(RUNNERS)
    stray = [
        fixture_id(path)
        for path in FIXTURES.rglob("*")
        if path.is_file() and path not in FIXTURE_PATHS
    ]
    assert stray == []


@pytest.mark.parametrize("path", FIXTURE_PATHS, ids=fixture_id)
def test_fixture(path: Path):
    fixture = json.loads(path.read_text())
    assert set(fixture) == FIXTURE_KEYS
    assert isinstance(fixture["description"], str) and fixture["description"]
    assert run(path.parent.name, fixture["input"]) == fixture["expected"]
