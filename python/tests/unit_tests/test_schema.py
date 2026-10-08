"""Tests for octools.schema."""

from typing import Annotated

import pytest
from pydantic import BaseModel, ConfigDict, Field

from octools import (
    SCHEMA_DIALECT,
    STRICT_FORMATS,
    STRICT_KEYWORDS,
    STRICT_TYPES,
    Finding,
    NoTitleGenerator,
    close_objects,
    input_schema_for,
    output_schema_for,
    schema_for,
    strict_clean,
    strip_keys,
    strip_titles,
)

SENS = {"x-sensitivity": "identifier"}


class Member(BaseModel):
    host_name: Annotated[str, Field(description="Member FQDN.", json_schema_extra=SENS)]
    vip: str | None = Field(default=None, description="Management IPv4.")


class Args(BaseModel):
    include_members: bool = Field(default=False, description="Also list members.")
    when: str = Field(
        description="ISO timestamp.", json_schema_extra={"format": "date-time"}
    )
    tags: list[str] = Field(default_factory=list, description="Filter tags.")
    mode: str = Field(default="fast", json_schema_extra={"enum": ["fast", "full"]})


class Nested(BaseModel):
    member: Member | None = None
    title: str = Field(description="A property literally named title.")
    options: dict[str, int] = Field(default_factory=dict)


class Forbidding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: int


class Bounded(BaseModel):
    max_results: int = Field(default=10, ge=1, le=1000)
    name: str = Field(min_length=1)


class Node(BaseModel):
    children: list["Node"] = Field(default_factory=list)


class Tree(BaseModel):
    root: Node


def _keys(node, found=None):
    found = set() if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            if key not in {"properties", "$defs"}:
                _keys(value, found)
            else:
                for sub in value.values():
                    _keys(sub, found)
    elif isinstance(node, list):
        for item in node:
            _keys(item, found)
    return found


def test_dialect_constant():
    assert SCHEMA_DIALECT.endswith("2020-12/schema")


@pytest.mark.parametrize("model", [Member, Args, Nested])
def test_schema_for_has_no_titles(model):
    assert "title" not in _keys(schema_for(model))
    assert "title" in _keys(model.model_json_schema())


def test_generator_direct_use():
    schema = Member.model_json_schema(schema_generator=NoTitleGenerator)
    assert "title" not in schema
    assert "title" not in schema["properties"]["host_name"]


def test_extension_passthrough():
    schema = output_schema_for(Member)
    assert schema["properties"]["host_name"]["x-sensitivity"] == "identifier"


def test_property_named_title_survives():
    schema = input_schema_for(Nested)
    assert "title" in schema["properties"]
    assert "title" not in schema["properties"]["title"]


def test_input_schema_closes_model_objects_but_not_dicts():
    schema = input_schema_for(Nested)
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["Member"]["additionalProperties"] is False
    assert "additionalProperties" not in schema["properties"]["options"] or isinstance(
        schema["properties"]["options"]["additionalProperties"], dict
    )


def test_input_schema_keeps_existing_closure():
    schema = input_schema_for(Forbidding)
    assert schema["additionalProperties"] is False


def test_output_schema_is_not_closed():
    assert "additionalProperties" not in output_schema_for(Member)


def test_optional_field_shape():
    schema = input_schema_for(Member)
    vip = schema["properties"]["vip"]
    assert vip["anyOf"] == [{"type": "string"}, {"type": "null"}]
    assert vip["default"] is None
    assert schema["required"] == ["host_name"]


def test_strip_titles_returns_copy_and_preserves_data_values():
    original = {
        "type": "object",
        "title": "T",
        "properties": {
            "a": {"type": "string", "title": "A", "default": {"title": "keep"}}
        },
        "enum": [{"title": "keep"}],
    }
    stripped = strip_titles(original)
    assert stripped == {
        "type": "object",
        "properties": {"a": {"type": "string", "default": {"title": "keep"}}},
        "enum": [{"title": "keep"}],
    }
    assert original["title"] == "T"
    assert (
        stripped["properties"]["a"]["default"]
        is not original["properties"]["a"]["default"]
    )


def test_strip_keys_prefixes():
    schema = output_schema_for(Member)
    clean = strip_keys(schema, prefixes=("x-",))
    assert "x-sensitivity" not in clean["properties"]["host_name"]
    assert "x-sensitivity" in schema["properties"]["host_name"]


def test_close_objects_only_where_properties():
    schema = {"type": "object", "properties": {"m": {"type": "object"}}}
    closed = close_objects(schema)
    assert closed["additionalProperties"] is False
    assert "additionalProperties" not in closed["properties"]["m"]


def test_strict_constant_sets():
    assert {"type", "$ref", "$defs", "minItems"} <= STRICT_KEYWORDS
    assert "minimum" not in STRICT_KEYWORDS
    assert {
        "object",
        "array",
        "string",
        "integer",
        "number",
        "boolean",
        "null",
    } == STRICT_TYPES
    assert len(STRICT_FORMATS) == 10


