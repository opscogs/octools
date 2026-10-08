"""Tests for octools.convert."""

import copy

import pytest

from octools import (
    MCP_META_NAMESPACE,
    SPEC_VERSION,
    OCTool,
    OCToolError,
    to_anthropic_tool,
    to_mcp_tool,
)
from octools.example import ECHO_RECORDS, RENDER_BADGE, TOOLS

INPUT = {
    "type": "object",
    "title": "Args",
    "properties": {"q": {"type": "string", "title": "Q", "x-sensitivity": "free_text"}},
    "required": ["q"],
}


def handler(_dependency: None, *, q: str) -> dict:
    return {"q": q}


REMOTE = OCTool(
    name="cluster_info",
    title="Cluster identity",
    description="Return the cluster's name. Read-only, one call.",
    input_schema=INPUT,
    output_schema={"type": "object", "additionalProperties": True},
    func=handler,
    access="remote",
    target="cluster",
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    meta={"min_api_version": "2.10", "schema_escape": "caller-shaped read"},
)


def test_mcp_full_mapping():
    mcp = to_mcp_tool(REMOTE)
    assert mcp == {
        "name": "cluster_info",
        "title": "Cluster identity",
        "description": REMOTE.description,
        "inputSchema": INPUT,
        "outputSchema": {"type": "object", "additionalProperties": True},
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
        },
        "_meta": {
            f"{MCP_META_NAMESPACE}spec_version": SPEC_VERSION,
            f"{MCP_META_NAMESPACE}access": "remote",
            f"{MCP_META_NAMESPACE}result_kind": "records",
            f"{MCP_META_NAMESPACE}deprecated": False,
            f"{MCP_META_NAMESPACE}meta": {
                "min_api_version": "2.10",
                "schema_escape": "caller-shaped read",
            },
            f"{MCP_META_NAMESPACE}target": "cluster",
        },
    }


def test_mcp_omits_unset_optionals():
    mcp = to_mcp_tool(ECHO_RECORDS)
    assert "target" not in {k.split("/")[-1] for k in mcp["_meta"]}
    tool = OCTool(
        name="bare",
        description="Bare tool. Nothing optional.",
        input_schema={"type": "object"},
        func=handler,
        access="local",
    )
    mcp = to_mcp_tool(tool)
    assert "title" not in mcp
    assert "outputSchema" not in mcp


def test_mcp_schemas_are_independent_copies():
    mcp = to_mcp_tool(RENDER_BADGE)
    mcp["inputSchema"]["properties"]["label"]["description"] = "changed"
    mcp["_meta"][f"{MCP_META_NAMESPACE}meta"]["renderer"] = "changed"
    assert RENDER_BADGE.input_schema["properties"]["label"]["description"] != "changed"
    assert RENDER_BADGE.meta["renderer"] == "svgstatic"


def test_mcp_meta_key_order_is_stable():
    keys = list(to_mcp_tool(RENDER_BADGE)["_meta"])
    assert keys[0] == f"{MCP_META_NAMESPACE}spec_version"


@pytest.mark.parametrize("tool", TOOLS)
def test_mcp_lossless_round_trip(tool):
    mcp = to_mcp_tool(tool)
    rebuilt = OCTool(
        name=mcp["name"],
        title=mcp.get("title"),
        description=mcp["description"],
        input_schema=mcp["inputSchema"],
        output_schema=mcp.get("outputSchema"),
        func=tool.func,
        access=mcp["_meta"][f"{MCP_META_NAMESPACE}access"],
        target=mcp["_meta"].get(f"{MCP_META_NAMESPACE}target"),
        result_kind=mcp["_meta"][f"{MCP_META_NAMESPACE}result_kind"],
        read_only_hint=mcp["annotations"]["readOnlyHint"],
        destructive_hint=mcp["annotations"]["destructiveHint"],
        idempotent_hint=mcp["annotations"]["idempotentHint"],
        deprecated=mcp["_meta"][f"{MCP_META_NAMESPACE}deprecated"],
        meta=mcp["_meta"][f"{MCP_META_NAMESPACE}meta"],
    )
    assert rebuilt == tool


def test_anthropic_mapping_strips_and_closes():
    entry = to_anthropic_tool(REMOTE, name_prefix="demo_")
    assert entry == {
        "name": "demo_cluster_info",
        "description": REMOTE.description,
        "input_schema": {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
            "additionalProperties": False,
        },
    }
    assert set(entry) == {"name", "description", "input_schema"}
    assert REMOTE.input_schema["title"] == "Args"


def test_anthropic_keeps_existing_closure():
    entry = to_anthropic_tool(ECHO_RECORDS)
    assert entry["name"] == "echo_records"
    assert entry["input_schema"]["additionalProperties"] is False
    assert entry["input_schema"] is not ECHO_RECORDS.input_schema


@pytest.mark.parametrize("convert", [to_anthropic_tool, to_mcp_tool])
@pytest.mark.parametrize("prefix", ["", "x" * 116])
def test_name_prefix_length_allows_128_characters(convert, prefix):
    entry = convert(REMOTE, name_prefix=prefix)
    assert entry["name"] == f"{prefix}cluster_info"
    if convert is to_mcp_tool:
        assert {**entry, "name": REMOTE.name} == to_mcp_tool(REMOTE)


def test_anthropic_name_prefix_allows_hyphen():
    entry = to_anthropic_tool(REMOTE, name_prefix="Site-A_")
    assert entry["name"] == "Site-A_cluster_info"


@pytest.mark.parametrize("prefix", ["site_a_", "Site-A."])
def test_mcp_name_prefix_allows_its_alphabet(prefix):
    entry = to_mcp_tool(REMOTE, name_prefix=prefix)
    assert entry["name"] == f"{prefix}cluster_info"
    assert {**entry, "name": REMOTE.name} == to_mcp_tool(REMOTE)


@pytest.mark.parametrize(
    ("convert", "prefix"),
    [
        (to_anthropic_tool, "x" * 117),
        (to_anthropic_tool, "bad.prefix_"),
        (to_anthropic_tool, "spaced "),
        (to_mcp_tool, "x" * 117),
        (to_mcp_tool, "bad/prefix_"),
        (to_mcp_tool, "spaced "),
    ],
)
def test_name_prefix_rule(convert, prefix):
    with pytest.raises(OCToolError, match="does not match"):
        convert(ECHO_RECORDS, name_prefix=prefix)


@pytest.mark.parametrize("convert", [to_anthropic_tool, to_mcp_tool])
def test_name_rule_rejects_trailing_newline(convert):
    tool = copy.copy(ECHO_RECORDS)
    object.__setattr__(tool, "name", f"{ECHO_RECORDS.name}\n")
    with pytest.raises(OCToolError, match="does not match"):
        convert(tool)
