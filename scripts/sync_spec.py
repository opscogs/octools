"""Generate the language-neutral spec files from the installed ``octools``.

The Python models are the source of the wire format. This script writes
``spec/vocabulary.json`` (``SPEC_VERSION``, every closed vocabulary with its
fallback, and the language-neutral constants of the public API) and
``spec/schema/*.schema.json`` (the JSON Schemas of the descriptor, the
envelopes, a finding and a listing row). Output is deterministic and laid
out the way Prettier formats JSON, so the files pass ``prettier --check``.
The curated fixtures under ``spec/fixtures/`` are not generated.

Run with no arguments to rewrite the generated files and remove schema files
nothing generates; run with ``--check`` to report drift and exit 1 without
writing.
"""

from __future__ import annotations

import argparse
import dataclasses
import inspect
import json
import sys
import typing
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, TypeAdapter, create_model

import octools
from octools import (
    ACCESS_FALLBACK,
    ACCESS_KINDS,
    ALIAS_OF_KEY,
    ANTHROPIC_NAME_RE,
    COLUMN_KIND_FALLBACK,
    COLUMN_KINDS,
    COLUMN_SCALE_FALLBACK,
    COLUMN_SCALES,
    LISTING_STYLES,
    MAX_SENTENCES,
    MCP_META_NAMESPACE,
    MCP_NAME_RE,
    MIN_SENTENCES,
    NAME_RE,
    RESULT_KIND_FALLBACK,
    RESULT_KINDS,
    SCHEMA_DIALECT,
    SCHEMA_ESCAPE_KEY,
    SENSITIVITY_FALLBACK,
    SPEC_VERSION,
    STRICT_FORMATS,
    STRICT_KEYWORDS,
    STRICT_TYPES,
    TABULAR_DEF_NAME,
    Finding,
    NoTitleGenerator,
    OCTool,
    RecordsEnvelope,
    Sensitivity,
    ToolSummary,
    artifact_schema,
    schema_for,
    tabular_schema,
)
from octools.schema import output_schema_for

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_NAME = "scripts/sync_spec.py"
PRINT_WIDTH = 80
"""Prettier's default ``printWidth``; a flat array must fit within it."""
INDENT = "  "


def _flat(value: object) -> str | None:
    """Return ``value`` on one line, or None when Prettier always expands it."""
    if isinstance(value, dict):
        return None if value else "{}"
    if isinstance(value, list):
        parts = [_flat(item) for item in value]
        if any(part is None for part in parts):
            return None
        return "[" + ", ".join(typing.cast(list[str], parts)) + "]"
    return json.dumps(value, ensure_ascii=False)


def _forced_break(items: list[object]) -> bool:
    """Return True for an array Prettier always breaks: lists of lists, each >1."""
    return len(items) > 1 and all(
        isinstance(item, list) and len(item) > 1 for item in items
    )


def _render(value: object, depth: int, used: int, suffix: str) -> str:
    """Render ``value`` at ``depth``; ``used`` columns precede it on its line."""
    if isinstance(value, dict) and value:
        inner = INDENT * (depth + 1)
        lines = []
        for index, (key, sub) in enumerate(value.items()):
            label = f"{inner}{json.dumps(key, ensure_ascii=False)}: "
            tail = "," if index < len(value) - 1 else ""
            lines.append(label + _render(sub, depth + 1, len(label), tail) + tail)
        return "{\n" + "\n".join(lines) + "\n" + INDENT * depth + "}"
    flat = _flat(value)
    if not isinstance(value, list) or not value:
        return typing.cast(str, flat)
    fits = flat is not None and used + len(flat) + len(suffix) <= PRINT_WIDTH
    if fits and not _forced_break(value):
        return typing.cast(str, flat)
    inner = INDENT * (depth + 1)
    lines = []
    for index, item in enumerate(value):
        tail = "," if index < len(value) - 1 else ""
        lines.append(inner + _render(item, depth + 1, len(inner), tail) + tail)
    return "[\n" + "\n".join(lines) + "\n" + INDENT * depth + "]"


def render_json(value: object) -> str:
    """Return ``value`` as JSON laid out as Prettier formats it, with a newline.

    Objects are always expanded, one key per line. An array of scalars (or of
    such arrays) stays on one line when it fits in ``PRINT_WIDTH`` columns
    with its trailing comma; otherwise, or when it holds an object, it is
    expanded one item per line.
    """
    return _render(value, 0, 0, "") + "\n"


def _vocabulary_entry(
    type_name: str,
    values_name: str | None,
    values: tuple[str, ...],
    fallback_name: str,
    fallback: str | None,
) -> dict[str, object]:
    """Describe one closed vocabulary: its values, in order, and its fallback.

    ``type_name`` is the exported literal type; ``values_name`` and
    ``fallback_name`` are the exported constants holding the values (None
    when no tuple is exported) and the fallback.
    """
    return {
        "fallback": fallback,
        "fallback_constant": fallback_name,
        "type": type_name,
        "values": list(values),
        "values_constant": values_name,
    }


