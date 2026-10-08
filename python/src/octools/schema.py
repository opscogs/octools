"""JSON Schema 2020-12 helpers for ``input_schema`` and ``output_schema``.

Schemas are generated from pydantic models, never hand-written. This module
suppresses pydantic's ``title`` noise, closes model objects for input
schemas, passes ``x-`` extension keys (such as ``x-sensitivity``) through
untouched, and checks a schema against the strict-mode keyword subset that
both Anthropic and OpenAI accept. The checker reports findings; it never
mutates the schema it is given.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable, Mapping
from typing import Any, cast

from pydantic import BaseModel
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode, JsonSchemaValue
from pydantic_core import CoreSchema

from octools.findings import Finding

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_SCHEMA_MAPS = frozenset(
    {"properties", "$defs", "patternProperties", "dependentSchemas"}
)
_SCHEMA_LISTS = frozenset({"anyOf", "allOf", "oneOf", "prefixItems"})
_DATA_KEYWORDS = frozenset({"default", "const", "enum", "examples"})
STRICT_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "anyOf",
        "allOf",
        "$ref",
        "$defs",
        "default",
        "description",
        "format",
        "minItems",
    }
)
"""Keywords both Anthropic and OpenAI strict modes accept (the intersection)."""
STRICT_TYPES = frozenset(
    {"object", "array", "string", "integer", "number", "boolean", "null"}
)
STRICT_FORMATS = frozenset(
    {
        "date-time",
        "time",
        "date",
        "duration",
        "email",
        "hostname",
        "uri",
        "ipv4",
        "ipv6",
        "uuid",
    }
)
_PRIMITIVES = (str, int, float, bool, type(None))
_DEFS_PREFIX = "#/$defs/"


class NoTitleGenerator(GenerateJsonSchema):
    """Pydantic schema generator that emits no ``title`` keywords at all."""

    def field_title_should_be_set(self, schema: CoreSchema) -> bool:  # noqa: ARG002
        """Never set a title on a field."""
        return False

    def generate(
        self, schema: CoreSchema, mode: JsonSchemaMode = "validation"
    ) -> JsonSchemaValue:
        """Generate the schema, then drop the model-level titles pydantic adds."""
        return strip_titles(super().generate(schema, mode=mode))


def _map_schema(node: object, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> object:
    """Return a plain-dict copy of ``node`` with ``fn`` applied to every subschema.

    Keys under ``properties`` / ``$defs`` are names, not keywords; values of
    ``default`` / ``const`` / ``enum`` / ``examples`` and ``x-`` keys are
    data, so neither is treated as a schema.
    """
    if not isinstance(node, Mapping):
        return copy.deepcopy(node)
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _SCHEMA_MAPS and isinstance(value, Mapping):
            out[key] = {name: _map_schema(sub, fn) for name, sub in value.items()}
        elif key in _SCHEMA_LISTS and isinstance(value, list):
            out[key] = [_map_schema(sub, fn) for sub in value]
        elif key in _DATA_KEYWORDS or key.startswith("x-"):
            out[key] = copy.deepcopy(value)
        elif isinstance(value, Mapping):
            out[key] = _map_schema(value, fn)
        else:
            out[key] = copy.deepcopy(value)
    return fn(out)


def strip_keys(
    schema: Mapping[str, Any],
    *,
    keys: Iterable[str] = (),
    prefixes: Iterable[str] = (),
) -> dict[str, Any]:
    """Return a copy of ``schema`` without the named keywords at any schema level.

    ``keys`` are removed exactly; ``prefixes`` remove every keyword that
    starts with one of them (``("x-",)`` drops all extension keys). Property
    names are never touched, even when they collide with a removed keyword.
    """
    drop = frozenset(keys)
    starts = tuple(prefixes)

    def clean(node: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in node.items()
            if key not in drop and not (starts and key.startswith(starts))
        }

    return cast(dict[str, Any], _map_schema(schema, clean))


def strip_titles(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of ``schema`` with every ``title`` keyword removed."""
    return strip_keys(schema, keys=("title",))


