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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol, cast, get_args, runtime_checkable

from octools.findings import Finding

SPEC_VERSION = "1.3"
"""Format version of the ``OCTool`` descriptor and the result envelopes.

Readers check the major only. A minor bump adds only what a reader may drop
or read as a fallback: an optional field whose absence keeps its meaning, or
a value in a vocabulary that has a fallback. Removing, renaming or changing
the meaning of a field or value needs a new major.
"""
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
"""Tool names: lowercase snake_case, at most 48 characters.

The 48 count the provider's namespace (``demo_get_rows``). The tightest
common tool-name limit is 64 characters; the 16 spare leave room for the
prefix an agent host adds when it routes to a server.
"""
NAMESPACE_RE = re.compile(r"^[a-z][a-z0-9]{0,15}$")
"""Provider namespaces: lowercase letters and digits, at most 16 characters.

A published name is ``<namespace>_<name>``; the namespace holds no
underscore, so the first underscore ends it.
"""
ResultKind = Literal["records", "artifact"]
Access = Literal["local", "remote"]
RESULT_KINDS: tuple[str, ...] = get_args(ResultKind)
ACCESS_KINDS: tuple[str, ...] = get_args(Access)
RESULT_KIND_FALLBACK: ResultKind = "records"
"""How a reader of a tool listing reads a ``result_kind`` it does not know."""
ToolTag = Literal["recommended", "advanced"]
"""The well-known tags; ``TOOL_TAGS`` lists the same values."""
TOOL_TAGS: tuple[str, ...] = get_args(ToolTag)
"""Every well-known tag, in documentation order."""
TOOL_TAG_FALLBACK: ToolTag | None = None
"""How a reader of a tool listing reads a tag it does not know: it ignores it.

A tool carrying only unknown tags is therefore never loaded by default.
"""
ACCESS_FALLBACK: Access = "remote"
"""How a reader of a tool listing reads an ``access`` it does not know.

``remote`` is the safer policy assumption.
"""
ALIAS_OF_KEY = "alias_of"
"""``meta`` key on a deprecated alias naming the tool it stands for."""


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
    tags: tuple[str, ...] = ()

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
        _require(
            isinstance(self.tags, tuple)
            and all(isinstance(tag, str) and tag.strip() for tag in self.tags),
            f"tool {self.name!r}: tags must be a tuple of non-empty strings",
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


@dataclass(frozen=True)
class _SelectedProvider:
    """The tools of one provider that carry any of the given tags."""

    provider: ToolProvider
    tags: frozenset[str]

    def all_tools(self) -> Sequence[OCTool]:
        """Return the matching tools in the provider's order, aliases pruned."""
        matched = [
            tool
            for tool in self.provider.all_tools()
            if isinstance(tool, OCTool) and self.tags.intersection(tool.tags)
        ]
        while True:
            names = {tool.name for tool in matched}
            kept = [tool for tool in matched if not _stranded(tool, names)]
            if len(kept) == len(matched):
                return tuple(kept)
            matched = kept


def _stranded(tool: OCTool, names: set[str]) -> bool:
    """Tell whether ``tool`` is a deprecated alias with no target in ``names``."""
    alias = tool.meta.get(ALIAS_OF_KEY)
    return tool.deprecated and isinstance(alias, str) and alias not in names


def select_tools(provider: ToolProvider, *, tags: Iterable[str]) -> ToolProvider:
    """Return a provider listing only the tools carrying any of ``tags``.

    A host calls this before converting, so it needs no consumer's ``meta``
    key: ``select_tools(merged, tags={"recommended"})``. Order is kept, and
    the result reads the underlying provider on every ``all_tools()`` call.
    A deprecated alias whose ``meta["alias_of"]`` target is not selected is
    dropped, and so is an alias of a dropped alias, until every kept alias
    names a kept tool, so the result passes ``validate_provider``. A target
    is never pulled in. A bare string raises
    ``OCToolError``, since it would match by character.
    """
    _require(not isinstance(tags, str), "tags must be an iterable of strings")
    return _SelectedProvider(provider, frozenset(tags))


_DATA_KEYWORDS = frozenset({"const", "default", "enum", "examples"})
"""Schema keywords whose values are instance data, never rewritten."""
_NAME_MAPS = frozenset(
    {"$defs", "definitions", "dependentSchemas", "patternProperties", "properties"}
)
"""Schema keywords whose keys are names and whose values are schemas."""


def _rewrite_schema(node: object, rewrite: Callable[[str], str]) -> object:
    """Return a copy of schema ``node`` with every ``description`` rewritten."""
    if isinstance(node, Mapping):
        out: dict[str, object] = {}
        for key, value in node.items():
            if key == "description" and isinstance(value, str):
                out[key] = rewrite(value)
            elif key in _NAME_MAPS and isinstance(value, Mapping):
                out[key] = {
                    name: _rewrite_schema(sub, rewrite) for name, sub in value.items()
                }
            elif key in _DATA_KEYWORDS:
                out[key] = value
            else:
                out[key] = _rewrite_schema(value, rewrite)
        return out
    if isinstance(node, list | tuple):
        return [_rewrite_schema(sub, rewrite) for sub in node]
    return node


def _renamer(renames: Mapping[str, str]) -> Callable[[str], str]:
    """Return a function replacing each whole-word key of ``renames`` in text.

    A word is a run of ASCII letters, digits and underscores, so an occurrence
    inside a longer name (``demo_get_rows``, ``get_rows_all``) is left alone.
    """
    changed = sorted((old for old, new in renames.items() if old != new), key=len)
    if not changed:
        return lambda text: text
    words = "|".join(re.escape(name) for name in reversed(changed))
    pattern = re.compile(rf"(?<![A-Za-z0-9_])(?:{words})(?![A-Za-z0-9_])")
    return lambda text: pattern.sub(lambda match: renames[match.group()], text)


def _with_prefix(name: str, name_prefix: str) -> str:
    """Return ``name`` with ``name_prefix`` prepended unless it already starts so."""
    return name if name.startswith(name_prefix) else f"{name_prefix}{name}"


def prefix_tools(tools: Iterable[OCTool], name_prefix: str) -> tuple[OCTool, ...]:
    """Return copies of ``tools`` published under ``name_prefix``.

    A prefix without a trailing underscore gets one, so ``"demo"`` and
    ``"demo_"`` are the same prefix. Each copy keeps its own ``func``; a name
    already starting with the prefix is kept, so applying it twice changes
    nothing. ``meta["alias_of"]`` is prefixed the same way. Every whole-word
    occurrence of a sibling's name, in ``description`` and in any
    ``description`` of ``input_schema`` or ``output_schema`` (instance data
    such as ``enum`` and ``default`` excepted), becomes the sibling's
    published name; an occurrence already prefixed and words that name no
    sibling stay as they are. A prefixed name that breaks ``NAME_RE``, or an
    item that is not an ``OCTool``, raises ``OCToolError``. A host
    dispatches by the returned descriptors' names.
    """
    if name_prefix and not name_prefix.endswith("_"):
        name_prefix = f"{name_prefix}_"
    listed = tuple(tools)
    for item in listed:
        _require(isinstance(item, OCTool), f"{item!r} is not an OCTool")
    renames = {tool.name: _with_prefix(tool.name, name_prefix) for tool in listed}
    for name in renames.values():
        _require(
            bool(NAME_RE.fullmatch(name)),
            f"tool name {name!r} does not match {NAME_RE.pattern}",
        )
    rename = _renamer(renames)
    return tuple(_prefixed(tool, renames, rename, name_prefix) for tool in listed)


def _prefixed(
    tool: OCTool,
    renames: Mapping[str, str],
    rename: Callable[[str], str],
    name_prefix: str,
) -> OCTool:
    """Return ``tool`` renamed, with its references and alias target rewritten."""
    meta = tool.meta
    alias = meta.get(ALIAS_OF_KEY)
    if isinstance(alias, str):
        meta = {**meta, ALIAS_OF_KEY: _with_prefix(alias, name_prefix)}
    output_schema = tool.output_schema
    if output_schema is not None:
        output_schema = cast(Mapping[str, Any], _rewrite_schema(output_schema, rename))
    return replace(
        tool,
        name=renames[tool.name],
        description=rename(tool.description),
        input_schema=cast(
            Mapping[str, Any], _rewrite_schema(tool.input_schema, rename)
        ),
        output_schema=output_schema,
        meta=meta,
    )


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
    "NAMESPACE_RE",
    "NAME_RE",
    "RESULT_KINDS",
    "RESULT_KIND_FALLBACK",
    "SPEC_VERSION",
    "TOOL_TAGS",
    "TOOL_TAG_FALLBACK",
    "Access",
    "OCTool",
    "OCToolError",
    "ResultKind",
    "ToolProvider",
    "ToolTag",
    "check_tool_listing",
    "merge_providers",
    "prefix_tools",
    "select_tools",
]
