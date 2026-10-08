"""Human-readable listings of a tool provider: table, Markdown, text and JSON.

``summarize_tool`` flattens an ``OCTool`` into a ``ToolSummary`` a person or a
CLI can read without the callable or the full schemas; ``render_listing``
renders a provider's summaries in one of the ``LISTING_STYLES``. Output is
plain text, GitHub Markdown or JSON, built from the standard library only.
"""

from __future__ import annotations

import json
import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from octools.descriptor import Access, OCTool, ResultKind, ToolProvider
from octools.validate import ALIAS_OF_KEY, SENTENCE_RE

ListingStyle = Literal["table", "md", "txt", "json"]
LISTING_STYLES: tuple[ListingStyle, ...] = ("table", "md", "txt", "json")
_MD_COLUMNS = (
    "name",
    "access",
    "mode",
    "result_kind",
    "pages",
    "deprecated",
    "summary",
)
_INPUT_COLUMNS = ("name", "type", "required", "description")
_WRAP_WIDTH = 88
_ENUM_WIDTH = 40


@dataclass(frozen=True)
class InputSummary:
    """One top-level argument of a tool: name, rendered type, requiredness."""

    name: str
    type: str
    required: bool
    description: str | None


@dataclass(frozen=True)
class ToolSummary:
    """The listing-relevant facts of one ``OCTool``, without func or schemas."""

    name: str
    title: str | None
    summary: str
    description: str
    access: Access
    target: str | None
    result_kind: ResultKind
    read_only: bool
    destructive: bool
    idempotent: bool
    pages: bool
    deprecated: bool
    alias_of: str | None
    inputs: tuple[InputSummary, ...]

    def as_row(self) -> dict[str, object]:
        """Return a JSON-ready flat dict; ``inputs`` is a list of plain dicts."""
        return {
            "name": self.name,
            "title": self.title,
            "summary": self.summary,
            "description": self.description,
            "access": self.access,
            "target": self.target,
            "result_kind": self.result_kind,
            "read_only": self.read_only,
            "destructive": self.destructive,
            "idempotent": self.idempotent,
            "pages": self.pages,
            "deprecated": self.deprecated,
            "alias_of": self.alias_of,
            "inputs": [_input_row(item) for item in self.inputs],
        }


def _input_row(item: InputSummary) -> dict[str, object]:
    """Return one input as a JSON-ready dict."""
    return {
        "name": item.name,
        "type": item.type,
        "required": item.required,
        "description": item.description,
    }


def _mode(summary: ToolSummary) -> str:
    """Return ``destructive``, ``write`` or ``read`` from the safety hints."""
    if summary.destructive:
        return "destructive"
    return "read" if summary.read_only else "write"


def _first_sentence(text: str) -> str:
    """Return ``text`` up to and including its first sentence end, stripped."""
    stripped = text.strip()
    match = SENTENCE_RE.search(stripped)
    return stripped[: match.end()].strip() if match else stripped


def _members_type(members: object) -> str:
    """Render ``anyOf`` / ``oneOf`` members as their types joined with ``|``."""
    if not isinstance(members, Sequence) or isinstance(members, str):
        return "any"
    return "|".join(_schema_type(member) for member in members) or "any"


def _value(value: object) -> str:
    """Render one ``enum`` or ``const`` value: strings bare, others as JSON."""
    return value if isinstance(value, str) else json.dumps(value)


def _enum_type(values: object) -> str:
    """Render ``enum(a|b)``, cut to the values fitting in 40 characters."""
    if not isinstance(values, list):
        return "enum"
    shown: list[str] = []
    for text in map(_value, values):
        if len("|".join([*shown, text])) > _ENUM_WIDTH:
            return f"enum({'|'.join([*shown, '...'])})"
        shown.append(text)
    return f"enum({'|'.join(shown)})"


