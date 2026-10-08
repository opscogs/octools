"""End-to-end: the demo provider validates, runs, and converts both ways."""

import json

import pytest

from octools import (
    MCP_META_NAMESPACE,
    ArtifactEnvelope,
    RecordsEnvelope,
    TabularEnvelope,
    example,
    read_envelope,
    to_anthropic_tool,
    to_mcp_tool,
    validate_provider,
    validate_tabular,
)
from octools.example import (
    BLOCK_SIZES,
    ECHO_RECORDS,
    RENDER_BADGE,
    TOOLS,
    EchoRecord,
    memory_sink,
)


def test_echo_records_runs_and_matches_schema():
    result = ECHO_RECORDS.func(None, values=["a", "b", "c"], limit=2)
    assert result == {
        "records": [{"value": "a", "position": 0}, {"value": "b", "position": 1}],
        "count": 2,
        "truncated": True,
        "total_count": 3,
        "next_cursor": "2",
        "resumable": True,
    }
    RecordsEnvelope[EchoRecord].model_validate(result)
    assert set(result) | {"stop_reason", "warnings"} == set(
        ECHO_RECORDS.output_schema["properties"]
    )


def test_echo_records_pages_to_the_end_with_the_cursor():
    first = ECHO_RECORDS.func(None, values=["a", "b", "c"], limit=2)
    last = ECHO_RECORDS.func(
        None, values=["a", "b", "c"], limit=2, cursor=first["next_cursor"]
    )
    assert last == {
        "records": [{"value": "c", "position": 2}],
        "count": 1,
        "truncated": False,
        "total_count": 3,
    }
    RecordsEnvelope[EchoRecord].model_validate(last)
    assert "cursor" in ECHO_RECORDS.input_schema["properties"]


@pytest.mark.parametrize("limit", [0, 101])
def test_echo_records_enforces_bounds_outside_schema(limit):
    assert "minimum" not in json.dumps(ECHO_RECORDS.input_schema)
    with pytest.raises(ValueError, match="limit"):
        ECHO_RECORDS.func(None, values=["a"], limit=limit)


@pytest.mark.parametrize("cursor", ["-1", "abc", "1.5"])
def test_echo_records_rejects_foreign_cursors(cursor):
    with pytest.raises(ValueError, match="cursor"):
        ECHO_RECORDS.func(None, values=["a"], cursor=cursor)


def test_block_sizes_uses_the_block_kinds_and_scale():
    result = BLOCK_SIZES.func(None, prefixes=["192.0.2.1/24", "2001:db8::/32"])
    assert result == {
        "columns": ["prefix", "prefix_len", "size"],
        "rows": [
            ["192.0.2.0/24", 24, 256],
            ["2001:db8::/32", 32, "79228162514264337593543950336"],
        ],
        "row_count": 2,
        "truncated": False,
        "column_kinds": ["ip_block", "integer", "big_integer"],
        "column_scales": [None, None, "log2"],
    }
    env = TabularEnvelope.model_validate(result)
    assert validate_tabular(env) == []
    assert read_envelope(TabularEnvelope, result) == env
    assert set(result) <= set(BLOCK_SIZES.output_schema["properties"])


def test_render_badge_writes_through_sink():
    store: dict[str, bytes] = {}
    result = RENDER_BADGE.func(memory_sink(store), label="build", value="passing")
    env = ArtifactEnvelope.model_validate(result)
    assert env.artifact.reference == "mem://0.svg"
    assert env.artifact.bytes == len(store["mem://0.svg"])
    assert store["mem://0.svg"].startswith(b"<svg")
    assert env.sensitivity == "inherits_input"


@pytest.mark.parametrize("tool", TOOLS)
def test_round_trips_through_both_converters(tool):
    assert validate_provider(example) == []
    mcp = to_mcp_tool(tool, name_prefix="demo_")
    anthropic = to_anthropic_tool(tool, name_prefix="demo_")
    assert mcp["name"] == f"demo_{tool.name}"
    assert mcp["inputSchema"] == tool.input_schema
    assert anthropic["name"] == f"demo_{tool.name}"
    assert anthropic["input_schema"]["additionalProperties"] is False
    assert "x-sensitivity" not in json.dumps(anthropic["input_schema"])
    json.dumps(mcp)
    json.dumps(anthropic)


def test_mcp_marks_artifact_and_deprecated_tools():
    by_name = {t["name"]: t for t in map(to_mcp_tool, TOOLS)}
    badge, echo = by_name["render_badge"]["_meta"], by_name["echo"]["_meta"]
    assert badge[f"{MCP_META_NAMESPACE}result_kind"] == "artifact"
    assert echo[f"{MCP_META_NAMESPACE}deprecated"] is True
    assert echo[f"{MCP_META_NAMESPACE}meta"] == {"alias_of": "echo_records"}
