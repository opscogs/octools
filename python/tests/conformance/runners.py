"""Run one spec fixture's ``input`` through the Python implementation.

Each runner takes a fixture's ``input`` and returns the JSON value its
``expected`` must equal. Tools are plain descriptor dicts (every ``OCTool``
field but ``func``); findings compare as ``rule``, ``tool`` and ``path``,
since ``message`` is for a person and is not part of the contract; errors
are ``{"error": <code>}``.
"""

import dataclasses
import ipaddress
import json
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, ValidationError, create_model

from octools import (
    TOOL_FORMATS,
    ArtifactEnvelope,
    Finding,
    OCTool,
    OCToolError,
    RecordsEnvelope,
    TabularEnvelope,
    check_tool_listing,
    close_objects,
    convert_tool,
    count_sentences,
    merge_providers,
    read_envelope,
    render_listing,
    render_markdown_table,
    select_tools,
    strict_clean,
    strip_keys,
    strip_titles,
    summarize_provider,
    summarize_tool,
    tabular_from_models,
    to_anthropic_tool,
    to_mcp_tool,
    validate_provider,
    validate_tabular,
    validate_tags,
    validate_tool,
)

ENVELOPES = {
    "records": RecordsEnvelope[dict[str, Any]],
    "tabular": TabularEnvelope,
    "artifact": ArtifactEnvelope,
}


