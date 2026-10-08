"""Tool listings: summaries, type rendering, and each rendering style."""

import json

import pytest

from octools import (
    LISTING_STYLES,
    InputSummary,
    OCTool,
    ToolSummary,
    example,
    render_listing,
    render_markdown_table,
    summarize_provider,
    summarize_tool,
)
from octools.example import ECHO_ALIAS, ECHO_RECORDS, ExampleProvider

DESCRIPTION = "Do the thing to a target. Use it when needed. Returns records."


class FakeProvider:
    def __init__(self, *tools):
        self.tools = tools

    def all_tools(self):
        return self.tools


def make_tool(**overrides):
    fields = {
        "name": "do_thing",
        "description": DESCRIPTION,
        "input_schema": {"type": "object"},
        "func": lambda: None,
        "access": "remote",
    } | overrides
    return OCTool(**fields)


def input_type(prop):
    tool = make_tool(input_schema={"type": "object", "properties": {"x": prop}})
    return summarize_tool(tool).inputs[0].type


@pytest.mark.parametrize("style", ["table", "md", "txt"])
@pytest.mark.parametrize("provider", [example, ExampleProvider()])
def test_render_listing_follows_the_summary(provider, style):
    summaries = summarize_provider(provider)
    text = render_listing(provider, style=style)
    flat = " ".join(text.split())
    assert text.endswith("\n")
    assert render_listing(example, style=style) == render_listing(
        ExampleProvider(), style=style
    )
    for summary in summaries:
        assert summary.name in text
        assert summary.summary in flat
        if summary.deprecated and summary.alias_of:
            assert summary.alias_of in text
    if style == "table":
        assert len(text.splitlines()) == len(summaries)
        for summary in summaries:
            if summary.deprecated and summary.alias_of:
                assert f"[deprecated; use {summary.alias_of}]" in text
    elif style == "md":
        lines = text.splitlines()
        assert len(lines) == len(summaries) + 2
        header = [cell.strip() for cell in lines[0].strip("|").split("|")]
        assert header == [
            "name",
            "access",
            "mode",
            "result_kind",
            "pages",
            "deprecated",
            "summary",
        ]
        for summary in summaries:
            row = next(line for line in lines if f"| {summary.name} " in line)
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            assert cells[0] == summary.name
            assert cells[4] == ("yes" if summary.pages else "no")
            assert cells[5] == ("yes" if summary.deprecated else "no")
            assert cells[6] == summary.summary
    else:
        for summary in summaries:
            assert " ".join(summary.description.split()) in flat
            for item in summary.inputs:
                assert item.name in flat


def test_render_listing_defaults_to_table():
    assert render_listing(example) == render_listing(example, style="table")


def test_render_listing_json_is_the_rows():
    text = render_listing(example, style="json")
    assert text.endswith("]\n")
    rows = json.loads(text)
    assert [row["name"] for row in rows] == [
        "echo_records",
        "echo",
        "block_sizes",
        "render_badge",
    ]
    assert rows[0] == summarize_tool(ECHO_RECORDS).as_row()
    assert text == json.dumps(rows, indent=2) + "\n"


def test_as_row_keys_and_values():
    row = summarize_tool(ECHO_ALIAS).as_row()
    assert list(row) == [
        "name",
        "title",
        "summary",
        "description",
        "access",
        "target",
        "result_kind",
        "read_only",
        "destructive",
        "idempotent",
        "pages",
        "deprecated",
        "alias_of",
        "inputs",
    ]
    assert row["alias_of"] == "echo_records"
    assert row["pages"] is True
    assert row["deprecated"] is True
    assert row["inputs"][0] == {
        "name": "values",
        "type": "array[string]",
        "required": True,
        "description": "Strings to echo back, one record each.",
    }


def test_summarize_tool_fields():
    tool = make_tool(
        title="Do thing",
        target="inventory",
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        input_schema={
            "type": "object",
            "properties": {"a": {"type": "string", "description": "An a."}},
            "required": ["a"],
        },
    )
    assert summarize_tool(tool) == ToolSummary(
        name="do_thing",
        title="Do thing",
        summary="Do the thing to a target.",
        description=DESCRIPTION,
        access="remote",
        target="inventory",
        result_kind="records",
        read_only=False,
        destructive=True,
        idempotent=False,
        pages=False,
        deprecated=False,
        alias_of=None,
        inputs=(InputSummary("a", "string", True, "An a."),),
    )