def _schema_type(schema: object) -> str:
    """Render a short type name for a JSON Schema property; never raises."""
    if not isinstance(schema, Mapping):
        return "any"
    if "enum" in schema:
        return _enum_type(schema["enum"])
    if "const" in schema:
        return f"const({_value(schema['const'])})"
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return ref.rsplit("/", 1)[-1]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            return _members_type(schema[key])
    kind = schema.get("type")
    if isinstance(kind, list):
        return "|".join(str(item) for item in kind)
    if kind == "array" and "items" in schema:
        return f"array[{_schema_type(schema['items'])}]"
    return kind if isinstance(kind, str) else "any"


def _inputs(schema: Mapping[str, object]) -> tuple[InputSummary, ...]:
    """Summarize the top-level ``properties`` of an input schema, in order."""
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return ()
    required = schema.get("required")
    names = set(required) if isinstance(required, list) else set()
    summaries = []
    for name, prop in properties.items():
        description = prop.get("description") if isinstance(prop, Mapping) else None
        summaries.append(
            InputSummary(
                name=str(name),
                type=_schema_type(prop),
                required=name in names,
                description=description if isinstance(description, str) else None,
            )
        )
    return tuple(summaries)


def _has_cursor(schema: Mapping[str, object]) -> bool:
    """Return whether the input schema's properties include ``cursor``."""
    properties = schema.get("properties")
    return isinstance(properties, Mapping) and "cursor" in properties


def summarize_tool(tool: OCTool) -> ToolSummary:
    """Flatten one ``OCTool`` into the facts a listing shows."""
    alias = tool.meta.get(ALIAS_OF_KEY)
    return ToolSummary(
        name=tool.name,
        title=tool.title,
        summary=_first_sentence(tool.description),
        description=tool.description,
        access=tool.access,
        target=tool.target,
        result_kind=tool.result_kind,
        read_only=tool.read_only_hint,
        destructive=tool.destructive_hint,
        idempotent=tool.idempotent_hint,
        pages=_has_cursor(tool.input_schema),
        deprecated=tool.deprecated,
        alias_of=alias if isinstance(alias, str) and alias else None,
        inputs=_inputs(tool.input_schema),
    )


def summarize_provider(
    provider: ToolProvider, *, access: Access | None = None
) -> tuple[ToolSummary, ...]:
    """Summarize ``provider.all_tools()`` in order, keeping only ``access`` if set."""
    return tuple(
        summarize_tool(tool)
        for tool in provider.all_tools()
        if access is None or tool.access == access
    )


def _plain(value: object) -> str:
    """Render one cell as one line: yes/no for bools, blank for None."""
    if isinstance(value, bool):
        text = "yes" if value else "no"
    elif value is None:
        text = ""
    else:
        text = str(value)
    return " ".join(text.splitlines())


def _cell(value: object) -> str:
    """Render one Markdown table cell: a plain cell with pipes escaped."""
    return _plain(value).replace("|", "\\|")


def _aligned(rows: Sequence[Sequence[str]]) -> list[str]:
    """Pad every column but the last to its width, with two-space gutters."""
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]) - 1)]
    return [
        "  ".join([*(v.ljust(w) for v, w in zip(row, widths, strict=False)), row[-1]])
        for row in rows
    ]


def render_markdown_table(
    rows: Sequence[Mapping[str, object]], columns: Sequence[str]
) -> str:
    """Render ``rows`` as a padded GitHub Markdown table over ``columns``.

    A bool renders as ``yes`` / ``no`` and a missing or ``None`` value as an
    empty cell. The result ends with a newline; no rows gives the header and
    dash rows only.
    """
    cells = [[_cell(row.get(column)) for column in columns] for row in rows]
    widths = [
        max([len(column), 3, *(len(line[index]) for line in cells)])
        for index, column in enumerate(columns)
    ]

    def line(values: Sequence[str]) -> str:
        """Join one row's cells, each padded to its column width."""
        padded = (
            value.ljust(width) for value, width in zip(values, widths, strict=True)
        )
        return "| " + " | ".join(padded) + " |"

    lines = [line(columns), line(["-" * width for width in widths])]
    lines.extend(line(values) for values in cells)
    return "\n".join(lines) + "\n"