class FixtureError(Exception):
    """An operation failed in a way the spec names: ``code`` is the error data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _handler(_dependency, **_args):
    return {}


def plain(value: object) -> Any:
    """Return ``value`` as plain JSON data."""
    return json.loads(json.dumps(value))


def build_tool(data: dict[str, Any]) -> OCTool:
    if isinstance(data.get("tags"), list):
        data = {**data, "tags": tuple(data["tags"])}
    try:
        return OCTool(func=_handler, **data)
    except (OCToolError, TypeError) as exc:
        raise FixtureError("invalid_descriptor") from exc


def unchecked_tool(data: dict[str, Any]) -> OCTool:
    """Build a tool whose fields skipped construction checks (set afterwards)."""
    tool = OCTool(
        name="unchecked",
        description="Unchecked.",
        input_schema={"type": "object"},
        func=_handler,
        access="local",
    )
    for key, value in data.items():
        object.__setattr__(tool, key, value)
    return tool


def listed(item: object) -> object:
    """A descriptor dict becomes a tool; any other JSON value is a foreign item."""
    return build_tool(item) if isinstance(item, dict) else item


class FixtureProvider:
    """Call ``n`` of ``all_tools()`` returns ``listings[n]``, then the last again."""

    def __init__(self, listings: list[list[object]]) -> None:
        self.listings = [tuple(listed(item) for item in items) for items in listings]
        self.calls = 0

    def all_tools(self):
        listing = self.listings[min(self.calls, len(self.listings) - 1)]
        self.calls += 1
        return listing


def provider(data: dict[str, Any]) -> FixtureProvider:
    """``tools`` is a stable listing; ``listings`` gives one listing per call."""
    return FixtureProvider(data["listings"] if "listings" in data else [data["tools"]])


def findings(found: list[Finding]) -> list[dict[str, object]]:
    return [{"rule": f.rule, "tool": f.tool, "path": f.path} for f in found]


def descriptor(tool: OCTool) -> dict[str, object]:
    return plain(
        {
            field.name: getattr(tool, field.name)
            for field in dataclasses.fields(tool)
            if field.name != "func"
        }
    )


def envelope(model: str, data: object, *, tolerant: bool) -> dict[str, object]:
    cls = ENVELOPES[model]
    try:
        parsed = read_envelope(cls, data) if tolerant else cls.model_validate(data)
    except (ValidationError, ValueError) as exc:
        raise FixtureError("invalid_envelope") from exc
    return parsed.model_dump(mode="json")


def convert(convert_fn: Callable[..., dict[str, Any]], data: dict[str, Any]) -> object:
    tool = build_tool(data["tool"])
    try:
        return convert_fn(tool, name_prefix=data.get("name_prefix", ""))
    except OCToolError as exc:
        raise FixtureError("invalid_name") from exc


def convert_format(data: dict[str, Any]) -> object:
    tool = build_tool(data["tool"])
    try:
        return convert_tool(
            tool, data["format"], name_prefix=data.get("name_prefix", "")
        )
    except OCToolError as exc:
        code = (
            "invalid_format" if data["format"] not in TOOL_FORMATS else "invalid_name"
        )
        raise FixtureError(code) from exc


def tabular(data: dict[str, Any]) -> object:
    try:
        table = TabularEnvelope.model_validate(data["envelope"])
    except ValidationError as exc:
        raise FixtureError("invalid_envelope") from exc
    return findings(validate_tabular(table))


class _Nested(BaseModel):
    a: int


FIELD_TYPES: dict[str, object] = {
    "boolean": bool,
    "integer": int,
    "number": float,
    "text": str,
    "timestamp": AwareDatetime,
    "datetime": datetime,
    "ip": ipaddress.IPv4Address,
    "ip_block": ipaddress.IPv4Network,
    "literal_text": Literal["a", "b"],
    "literal_integer": Literal[1, 2],
    "literal_mixed": Literal["a", 1],
    "list": list[str],
    "object": dict[str, int],
    "nested": _Nested,
    "union": int | str,
    "union_numeric": int | float,
    "union_boolean": bool | str,
    "literal_nullable": Literal[1, None],  # noqa: PYI061
    "positive": Annotated[int, Field(gt=0)],
}
"""Each neutral field type of a ``tabular_from_models`` fixture as an annotation."""


def _model_field(field: dict[str, Any]) -> tuple[object, object]:
    annotation = FIELD_TYPES[field["type"]]
    description = field.get("description")
    if field.get("nullable"):
        return (annotation | None, Field(default=None, description=description))
    return (annotation, Field(description=description))


def from_models(data: dict[str, Any]) -> object:
    model = create_model(
        "Row", **{field["name"]: _model_field(field) for field in data["fields"]}
    )
    items = [model.model_validate(item) for item in data["items"]]
    try:
        table = tabular_from_models(
            model,
            items,
            column_kinds=data.get("column_kinds"),
            truncated=data.get("truncated", False),
            next_cursor=data.get("next_cursor"),
        )
    except OCToolError as exc:
        raise FixtureError("invalid_column") from exc
    except ValidationError as exc:
        raise FixtureError("invalid_envelope") from exc
    return table.model_dump(mode="json")


def listing(data: dict[str, Any]) -> object:
    try:
        return render_listing(
            provider(data),
            style=data.get("style", "table"),
            access=data.get("access"),
            pretty=data.get("pretty", True),
        )
    except ValueError as exc:
        raise FixtureError("invalid_style") from exc


def tool_findings(data: dict[str, Any]) -> object:
    build = unchecked_tool if data.get("unchecked") else build_tool
    return findings(validate_tool(build(data["tool"])))


RUNNERS: dict[str, Callable[[dict[str, Any]], object]] = {
    "OCTool": lambda data: descriptor(build_tool(data["tool"])),
    "check_tool_listing": lambda data: findings(check_tool_listing(provider(data))),
    "close_objects": lambda data: close_objects(data["schema"]),
    "convert_tool": convert_format,
    "count_sentences": lambda data: count_sentences(data["text"]),
    "merge_providers": lambda data: [
        tool.name
        for tool in merge_providers(*map(provider, data["providers"])).all_tools()
    ],
    "read_envelope": lambda data: envelope(data["model"], data["data"], tolerant=True),
    "render_listing": listing,
    "render_markdown_table": lambda data: render_markdown_table(
        data["rows"], data["columns"]
    ),
    "select_tools": lambda data: [
        tool.name
        for tool in select_tools(provider(data), tags=data["tags"]).all_tools()
    ],
    "strict_clean": lambda data: findings(strict_clean(data["schema"])),
    "strip_keys": lambda data: strip_keys(
        data["schema"], keys=data.get("keys", ()), prefixes=data.get("prefixes", ())
    ),
    "strip_titles": lambda data: strip_titles(data["schema"]),
    "summarize_provider": lambda data: [
        summary.as_row()
        for summary in summarize_provider(provider(data), access=data.get("access"))
    ],
    "summarize_tool": lambda data: summarize_tool(build_tool(data["tool"])).as_row(),
    "tabular_from_models": from_models,
    "to_anthropic_tool": lambda data: convert(to_anthropic_tool, data),
    "to_mcp_tool": lambda data: convert(to_mcp_tool, data),
    "validate_envelope": lambda data: envelope(
        data["model"], data["data"], tolerant=False
    ),
    "validate_provider": lambda data: findings(validate_provider(provider(data))),
    "validate_tabular": tabular,
    "validate_tags": lambda data: findings(
        validate_tags(provider(data), allowed=data.get("allowed", ()))
    ),
    "validate_tool": tool_findings,
}
"""One runner per fixture directory under ``spec/fixtures/``."""


def run(operation: str, data: dict[str, Any]) -> object:
    """Return what ``operation`` produces for ``data``, errors as data."""
    try:
        return plain(RUNNERS[operation](data))
    except FixtureError as exc:
        return {"error": exc.code}