@pytest.mark.parametrize(
    ("description", "summary"),
    [
        ("  One sentence here.  Two!", "One sentence here."),
        ("Stops at the first run?! Then more.", "Stops at the first run?!"),
        ("  No sentence end at all  ", "No sentence end at all"),
        ("Version 1.2 is fine. Next.", "Version 1.2 is fine."),
    ],
)
def test_summary_is_first_sentence(description, summary):
    assert summarize_tool(make_tool(description=description)).summary == summary


@pytest.mark.parametrize("alias", [None, "", 3])
def test_alias_of_needs_non_empty_string(alias):
    tool = make_tool(deprecated=True, meta={} if alias is None else {"alias_of": alias})
    assert summarize_tool(tool).alias_of is None


@pytest.mark.parametrize(
    ("prop", "expected"),
    [
        ({"type": "string"}, "string"),
        ({"type": ["string", "null"]}, "string|null"),
        ({"type": "array", "items": {"type": "integer"}}, "array[integer]"),
        ({"type": "array", "items": "junk"}, "array[any]"),
        ({"type": "array"}, "array"),
        ({"enum": ["a", "b"]}, "enum(a|b)"),
        ({"type": "string", "enum": ["a"]}, "enum(a)"),
        ({"type": "integer", "enum": [1, 2]}, "enum(1|2)"),
        ({"enum": [None, True, 1.5]}, "enum(null|true|1.5)"),
        ({"enum": []}, "enum()"),
        ({"enum": "junk"}, "enum"),
        ({"enum": ["x" * 19, "y" * 20]}, f"enum({'x' * 19}|{'y' * 20})"),
        ({"enum": ["x" * 20, "y" * 20, "z"]}, f"enum({'x' * 20}|...)"),
        ({"enum": ["x" * 41, "y"]}, "enum(...)"),
        ({"anyOf": [{"enum": ["a", "b"]}, {"type": "null"}]}, "enum(a|b)|null"),
        ({"$ref": "#/$defs/Mode"}, "Mode"),
        ({"$ref": "Mode"}, "Mode"),
        ({"anyOf": [{"type": "string"}, {"type": "null"}]}, "string|null"),
        ({"oneOf": [{"$ref": "#/$defs/A"}, {"type": "integer"}]}, "A|integer"),
        ({"anyOf": "junk"}, "any"),
        ({"anyOf": []}, "any"),
        ({"const": 1}, "const(1)"),
        ({"type": "string", "const": "on"}, "const(on)"),
        ({"type": 5}, "any"),
        ({}, "any"),
        ("not a schema", "any"),
    ],
)
def test_input_type_rendering(prop, expected):
    assert input_type(prop) == expected


@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        ({"type": "object"}, ()),
        ({"type": "object", "properties": ["x"]}, ()),
        (
            {"type": "object", "properties": {"x": {}}, "required": "x"},
            (InputSummary("x", "any", False, None),),
        ),
        (
            {"type": "object", "properties": {"x": {"description": 3}, "y": 1}},
            (
                InputSummary("x", "any", False, None),
                InputSummary("y", "any", False, None),
            ),
        ),
    ],
)
def test_inputs_tolerate_odd_schemas(schema, expected):
    assert summarize_tool(make_tool(input_schema=schema)).inputs == expected


def test_summarize_provider_filters_by_access():
    local = make_tool(name="local_one", access="local")
    remote = make_tool(name="remote_one")
    provider = FakeProvider(remote, local)
    assert [s.name for s in summarize_provider(provider)] == [
        "remote_one",
        "local_one",
    ]
    assert [s.name for s in summarize_provider(provider, access="local")] == [
        "local_one"
    ]


@pytest.mark.parametrize(
    ("style", "expected"),
    [
        ("table", ""),
        ("txt", ""),
        ("json", "[]\n"),
        (
            "md",
            (
                "| name | access | mode | result_kind | pages | deprecated "
                "| summary |\n"
                "| ---- | ------ | ---- | ----------- | ----- | ---------- "
                "| ------- |\n"
            ),
        ),
    ],
)
def test_empty_listing(style, expected):
    assert render_listing(example, style=style, access="remote") == expected


