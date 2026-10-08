"""Test scripts/sync_upstream_requests.py."""

import json
from datetime import date
from pathlib import Path

import pytest

from scripts.tests.support import load_script, unload_script


@pytest.fixture(scope="module")
def sync_upstream_requests():
    """Load the sync script under a private module name."""
    name, module = load_script("sync_upstream_requests.py")
    yield module
    unload_script(name)


ISSUE_PLANNED = {
    "number": 1,
    "title": "DEMO-UR-0001 Add a duration value to column_kinds",
    "labels": [
        {"name": "upstream-request"},
        {"name": "ur:planned"},
        {"name": "consumer:demo_tools"},
    ],
    "milestone": {"title": "0.2.0"},
    "createdAt": "2026-09-02T10:00:00Z",
    "closedAt": None,
    "state": "OPEN",
}

ISSUE_DELIVERED_AND_CLOSED = {
    "number": 2,
    "title": "DEMO-UR-0002 Promote TabularEnvelope as a shared ref",
    "labels": [
        {"name": "upstream-request"},
        {"name": "ur:delivered"},
        {"name": "consumer:demo_tools"},
    ],
    "milestone": {"title": "0.1.0"},
    "createdAt": "2026-08-20T09:30:00Z",
    "closedAt": "2026-09-01T00:00:00Z",
    "state": "CLOSED",
}

ISSUE_BLOCKING_DECLINED = {
    "number": 5,
    "title": "DEMO-UR-0005 Publish a vendor-specific helper",
    "labels": [
        {"name": "upstream-request"},
        {"name": "ur:blocking"},
        {"name": "ur:declined"},
        {"name": "consumer:demo_tools"},
    ],
    "milestone": None,
    "createdAt": "2026-09-04T00:00:00Z",
    "closedAt": "2026-09-05T00:00:00Z",
    "state": "CLOSED",
}

ISSUE_WITHDRAWN = {
    "number": 6,
    "title": "DEMO-UR-0006 Add a helper the consumer no longer needs",
    "labels": [
        {"name": "upstream-request"},
        {"name": "ur:withdrawn"},
        {"name": "consumer:demo_tools"},
    ],
    "milestone": None,
    "createdAt": "2026-09-04T00:00:00Z",
    "closedAt": "2026-09-06T00:00:00Z",
    "state": "CLOSED",
}

ISSUE_NO_ID = {
    "number": 3,
    "title": "No id anywhere in this title",
    "labels": [{"name": "upstream-request"}, {"name": "ur:filed"}],
    "milestone": None,
    "createdAt": "2026-09-03T00:00:00Z",
    "closedAt": None,
    "state": "OPEN",
}

ISSUE_NO_UR_LABEL = {
    "number": 4,
    "title": "DEMO-UR-0004 Missing its state label",
    "labels": [
        {"name": "upstream-request"},
        {"name": "ur:blocking"},
        {"name": "consumer:demo_tools"},
    ],
    "milestone": None,
    "createdAt": "2026-09-04T00:00:00Z",
    "closedAt": None,
    "state": "OPEN",
}

ALL_ISSUES = [ISSUE_PLANNED, ISSUE_DELIVERED_AND_CLOSED, ISSUE_NO_ID, ISSUE_NO_UR_LABEL]


def make_runner(issues: list[dict]):
    """Return a fake runner(argv) -> str returning issues as gh-style JSON."""

    def _runner(argv: list[str]) -> str:
        assert argv[0] == "gh"
        return json.dumps(issues)

    return _runner


def test_build_records_skips_no_id_and_no_ur_label(
    sync_upstream_requests, capsys: pytest.CaptureFixture
) -> None:
    """Test build_records skips a titleless-id issue and a labelless issue, warning."""
    records = sync_upstream_requests.build_records(ALL_ISSUES, date(2026, 9, 5))
    ids = [r["id"] for r in records]
    assert ids == ["DEMO-UR-0002", "DEMO-UR-0001"]
    err = capsys.readouterr().err
    assert "issue #3" in err
    assert "issue #4" in err


def test_build_records_sorted_by_filed_newest_last(sync_upstream_requests) -> None:
    """Test records sort by filed date then id, with the newest last."""
    records = sync_upstream_requests.build_records(ALL_ISSUES, date(2026, 9, 5))
    assert [r["filed"] for r in records] == ["2026-08-20", "2026-09-02"]


