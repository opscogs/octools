"""The ``OCTool`` agent-tool descriptor and the ``ToolProvider`` protocol.

An ``OCTool`` is a frozen, vendor-neutral description of one capability a
library offers to an agent runtime: a name, a model-facing description, JSON
Schema 2020-12 for its arguments and result, MCP-vocabulary safety hints, an
OpsCogs access classification, and the callable that does the work.
Construction fails fast on structural errors; policy conformance (sentence
counts, strict-clean schemas, escape reasons) is reported by
``octools.validate`` instead so a library can assert on findings.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, get_args, runtime_checkable

from octools.findings import Finding

SPEC_VERSION = "1.1"
"""Format version of the ``OCTool`` descriptor and the result envelopes.

Readers check the major only. A minor bump adds only what a reader may drop
or read as a fallback: an optional field whose absence keeps its meaning, or
a value in a vocabulary that has a fallback. Removing, renaming or changing
the meaning of a field or value needs a new major.
"""
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
"""Tool names: lowercase snake_case, at most 48 characters.

The tightest common tool-name limit is 64 characters; the 16 spare leave
room for the runtime's namespace prefix (for example ``demo_``).
"""
ResultKind = Literal["records", "artifact"]
Access = Literal["local", "remote"]
RESULT_KINDS: tuple[str, ...] = get_args(ResultKind)
ACCESS_KINDS: tuple[str, ...] = get_args(Access)
RESULT_KIND_FALLBACK: ResultKind = "records"
"""How a reader of a tool listing reads a ``result_kind`` it does not know."""
ACCESS_FALLBACK: Access = "remote"
"""How a reader of a tool listing reads an ``access`` it does not know.

``remote`` is the safer policy assumption.
"""


class OCToolError(ValueError):
    """Raised when an ``OCTool`` is constructed or converted with invalid data."""


def _require(condition: bool, message: str) -> None:
    """Raise ``OCToolError`` with ``message`` unless ``condition`` holds."""
    if not condition:
        raise OCToolError(message)


def _check_object_schema(schema: object, label: str) -> None:
    """Require ``schema`` to be a mapping whose root type is ``object``."""
    if not isinstance(schema, Mapping):
        raise OCToolError(f"{label} must be a mapping")
    _require(
        schema.get("type") == "object",
        f"{label} root must have type 'object', got {schema.get('type')!r}",
    )


@dataclass(frozen=True, kw_only=True)
class OCTool:
    """One agent tool, described once, convertible to any vendor's shape.

    Required: ``name``, ``description``, ``input_schema``, ``func`` and
    ``access``. Everything else has a default so adding a field to a later
    minor spec version never breaks construction (``kw_only`` guarantees the
    same for positional order). See ``docs/site/octools_descriptor.md`` for
    the meaning of every field.
    """

    name: str
    description: str
    input_schema: Mapping[str, Any]
    func: Callable[..., Any]
    access: Access
    target: str | None = None
    output_schema: Mapping[str, Any] | None = None
    result_kind: ResultKind = "records"
    title: str | None = None
    read_only_hint: bool = True
    destructive_hint: bool = False
    idempotent_hint: bool = True
    deprecated: bool = False
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the structural invariants; raise ``OCToolError`` on failure."""
        _require(
            isinstance(self.name, str) and bool(NAME_RE.fullmatch(self.name)),
            f"name {self.name!r} must match {NAME_RE.pattern}",
        )
        _require(
            isinstance(self.description, str) and bool(self.description.strip()),
            f"tool {self.name!r}: description must be a non-empty string",
        )
        _check_object_schema(self.input_schema, f"tool {self.name!r}: input_schema")
        if self.output_schema is not None:
            _check_object_schema(
                self.output_schema, f"tool {self.name!r}: output_schema"
            )
        _require(callable(self.func), f"tool {self.name!r}: func must be callable")
        _require(
            not (
                inspect.iscoroutinefunction(self.func)
                or inspect.isasyncgenfunction(self.func)
            ),
            f"tool {self.name!r}: func must be synchronous, not async",
        )
        _require(
            self.access in ACCESS_KINDS,
            f"tool {self.name!r}: access must be one of {ACCESS_KINDS}, "
            f"got {self.access!r}",
        )
        _require(
            self.target is None
            or (isinstance(self.target, str) and bool(self.target.strip())),
            f"tool {self.name!r}: target must be None or a non-empty string",
        )
        _require(
            self.result_kind in RESULT_KINDS,
            f"tool {self.name!r}: result_kind must be one of {RESULT_KINDS}, "
            f"got {self.result_kind!r}",
        )
        _require(
            self.title is None
            or (isinstance(self.title, str) and bool(self.title.strip())),
            f"tool {self.name!r}: title must be None or a non-empty string",
        )
        for hint in ("read_only_hint", "destructive_hint", "idempotent_hint"):
            _require(
                isinstance(getattr(self, hint), bool),
                f"tool {self.name!r}: {hint} must be a bool",
            )
        _require(
            isinstance(self.deprecated, bool),
            f"tool {self.name!r}: deprecated must be a bool",
        )
        _require(
            isinstance(self.meta, Mapping),
            f"tool {self.name!r}: meta must be a mapping",
        )


