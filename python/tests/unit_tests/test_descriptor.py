"""Tests for octools.descriptor."""

import dataclasses

import pytest

from octools import (
    ACCESS_FALLBACK,
    ACCESS_KINDS,
    RESULT_KIND_FALLBACK,
    RESULT_KINDS,
    SPEC_VERSION,
    OCTool,
    OCToolError,
    ToolProvider,
    check_tool_listing,
    example,
    merge_providers,
    validate_provider,
)
from octools.example import ECHO_RECORDS, TOOLS, ExampleProvider
from tests.support import build_tool

OBJECT = {"type": "object", "properties": {}, "additionalProperties": False}


def noop(_dependency: None) -> dict:
    return {}


async def async_noop(_dependency: None) -> dict:
    return {}


async def async_stream(_dependency: None):
    yield {}


def make(**overrides) -> OCTool:
    fields = {
        "description": "Does a thing. Returns an object.",
        "func": noop,
        "input_schema": OBJECT,
    }
    fields.update(overrides)
    return build_tool(**fields)


def test_spec_version_and_literals():
    assert SPEC_VERSION == "1.1"
    assert RESULT_KINDS == ("records", "artifact")
    assert ACCESS_KINDS == ("local", "remote")
    assert RESULT_KIND_FALLBACK in RESULT_KINDS
    assert ACCESS_FALLBACK == "remote"


def test_defaults():
    tool = make()
    assert tool.target is None
    assert tool.output_schema is None
    assert tool.result_kind == "records"
    assert tool.title is None
    assert tool.read_only_hint is True
    assert tool.destructive_hint is False
    assert tool.idempotent_hint is True
    assert tool.deprecated is False
    assert tool.meta == {}


def test_frozen():
    tool = make()
    with pytest.raises(dataclasses.FrozenInstanceError):
        tool.name = "other"  # type: ignore[misc]


def test_kw_only():
    with pytest.raises(TypeError):
        OCTool("sample_tool")  # type: ignore[misc]


@pytest.mark.parametrize(
    "name",
    ["a", "cluster_info", "list_items_v2", "a" * 48, "x0_"],
)
def test_valid_names(name):
    assert make(name=name).name == name


@pytest.mark.parametrize(
    "name",
    ["", "Cluster", "1abc", "cluster-info", "cluster.info", "a" * 49, "_x", 42, None],
)
def test_invalid_names(name):
    with pytest.raises(OCToolError, match="name"):
        make(name=name)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"description": ""}, "description"),
        ({"description": "   "}, "description"),
        ({"description": 3}, "description"),
        ({"input_schema": []}, "input_schema must be a mapping"),
        ({"input_schema": {"type": "array"}}, "input_schema root"),
        ({"input_schema": {}}, "input_schema root"),
        ({"output_schema": "x"}, "output_schema must be a mapping"),
        ({"output_schema": {"type": "string"}}, "output_schema root"),
        ({"func": "not callable"}, "func must be callable"),
        ({"func": async_noop}, "func must be synchronous"),
        ({"func": async_stream}, "func must be synchronous"),
        ({"access": "cluster"}, "access must be one of"),
        ({"target": ""}, "target"),
        ({"target": 7}, "target"),
        ({"result_kind": "table"}, "result_kind must be one of"),
        ({"title": ""}, "title"),
        ({"read_only_hint": "yes"}, "read_only_hint must be a bool"),
        ({"destructive_hint": 1}, "destructive_hint must be a bool"),
        ({"idempotent_hint": None}, "idempotent_hint must be a bool"),
        ({"deprecated": "no"}, "deprecated must be a bool"),
        ({"meta": [("a", 1)]}, "meta must be a mapping"),
    ],
)
def test_structural_errors(overrides, match):
    with pytest.raises(OCToolError, match=match):
        make(**overrides)


def test_octoolerror_is_valueerror():
    assert issubclass(OCToolError, ValueError)


def test_optional_fields_accepted():
    tool = make(
        target="cluster",
        title="Sample",
        output_schema=OBJECT,
        result_kind="artifact",
        access="remote",
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        deprecated=True,
        meta={"alias_of": "other"},
    )
    assert (tool.target, tool.title, tool.access) == ("cluster", "Sample", "remote")
    assert tool.result_kind == "artifact"


class ShufflingProvider:
    def __init__(self):
        self.calls = 0

    def all_tools(self):
        self.calls += 1
        return TOOLS if self.calls % 2 else tuple(reversed(TOOLS))


class DuplicatingProvider:
    def all_tools(self):
        return (ECHO_RECORDS, ECHO_RECORDS)


@pytest.mark.parametrize("provider", [example, ExampleProvider()])
def test_tool_provider_protocol(provider):
    assert isinstance(provider, ToolProvider)
    assert check_tool_listing(provider) == []


@pytest.mark.parametrize(
    ("provider", "rules", "check"),
    [
        (
            ShufflingProvider(),
            ["unstable_order"],
            lambda findings: "render_badge" in findings[0].message,
        ),
        (
            DuplicatingProvider(),
            ["duplicate_name"],
            lambda findings: findings[0].tool == "echo_records",
        ),
    ],
)
def test_check_tool_listing_findings(provider, rules, check):
    for findings in (check_tool_listing(provider), validate_provider(provider)):
        assert [f.rule for f in findings] == rules
        assert check(findings)


class OneToolProvider:
    def __init__(self, tool):
        self.tool = tool

    def all_tools(self):
        return (self.tool,)


def test_merge_providers_concatenates_in_argument_order():
    badge = OneToolProvider(TOOLS[-1])
    merged = merge_providers(OneToolProvider(ECHO_RECORDS), badge)
    assert isinstance(merged, ToolProvider)
    assert [t.name for t in merged.all_tools()] == ["echo_records", "render_badge"]
    assert check_tool_listing(merged) == []
    assert validate_provider(merged) == []


def test_merge_providers_of_nothing_lists_nothing():
    assert merge_providers().all_tools() == ()


def test_merge_providers_reports_a_collision_rather_than_hiding_it():
    merged = merge_providers(example, OneToolProvider(ECHO_RECORDS))
    assert [f.rule for f in check_tool_listing(merged)] == ["duplicate_name"]
    findings = validate_provider(merged)
    assert [f.rule for f in findings] == ["duplicate_name"]
    assert findings[0].tool == "echo_records"


def test_merge_providers_still_sees_an_unstable_member():
    merged = merge_providers(ShufflingProvider())
    assert [f.rule for f in check_tool_listing(merged)] == ["unstable_order"]
    assert [f.rule for f in validate_provider(merged)] == ["unstable_order"]
