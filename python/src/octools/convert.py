"""Pure-dict converters from ``OCTool`` to vendor tool shapes.

No SDK is imported: each converter returns the JSON object the target
expects, built from plain dicts, so a library can test its descriptors
without depending on ``mcp`` or ``anthropic``. The MCP mapping is lossless
(everything but ``func`` survives, OpsCogs fields under a namespaced
``_meta``); the Anthropic mapping is lossy by necessity and documents what
it drops.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, cast

from octools.descriptor import SPEC_VERSION, OCTool, OCToolError
from octools.schema import strip_keys

MCP_META_NAMESPACE = "com.opscogs.octools/"
"""Reverse-DNS prefix for OpsCogs keys in an MCP tool's ``_meta``."""
ANTHROPIC_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
"""The Anthropic tool name rule: 1-128 of ``A-Z a-z 0-9 _ -``."""
MCP_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
"""The MCP ``Tool.name`` rule: 1-128 of ``A-Z a-z 0-9 _ - .``.

The same in MCP specs 2025-11-25 and 2026-07-28.
"""


def _plain(value: object) -> object:
    """Return ``value`` as plain JSON-compatible dicts and lists (a deep copy)."""
    if isinstance(value, Mapping):
        return {str(key): _plain(sub) for key, sub in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(sub) for sub in value]
    return value


def _plain_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``value`` as a plain, independent ``dict``."""
    return cast(dict[str, Any], _plain(value))


def _prefixed_name(tool: OCTool, name_prefix: str, rule: re.Pattern[str]) -> str:
    """Return ``name_prefix`` plus the tool's name, or raise if it breaks ``rule``."""
    name = f"{name_prefix}{tool.name}"
    if not rule.fullmatch(name):
        raise OCToolError(f"tool name {name!r} does not match {rule.pattern}")
    return name


def to_mcp_tool(tool: OCTool, *, name_prefix: str = "") -> dict[str, Any]:
    """Return ``tool`` as an MCP ``Tool`` object (specs 2025-11-25 and 2026-07-28).

    ``name`` has ``name_prefix`` prepended, checked against ``MCP_NAME_RE``,
    so one provider can reach two targets on one server. ``inputSchema`` and
    ``outputSchema`` are the descriptor's schemas verbatim; the three hints
    become ``annotations``; ``access``, ``target``, ``result_kind``,
    ``deprecated`` and the ``meta`` bag go under ``_meta`` with the
    ``com.opscogs.octools/`` prefix, beside the spec version. Only ``func`` is
    not represented (it is the server's handler). ``title``, ``outputSchema``
    and ``target`` are present only when set.
    """
    out: dict[str, Any] = {"name": _prefixed_name(tool, name_prefix, MCP_NAME_RE)}
    if tool.title is not None:
        out["title"] = tool.title
    out["description"] = tool.description
    out["inputSchema"] = _plain_mapping(tool.input_schema)
    if tool.output_schema is not None:
        out["outputSchema"] = _plain_mapping(tool.output_schema)
    out["annotations"] = {
        "readOnlyHint": tool.read_only_hint,
        "destructiveHint": tool.destructive_hint,
        "idempotentHint": tool.idempotent_hint,
    }
    meta: dict[str, Any] = {
        f"{MCP_META_NAMESPACE}spec_version": SPEC_VERSION,
        f"{MCP_META_NAMESPACE}access": tool.access,
        f"{MCP_META_NAMESPACE}result_kind": tool.result_kind,
        f"{MCP_META_NAMESPACE}deprecated": tool.deprecated,
        f"{MCP_META_NAMESPACE}meta": _plain_mapping(tool.meta),
    }
    if tool.target is not None:
        meta[f"{MCP_META_NAMESPACE}target"] = tool.target
    out["_meta"] = meta
    return out


def to_anthropic_tool(tool: OCTool, *, name_prefix: str = "") -> dict[str, Any]:
    """Return ``tool`` as an Anthropic Messages API ``tools[]`` entry.

    The entry carries ``name`` (with ``name_prefix`` prepended, checked
    against Anthropic's 128-character rule), ``description`` and
    ``input_schema``. The schema is the descriptor's with every ``title`` and
    ``x-`` key stripped and ``additionalProperties: false`` on the root, so
    the runtime can set ``strict: true`` itself. Dropped, because the API has
    no slot for them: ``title``, ``output_schema``, the hints, ``access`` /
    ``target``, ``result_kind``, ``deprecated`` and ``meta`` -- the runtime's
    registry keeps those. ``strict`` is not emitted; it is a runtime choice.
    """
    name = _prefixed_name(tool, name_prefix, ANTHROPIC_NAME_RE)
    schema = strip_keys(tool.input_schema, keys=("title",), prefixes=("x-",))
    schema.setdefault("additionalProperties", False)
    return {"name": name, "description": tool.description, "input_schema": schema}


__all__ = [
    "ANTHROPIC_NAME_RE",
    "MCP_META_NAMESPACE",
    "MCP_NAME_RE",
    "to_anthropic_tool",
    "to_mcp_tool",
]
