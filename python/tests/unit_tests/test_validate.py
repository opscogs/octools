"""Tests for octools.validate."""

import dataclasses

import pytest

from octools import (
    ALIAS_OF_KEY,
    SCHEMA_ESCAPE_KEY,
    OCTool,
    count_sentences,
    example,
    validate_provider,
    validate_tool,
)
from octools.example import ECHO_ALIAS, ECHO_RECORDS, RENDER_BADGE, TOOLS
from tests.support import build_tool

CLOSED = {"type": "object", "properties": {}, "additionalProperties": False}
GOOD_DESCRIPTION = "Does one thing well. Returns a closed object."


def handler(_dependency: None) -> dict:
    return {}


def make(**overrides) -> OCTool:
    fields = {
        "description": GOOD_DESCRIPTION,
        "func": handler,
        "input_schema": CLOSED,
        "output_schema": CLOSED,
    }
    fields.update(overrides)
    return build_tool(**fields)


class ListProvider:
    def __init__(self, *tools):
        self.tools = tools

    def all_tools(self):
        return self.tools


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("One.", 1),
        ("One. Two.", 2),
        ("One! Two? Three.", 3),
        ("No terminal punctuation", 0),
        ("Ends with ellipsis... then more. ", 2),
        ("Version 2.10 is fine. Really.", 2),
        (ECHO_RECORDS.description, 3),
    ],
)
def test_count_sentences(text, expected):
    assert count_sentences(text) == expected


def test_conforming_tool_has_no_findings():
    assert validate_tool(make()) == []


@pytest.mark.parametrize("tool", TOOLS)
def test_example_tools_conform(tool):
    assert validate_tool(tool) == []


@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        ({"description": "One sentence only."}, "description_sentences"),
        ({"description": "A. B. C. D. E."}, "description_sentences"),
        ({"input_schema": {"type": "object"}}, "open_object"),
        ({"input_schema": {**CLOSED, "title": "T"}}, "title_present"),
        ({"output_schema": None}, "output_schema_escape"),
        (
            {"output_schema": {"type": "object", "additionalProperties": True}},
            "output_schema_escape",
        ),
        (
            {"output_schema": None, "meta": {SCHEMA_ESCAPE_KEY: ""}},
            "output_schema_escape",
        ),
        (
            {"output_schema": None, "meta": {SCHEMA_ESCAPE_KEY: 3}},
            "output_schema_escape",
        ),
        ({"result_kind": "artifact"}, "artifact_envelope"),
        (
            {
                "result_kind": "artifact",
                "output_schema": None,
                "meta": {SCHEMA_ESCAPE_KEY: "x"},
            },
            "artifact_envelope",
        ),
        ({"deprecated": True}, "deprecated_alias"),
        (
            {"deprecated": True, "meta": {ALIAS_OF_KEY: "sample_tool"}},
            "deprecated_alias",
        ),
        ({"deprecated": True, "meta": {ALIAS_OF_KEY: 5}}, "deprecated_alias"),
    ],
)
def test_single_rule(overrides, rule):
    findings = validate_tool(make(**overrides))
    assert [f.rule for f in findings] == [rule]
    assert findings[0].tool == "sample_tool"


def test_input_schema_findings_carry_prefixed_path():
    tool = make(
        input_schema={**CLOSED, "properties": {"n": {"type": "integer", "minimum": 1}}}
    )
    (finding,) = validate_tool(tool)
    assert finding.rule == "unsupported_keyword"
    assert finding.path == "/input_schema/properties/n"


def test_escape_reason_accepted():
    tool = make(output_schema=None, meta={SCHEMA_ESCAPE_KEY: "free-form SQL result"})
    assert validate_tool(tool) == []
    open_tool = make(
        output_schema={"type": "object", "additionalProperties": True},
        meta={SCHEMA_ESCAPE_KEY: "caller chooses _return_fields"},
    )
    assert validate_tool(open_tool) == []


def test_name_rule_reported_for_corrupted_descriptor():
    tool = make()
    object.__setattr__(tool, "name", "Not-Valid")
    assert [f.rule for f in validate_tool(tool)] == ["name_pattern"]


def test_multiple_findings_reported_together():
    tool = make(description="Short.", output_schema=None, deprecated=True)
    assert [f.rule for f in validate_tool(tool)] == [
        "description_sentences",
        "output_schema_escape",
        "deprecated_alias",
    ]


@pytest.mark.parametrize("provider", [example, example.ExampleProvider()])
def test_example_conforms(provider):
    assert validate_provider(provider) == []


def test_provider_alias_target_missing():
    findings = validate_provider(ListProvider(ECHO_ALIAS, RENDER_BADGE))
    assert [(f.rule, f.tool) for f in findings] == [("alias_target_missing", "echo")]


def test_provider_reports_listing_and_foreign_items():
    findings = validate_provider(ListProvider(ECHO_RECORDS, ECHO_RECORDS, "nope"))
    assert [f.rule for f in findings] == ["duplicate_name", "not_octool"]
    assert findings[1].message.startswith("all_tools()[2] is str")


def test_provider_collects_tool_findings():
    bad = dataclasses.replace(make(), description="One.")
    findings = validate_provider(ListProvider(bad, ECHO_RECORDS))
    assert [(f.rule, f.tool) for f in findings] == [
        ("description_sentences", "sample_tool")
    ]