def _render_table(summaries: Sequence[ToolSummary]) -> str:
    """Render one padded line per tool: name, access, mode and summary."""
    if not summaries:
        return ""
    rows = [(s.name, s.access, _mode(s), _table_summary(s)) for s in summaries]
    return "".join(f"{line}\n" for line in _aligned(rows))


def _table_summary(summary: ToolSummary) -> str:
    """Return the summary with a deprecation marker when the tool has one."""
    if not summary.deprecated:
        return summary.summary
    marker = f"deprecated; use {summary.alias_of}" if summary.alias_of else "deprecated"
    return f"{summary.summary} [{marker}]"


def _render_md(summaries: Sequence[ToolSummary]) -> str:
    """Render a Markdown table: name, access, mode, kind, paging, deprecation."""
    rows = [{**s.as_row(), "mode": _mode(s)} for s in summaries]
    return render_markdown_table(rows, _MD_COLUMNS)


def _txt_block(summary: ToolSummary) -> str:
    """Render one tool as a header line followed by indented facts."""
    header = summary.name + (f" - {summary.title}" if summary.title else "")
    hints = ["read-only" if summary.read_only else "writes"]
    if summary.destructive:
        hints.append("destructive")
    if summary.idempotent:
        hints.append("idempotent")
    if summary.pages:
        hints.append("pages")
    lines = [
        header,
        textwrap.fill(
            summary.description,
            width=_WRAP_WIDTH,
            initial_indent="  ",
            subsequent_indent="  ",
        ),
        (
            f"  access: {summary.access}  target: {summary.target or '-'}  "
            f"result: {summary.result_kind}"
        ),
        f"  hints: {', '.join(hints)}",
    ]
    if summary.deprecated:
        lines.append(
            f"  deprecated: use {summary.alias_of}"
            if summary.alias_of
            else "  deprecated: yes"
        )
    if summary.inputs:
        rows: list[Sequence[str]] = [_INPUT_COLUMNS]
        rows.extend(
            tuple(_plain(row[column]) for column in _INPUT_COLUMNS)
            for row in map(_input_row, summary.inputs)
        )
        lines.append("  inputs:")
        lines.extend(f"    {line}".rstrip() for line in _aligned(rows))
    else:
        lines.append("  inputs: none")
    return "\n".join(lines) + "\n"


def render_listing(
    provider: ToolProvider,
    *,
    style: ListingStyle = "table",
    access: Access | None = None,
    pretty: bool = True,
) -> str:
    """Render a provider's tools in ``style``, keeping only ``access`` if set.

    Raises ``ValueError`` for a style outside ``LISTING_STYLES``. Output ends
    with a newline, except an empty listing is ``""`` for ``table`` and
    ``txt``; ``md`` then renders the header and divider, ``json`` ``[]``.
    ``pretty`` affects ``json`` only: indented when true, else compact.
    """
    if style not in LISTING_STYLES:
        raise ValueError(f"style must be one of {LISTING_STYLES}, got {style!r}")
    summaries = summarize_provider(provider, access=access)
    if style == "table":
        return _render_table(summaries)
    if style == "md":
        return _render_md(summaries)
    if style == "txt":
        return "\n".join(_txt_block(s) for s in summaries)
    rows = [s.as_row() for s in summaries]
    if pretty:
        return json.dumps(rows, indent=2) + "\n"
    return json.dumps(rows, separators=(",", ":")) + "\n"


__all__ = [
    "LISTING_STYLES",
    "InputSummary",
    "ListingStyle",
    "ToolSummary",
    "render_listing",
    "render_markdown_table",
    "summarize_provider",
    "summarize_tool",
]