@pytest.mark.parametrize("style", ["fancy", "compact", "detail", "markdown"])
def test_unknown_style_raises(style):
    with pytest.raises(ValueError, match="table"):
        render_listing(example, style=style)
    assert LISTING_STYLES == ("table", "md", "txt", "json")


@pytest.mark.parametrize("style", ["table", "md", "txt"])
def test_pretty_affects_json_only(style):
    assert render_listing(example, style=style, pretty=False) == (
        render_listing(example, style=style)
    )


def test_json_pretty_and_compact():
    rows = [summary.as_row() for summary in summarize_provider(example)]
    pretty = render_listing(example, style="json")
    compact = render_listing(example, style="json", pretty=False)
    assert pretty == json.dumps(rows, indent=2) + "\n"
    assert compact == json.dumps(rows, separators=(",", ":")) + "\n"
    assert compact.count("\n") == 1
    assert json.loads(pretty) == json.loads(compact) == rows


@pytest.mark.parametrize(
    ("schema", "pages"),
    [
        ({"type": "object"}, False),
        ({"type": "object", "properties": {"limit": {"type": "integer"}}}, False),
        ({"type": "object", "properties": {"cursor": {"type": "string"}}}, True),
    ],
)
def test_pages_follows_the_cursor_input(schema, pages):
    assert summarize_tool(make_tool(input_schema=schema)).pages is pages


def test_example_pages():
    assert {s.name: s.pages for s in summarize_provider(example)} == {
        "echo_records": True,
        "echo": True,
        "block_sizes": False,
        "render_badge": False,
    }


def test_table_modes_and_bare_deprecation():
    provider = FakeProvider(
        make_tool(name="writer", read_only_hint=False),
        make_tool(name="wiper", read_only_hint=False, destructive_hint=True),
        make_tool(name="old", deprecated=True),
    )
    assert render_listing(provider) == (
        "writer  remote  write        Do the thing to a target.\n"
        "wiper   remote  destructive  Do the thing to a target.\n"
        "old     remote  read         Do the thing to a target. [deprecated]\n"
    )


def test_txt_for_writing_tool_without_inputs():
    tool = make_tool(
        title="Wipe",
        target="inventory",
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        deprecated=True,
    )
    assert render_listing(FakeProvider(tool), style="txt") == (
        "do_thing - Wipe\n"
        f"  {DESCRIPTION}\n"
        "  access: remote  target: inventory  result: records\n"
        "  hints: writes, destructive\n"
        "  deprecated: yes\n"
        "  inputs: none\n"
    )


def test_txt_inputs_are_plain_aligned_columns():
    schema = {
        "type": "object",
        "properties": {
            "cursor": {"type": ["string", "null"], "description": "Next page."},
            "n": {"type": "integer"},
        },
        "required": ["n"],
    }
    text = render_listing(FakeProvider(make_tool(input_schema=schema)), style="txt")
    assert "  hints: read-only, idempotent, pages\n" in text
    assert text.endswith(
        "  inputs:\n"
        "    name    type         required  description\n"
        "    cursor  string|null  no        Next page.\n"
        "    n       integer      yes\n"
    )


@pytest.mark.parametrize(
    ("value", "cell"),
    [
        (True, "yes"),
        (False, "no"),
        (None, ""),
        (7, "7"),
        ("a|b", "a\\|b"),
        ("two\nlines", "two lines"),
    ],
)
def test_markdown_cells(value, cell):
    table = render_markdown_table([{"col": value}], ["col"])
    assert table.splitlines()[2] == f"| {cell.ljust(3)} |"


def test_markdown_table_pads_missing_keys_and_short_headers():
    assert render_markdown_table([{"a": "long value"}, {}], ["a", "b"]) == (
        "| a          | b   |\n"
        "| ---------- | --- |\n"
        "| long value |     |\n"
        "|            |     |\n"
    )


def test_markdown_table_without_rows():
    assert render_markdown_table([], ["name"]) == "| name |\n| ---- |\n"