def close_objects(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with ``additionalProperties: false`` on every model object.

    Only objects that declare ``properties`` are closed; a free-form
    ``dict`` field (an object with no ``properties``) is left alone so its
    meaning is not silently changed, and ``strict_clean`` reports it.
    """

    def close(node: dict[str, Any]) -> dict[str, Any]:
        if "properties" in node and "additionalProperties" not in node:
            return {**node, "additionalProperties": False}
        return node

    return cast(dict[str, Any], _map_schema(schema, close))


def schema_for(
    model: type[BaseModel], *, mode: JsonSchemaMode = "validation"
) -> dict[str, Any]:
    """Return the 2020-12 JSON Schema of ``model`` with no ``title`` keywords.

    ``$defs`` are kept (internal refs are strict-clean); ``json_schema_extra``
    keys such as ``x-sensitivity`` pass through unchanged.
    """
    return model.model_json_schema(schema_generator=NoTitleGenerator, mode=mode)


def input_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """Return ``model``'s schema shaped for ``OCTool.input_schema``.

    Validation mode (it describes what the model sends), no titles, and
    every model object closed with ``additionalProperties: false``.
    """
    return close_objects(schema_for(model, mode="validation"))


def output_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """Return ``model``'s schema shaped for ``OCTool.output_schema``.

    Serialization mode (it describes what the tool returns) and no titles.
    Output schemas are unconstrained 2020-12: nothing sends them to a
    grammar compiler, so extras and bounds are fine here.
    """
    return schema_for(model, mode="serialization")


def _collect_refs(node: object) -> set[str]:
    """Return every internal ``$defs`` name referenced anywhere under ``node``."""
    refs: set[str] = set()
    if isinstance(node, Mapping):
        for key, value in node.items():
            if (
                key == "$ref"
                and isinstance(value, str)
                and value.startswith(_DEFS_PREFIX)
            ):
                refs.add(value[len(_DEFS_PREFIX) :])
            elif key not in _DATA_KEYWORDS:
                refs |= _collect_refs(value)
    elif isinstance(node, list):
        for item in node:
            refs |= _collect_refs(item)
    return refs


def _recursive_defs(defs: Mapping[str, Any]) -> list[str]:
    """Return the ``$defs`` names that can reach themselves through ``$ref``."""
    graph = {name: _collect_refs(sub) & defs.keys() for name, sub in defs.items()}
    recursive: list[str] = []
    for start, neighbors in graph.items():
        seen: set[str] = set()
        stack = list(neighbors)
        while stack:
            current = stack.pop()
            if current == start:
                recursive.append(start)
                break
            if current not in seen:
                seen.add(current)
                stack.extend(graph[current])
    return recursive


class _StrictChecker:
    """Walk one schema and collect strict-mode findings."""

    def __init__(self, defs: Mapping[str, Any]) -> None:
        self.defs = defs
        self.findings: list[Finding] = []

    def add(self, rule: str, message: str, path: str) -> None:
        """Record one finding at ``path``."""
        self.findings.append(Finding(rule=rule, message=message, path=path))

    def check(self, node: object, path: str, *, root: bool = False) -> None:
        """Check ``node`` and recurse into its subschemas."""
        if not isinstance(node, Mapping):
            self.add("boolean_schema", f"boolean schema {node!r} is not allowed", path)
            return
        for key in node:
            self.check_keyword(key, node[key], path)
        if "$defs" in node and not root:
            self.add("defs_not_at_root", "$defs must live at the schema root", path)
        self.check_object(node, path)
        self.check_refs(node, path)
        self.recurse(node, path)

    def check_keyword(self, key: str, value: object, path: str) -> None:
        """Check one keyword and its scalar value."""
        if key == "title":
            self.add("title_present", "title is schema noise; strip it", path)
        elif key.startswith("x-"):
            self.add(
                "extension_key",
                f"extension key {key!r} belongs on output schemas only",
                path,
            )
        elif key not in STRICT_KEYWORDS:
            self.add(
                "unsupported_keyword", f"{key!r} is outside the strict subset", path
            )
        elif key == "type":
            self.check_type(value, path)
        elif key == "format" and value not in STRICT_FORMATS:
            self.add("unsupported_format", f"format {value!r} is not shared", path)
        elif key == "minItems" and value not in (0, 1):
            self.add("min_items", f"minItems must be 0 or 1, got {value!r}", path)
        elif key == "enum" and (
            not isinstance(value, list)
            or not all(isinstance(v, _PRIMITIVES) for v in value)
        ):
            self.add("enum_not_primitive", "enum values must be primitives", path)

    def check_type(self, value: object, path: str) -> None:
        """Check a ``type`` value against the shared type names."""
        types = value if isinstance(value, list) else [value]
        for name in types:
            if name not in STRICT_TYPES:
                self.add("unsupported_type", f"type {name!r} is not allowed", path)

    def check_object(self, node: Mapping[str, Any], path: str) -> None:
        """Require every object schema to be closed."""
        if node.get("type") == "object" or "properties" in node:
            extra = node.get("additionalProperties", "missing")
            if extra is not False:
                self.add(
                    "open_object",
                    f"object schema needs additionalProperties: false "
                    f"(found {extra!r})",
                    path,
                )

    def check_refs(self, node: Mapping[str, Any], path: str) -> None:
        """Check ``$ref`` targets and the ``allOf``-with-``$ref`` rule."""
        ref = node.get("$ref")
        if isinstance(ref, str) and (
            not ref.startswith(_DEFS_PREFIX)
            or ref[len(_DEFS_PREFIX) :] not in self.defs
        ):
            self.add(
                "unknown_ref", f"$ref {ref!r} must point at a root $defs entry", path
            )
        members = node.get("allOf")
        if isinstance(members, list) and any(
            isinstance(m, Mapping) and "$ref" in m for m in members
        ):
            self.add(
                "allof_ref", "allOf must not contain a $ref member", path + "/allOf"
            )

    def recurse(self, node: Mapping[str, Any], path: str) -> None:
        """Descend into the subschemas of ``node``."""
        for name, sub in node.get("properties", {}).items():
            self.check(sub, f"{path}/properties/{name}")
        if "items" in node:
            self.check(node["items"], f"{path}/items")
        for keyword in ("anyOf", "allOf"):
            for index, sub in enumerate(node.get(keyword, [])):
                self.check(sub, f"{path}/{keyword}/{index}")
        extra = node.get("additionalProperties")
        if isinstance(extra, Mapping):
            self.check(extra, f"{path}/additionalProperties")


def strict_clean(schema: Mapping[str, Any]) -> list[Finding]:
    """Report every way ``schema`` leaves the Anthropic/OpenAI strict subset.

    Rules: object root; only ``STRICT_KEYWORDS`` (no ``title``, no ``x-``
    keys, no numeric or string bounds); ``STRICT_TYPES`` and
    ``STRICT_FORMATS`` only; ``minItems`` 0 or 1; primitive ``enum`` values;
    ``additionalProperties: false`` on every object; ``$ref`` only to a root
    ``$defs`` entry, never inside ``allOf``, never recursive. Returns an
    empty list for a clean schema; the schema itself is never modified.
    """
    if not isinstance(schema, Mapping) or schema.get("type") != "object":
        return [
            Finding(
                rule="root_not_object",
                message="input schemas must be a mapping with root type 'object'",
                path="",
            )
        ]
    defs = schema.get("$defs", {})
    if not isinstance(defs, Mapping):
        return [
            Finding(rule="bad_defs", message="$defs must be a mapping", path="/$defs")
        ]
    checker = _StrictChecker(defs)
    checker.check(schema, "", root=True)
    for name, sub in defs.items():
        checker.check(sub, f"/$defs/{name}")
    for name in _recursive_defs(defs):
        checker.add(
            "recursive_ref", f"$defs entry {name!r} refers to itself", f"/$defs/{name}"
        )
    return checker.findings


__all__ = [
    "SCHEMA_DIALECT",
    "STRICT_FORMATS",
    "STRICT_KEYWORDS",
    "STRICT_TYPES",
    "NoTitleGenerator",
    "close_objects",
    "input_schema_for",
    "output_schema_for",
    "schema_for",
    "strict_clean",
    "strip_keys",
    "strip_titles",
]