@pytest.mark.parametrize("model", [Args, Forbidding])
def test_strict_clean_passes_generated_input_schema(model):
    assert strict_clean(input_schema_for(model)) == []


def test_strict_clean_does_not_mutate():
    schema = input_schema_for(Bounded)
    before = repr(schema)
    findings = strict_clean(schema)
    assert findings != []
    assert {finding.rule for finding in findings} == {"unsupported_keyword"}
    assert repr(schema) == before


@pytest.mark.parametrize(
    ("schema", "rules"),
    [
        ({"type": "array"}, ["root_not_object"]),
        ("nope", ["root_not_object"]),
        ({"type": "object", "additionalProperties": False, "$defs": 3}, ["bad_defs"]),
        ({"type": "object"}, ["open_object"]),
        ({"type": "object", "additionalProperties": True}, ["open_object"]),
        (
            {"type": "object", "additionalProperties": False, "title": "T"},
            ["title_present"],
        ),
        (
            {"type": "object", "additionalProperties": False, "x-sensitivity": "n"},
            ["extension_key"],
        ),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"n": {"type": "integer", "minimum": 1}},
            },
            ["unsupported_keyword"],
        ),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"n": {"type": "money"}},
            },
            ["unsupported_type"],
        ),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"n": {"type": ["string", "money"]}},
            },
            ["unsupported_type"],
        ),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"n": {"type": "string", "format": "binary"}},
            },
            ["unsupported_format"],
        ),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"n": {"type": "array", "items": {}, "minItems": 2}},
            },
            ["min_items"],
        ),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"n": {"enum": [{"a": 1}]}},
            },
            ["enum_not_primitive"],
        ),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"n": {"enum": "ab"}},
            },
            ["enum_not_primitive"],
        ),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"n": {"$ref": "#/$defs/Missing"}},
            },
            ["unknown_ref"],
        ),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"n": {"$ref": "https://example.com/x.json"}},
            },
            ["unknown_ref"],
        ),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "$defs": {"A": {"type": "string"}},
                "properties": {"n": {"allOf": [{"$ref": "#/$defs/A"}]}},
            },
            ["allof_ref"],
        ),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"n": {"type": "array", "items": True}},
            },
            ["boolean_schema"],
        ),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "n": {"type": "object", "additionalProperties": False, "$defs": {}}
                },
            },
            ["defs_not_at_root"],
        ),
        (
            {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            ["open_object"],
        ),
    ],
)
def test_strict_clean_rules(schema, rules):
    findings = strict_clean(schema)
    assert [f.rule for f in findings] == rules
    assert all(isinstance(f, Finding) and f.tool is None for f in findings)


def test_strict_clean_paths():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "a": {"anyOf": [{"type": "string", "maxLength": 3}, {"type": "null"}]}
        },
    }
    (finding,) = strict_clean(schema)
    assert finding.path == "/properties/a/anyOf/0"


def test_strict_clean_bounds_from_pydantic():
    rules = {f.rule for f in strict_clean(input_schema_for(Bounded))}
    assert rules == {"unsupported_keyword"}


def test_strict_clean_recursion():
    schema = input_schema_for(Tree)
    findings = [f for f in strict_clean(schema) if f.rule == "recursive_ref"]
    assert [f.path for f in findings] == ["/$defs/Node"]


def test_self_referencing_root_is_a_ref_not_an_object():
    assert [f.rule for f in strict_clean(input_schema_for(Node))] == ["root_not_object"]


def test_strip_titles_tolerates_boolean_members():
    schema = {"type": "object", "anyOf": [True, {"type": "null", "title": "N"}]}
    assert strip_titles(schema) == {"type": "object", "anyOf": [True, {"type": "null"}]}


def test_strict_clean_mutual_recursion():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "$defs": {
            "A": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"b": {"$ref": "#/$defs/B"}},
            },
            "B": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"a": {"$ref": "#/$defs/A"}},
            },
            "C": {"type": "string"},
        },
        "properties": {"a": {"$ref": "#/$defs/A"}},
    }
    recursive = sorted(
        f.path for f in strict_clean(schema) if f.rule == "recursive_ref"
    )
    assert recursive == ["/$defs/A", "/$defs/B"]


def test_strict_clean_cycle_revisits_seen_node():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "$defs": {
            "A": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"b": {"$ref": "#/$defs/B"}},
            },
            "B": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"c": {"$ref": "#/$defs/C"}},
            },
            "C": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"b": {"$ref": "#/$defs/B"}},
            },
        },
        "properties": {"a": {"$ref": "#/$defs/A"}},
    }
    recursive = sorted(
        f.path for f in strict_clean(schema) if f.rule == "recursive_ref"
    )
    assert recursive == ["/$defs/B", "/$defs/C"]