@runtime_checkable
class ToolProvider(Protocol):
    """Anything that lists its tools: a module or object exposing ``all_tools``.

    ``all_tools()`` returns the descriptors in a fixed order (MCP asks for
    deterministic listings so prompt caches stay warm) with unique names.
    """

    def all_tools(self) -> Sequence[OCTool]:
        """Return every tool this provider offers, in deterministic order."""
        ...


@dataclass(frozen=True)
class _MergedProvider:
    """One listing built from several providers, concatenated in order."""

    providers: tuple[ToolProvider, ...]

    def all_tools(self) -> Sequence[OCTool]:
        """Return every listed tool, provider by provider, in argument order."""
        return tuple(
            tool for provider in self.providers for tool in provider.all_tools()
        )


def merge_providers(*providers: ToolProvider) -> ToolProvider:
    """Combine providers into one whose listing concatenates theirs, in order.

    A consumer registering its own tools beside another package's validates
    the union, not each half. Nothing is deduplicated: a name two providers
    share stays listed twice so ``validate_provider`` reports it as
    ``duplicate_name`` instead of silently dropping one of them.
    """
    return _MergedProvider(tuple(providers))


def _listed_names(provider: ToolProvider) -> list[str]:
    """Return the names ``all_tools()`` lists; foreign items show as their type."""
    return [
        tool.name if isinstance(tool, OCTool) else f"<{type(tool).__name__}>"
        for tool in provider.all_tools()
    ]


def check_tool_listing(provider: ToolProvider) -> list[Finding]:
    """Report duplicate names and unstable ordering in a provider's listing.

    Calls ``all_tools()`` twice: the two name sequences must be identical
    (``unstable_order``) and each name must appear once (``duplicate_name``).
    """
    first = _listed_names(provider)
    second = _listed_names(provider)
    findings: list[Finding] = []
    if first != second:
        findings.append(
            Finding(
                rule="unstable_order",
                message=f"all_tools() order changed between calls: {first} then "
                f"{second}",
            )
        )
    seen: set[str] = set()
    for name in first:
        if name in seen:
            findings.append(
                Finding(
                    rule="duplicate_name",
                    message=f"tool name {name!r} is listed more than once",
                    tool=name,
                )
            )
        seen.add(name)
    return findings


__all__ = [
    "ACCESS_FALLBACK",
    "ACCESS_KINDS",
    "NAME_RE",
    "RESULT_KINDS",
    "RESULT_KIND_FALLBACK",
    "SPEC_VERSION",
    "Access",
    "OCTool",
    "OCToolError",
    "ResultKind",
    "ToolProvider",
    "check_tool_listing",
    "merge_providers",
]