@pytest.mark.parametrize(
    ("issue", "state", "issue_state"),
    [
        (ISSUE_PLANNED, "planned", "open"),
        (ISSUE_DELIVERED_AND_CLOSED, "delivered", "closed"),
        (ISSUE_BLOCKING_DECLINED, "declined", "closed"),
        (ISSUE_WITHDRAWN, "withdrawn", "closed"),
    ],
)
def test_build_record_state(
    sync_upstream_requests, issue: dict, state: str, issue_state: str
) -> None:
    """Test state is the ur: state label suffix and issue_state is open/closed."""
    record = sync_upstream_requests.build_record(issue, date(2026, 9, 5))
    assert record is not None
    assert record["state"] == state
    assert record["issue_state"] == issue_state


def test_build_record_fields(sync_upstream_requests) -> None:
    """Test every mirror field is populated from the raw issue as documented."""
    record = sync_upstream_requests.build_record(
        ISSUE_DELIVERED_AND_CLOSED, date(2026, 9, 5)
    )
    assert record == {
        "id": "DEMO-UR-0002",
        "issue": 2,
        "consumer": "demo_tools",
        "title": "Promote TabularEnvelope as a shared ref",
        "state": "delivered",
        "issue_state": "closed",
        "milestone": "0.1.0",
        "filed": "2026-08-20",
        "synced": "2026-09-05",
    }


def test_main_writes_mirror_file(sync_upstream_requests, tmp_path: Path) -> None:
    """Test main() writes the JSONL mirror, sorted, newest last, parent created."""
    output = tmp_path / "nested" / "requests.jsonl"
    exit_code = sync_upstream_requests.main(
        ["--output", str(output)],
        runner=make_runner(ALL_ISSUES),
        today=date(2026, 9, 5),
    )
    assert exit_code == 0
    lines = output.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert [r["id"] for r in records] == ["DEMO-UR-0002", "DEMO-UR-0001"]
    assert all(r["synced"] == "2026-09-05" for r in records)


def test_check_clean_ignores_synced(sync_upstream_requests, tmp_path: Path) -> None:
    """Test --check passes when only the synced date differs from disk."""
    output = tmp_path / "requests.jsonl"
    sync_upstream_requests.main(
        ["--output", str(output)],
        runner=make_runner(ALL_ISSUES),
        today=date(2026, 9, 5),
    )
    exit_code = sync_upstream_requests.main(
        ["--output", str(output), "--check"],
        runner=make_runner(ALL_ISSUES),
        today=date(2026, 9, 6),
    )
    assert exit_code == 0


def test_check_dirty_when_content_differs(
    sync_upstream_requests, tmp_path: Path
) -> None:
    """Test --check fails when the mirror on disk is stale beyond synced."""
    output = tmp_path / "requests.jsonl"
    sync_upstream_requests.main(
        ["--output", str(output)],
        runner=make_runner([ISSUE_PLANNED]),
        today=date(2026, 9, 5),
    )
    exit_code = sync_upstream_requests.main(
        ["--output", str(output), "--check"],
        runner=make_runner(ALL_ISSUES),
        today=date(2026, 9, 6),
    )
    assert exit_code == 1


def test_check_dirty_when_file_missing(sync_upstream_requests, tmp_path: Path) -> None:
    """Test --check fails when the mirror file does not exist yet."""
    output = tmp_path / "requests.jsonl"
    exit_code = sync_upstream_requests.main(
        ["--output", str(output), "--check"],
        runner=make_runner(ALL_ISSUES),
        today=date(2026, 9, 5),
    )
    assert exit_code == 1


def test_markdown_prints_table_and_writes_nothing(
    sync_upstream_requests, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Test --markdown prints a table to stdout and never touches --output."""
    output = tmp_path / "requests.jsonl"
    exit_code = sync_upstream_requests.main(
        ["--output", str(output), "--markdown"],
        runner=make_runner(ALL_ISSUES),
        today=date(2026, 9, 5),
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "DEMO-UR-0001" in out
    assert "DEMO-UR-0002" in out
    assert not output.exists()


def test_default_runner_shells_out_to_gh(
    sync_upstream_requests, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test the default runner shells out via subprocess.run and returns stdout."""

    class _Completed:
        stdout = "[]"

    captured: dict[str, object] = {}

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _Completed()

    monkeypatch.setattr(sync_upstream_requests.subprocess, "run", _fake_run)
    result = sync_upstream_requests.default_runner(["gh", "issue", "list"])
    assert result == "[]"
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["text"] is True
    assert captured["kwargs"]["check"] is True