def vocabulary() -> dict[str, object]:
    """Return the vocabulary document: spec version, vocabularies and constants."""
    vocabularies = {
        "access": _vocabulary_entry(
            "Access", "ACCESS_KINDS", ACCESS_KINDS, "ACCESS_FALLBACK", ACCESS_FALLBACK
        ),
        "column_kinds": _vocabulary_entry(
            "ColumnKind",
            "COLUMN_KINDS",
            COLUMN_KINDS,
            "COLUMN_KIND_FALLBACK",
            COLUMN_KIND_FALLBACK,
        ),
        "column_scales": _vocabulary_entry(
            "ColumnScale",
            "COLUMN_SCALES",
            COLUMN_SCALES,
            "COLUMN_SCALE_FALLBACK",
            COLUMN_SCALE_FALLBACK,
        ),
        "result_kind": _vocabulary_entry(
            "ResultKind",
            "RESULT_KINDS",
            RESULT_KINDS,
            "RESULT_KIND_FALLBACK",
            RESULT_KIND_FALLBACK,
        ),
        "sensitivity": _vocabulary_entry(
            "Sensitivity",
            None,
            typing.get_args(Sensitivity),
            "SENSITIVITY_FALLBACK",
            SENSITIVITY_FALLBACK,
        ),
    }
    constants: dict[str, object] = {
        "ALIAS_OF_KEY": ALIAS_OF_KEY,
        "ANTHROPIC_NAME_RE": ANTHROPIC_NAME_RE.pattern,
        "LISTING_STYLES": list(LISTING_STYLES),
        "MAX_SENTENCES": MAX_SENTENCES,
        "MCP_META_NAMESPACE": MCP_META_NAMESPACE,
        "MCP_NAME_RE": MCP_NAME_RE.pattern,
        "MIN_SENTENCES": MIN_SENTENCES,
        "NAME_RE": NAME_RE.pattern,
        "SCHEMA_DIALECT": SCHEMA_DIALECT,
        "SCHEMA_ESCAPE_KEY": SCHEMA_ESCAPE_KEY,
        "STRICT_FORMATS": sorted(STRICT_FORMATS),
        "STRICT_KEYWORDS": sorted(STRICT_KEYWORDS),
        "STRICT_TYPES": sorted(STRICT_TYPES),
        "TABULAR_DEF_NAME": TABULAR_DEF_NAME,
    }
    return {
        "constants": constants,
        "spec_version": SPEC_VERSION,
        "vocabularies": vocabularies,
    }


def _descriptor_model() -> type[BaseModel]:
    """Build a closed model of the descriptor's wire fields (all but ``func``)."""
    hints = typing.get_type_hints(OCTool)
    fields: dict[str, Any] = {}
    for field in dataclasses.fields(OCTool):
        if field.name == "func":
            continue
        if field.default is not dataclasses.MISSING:
            default: object = field.default
        elif field.default_factory is not dataclasses.MISSING:
            default = field.default_factory()
        else:
            default = ...
        fields[field.name] = (hints[field.name], default)
    doc = (inspect.getdoc(OCTool) or "").split("\n\n")[0]
    return create_model(  # type: ignore[call-overload,no-any-return]
        "OCToolDescriptor",
        __config__=ConfigDict(extra="forbid"),
        __doc__=doc,
        **fields,
    )


def descriptor_schema() -> dict[str, Any]:
    """Return the schema of a descriptor as data: every field except ``func``."""
    schema = schema_for(_descriptor_model())
    schema["properties"]["name"]["pattern"] = NAME_RE.pattern
    return schema


def _dataclass_schema(cls: type) -> dict[str, Any]:
    """Return the serialization schema of a dataclass, without titles."""
    return TypeAdapter(cls).json_schema(
        schema_generator=NoTitleGenerator, mode="serialization"
    )


SCHEMAS: Mapping[str, Callable[[], dict[str, Any]]] = {
    "artifact_envelope": artifact_schema,
    "descriptor": descriptor_schema,
    "finding": lambda: _dataclass_schema(Finding),
    "records_envelope": lambda: output_schema_for(RecordsEnvelope[dict[str, Any]]),
    "tabular_envelope": tabular_schema,
    "tool_summary": lambda: _dataclass_schema(ToolSummary),
}
"""Each generated schema file's stem and the function that builds its schema."""


def _with_dialect(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``schema`` with ``$schema`` naming the 2020-12 dialect first."""
    return {"$schema": SCHEMA_DIALECT, **schema}


def expected_files(root: Path) -> dict[Path, str]:
    """Map every generated file path under root to its expected content."""
    spec = root / "spec"
    expected = {spec / "vocabulary.json": render_json(vocabulary())}
    for stem, build in sorted(SCHEMAS.items()):
        path = spec / "schema" / f"{stem}.schema.json"
        expected[path] = render_json(_with_dialect(build()))
    return expected


def extra_files(root: Path, expected: dict[Path, str]) -> list[Path]:
    """Return files under ``spec/schema`` that nothing generates."""
    return sorted(
        path
        for path in (root / "spec" / "schema").glob("*")
        if path.is_file() and path not in expected
    )


def sync(root: Path, check: bool) -> int:
    """Write (or, with check, compare) the generated files. Return exit code."""
    expected = expected_files(root)
    drift = [
        path
        for path, content in expected.items()
        if not path.exists() or path.read_text() != content
    ]
    extra = extra_files(root, expected)
    for path in drift:
        state = "stale" if path.exists() else "missing"
        print(f"{state}: {path.relative_to(root).as_posix()}")
    for path in extra:
        print(f"extra: {path.relative_to(root).as_posix()}")
    if check:
        if drift or extra:
            print(f"out of date; run: python {SCRIPT_NAME}", file=sys.stderr)
            return 1
        return 0
    for path in drift:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected[path])
    for path in extra:
        path.unlink()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the sync CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate spec/vocabulary.json and spec/schema/ from octools "
            f"{octools.__version__}."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report out-of-date generated files and exit 1 without writing",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root (defaults to this script's repository)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point: sync or check the generated spec files."""
    args = build_parser().parse_args(argv)
    return sync(args.root, args.check)


if __name__ == "__main__":
    sys.exit(main())
