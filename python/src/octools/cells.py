"""Cell-level check of a ``TabularEnvelope``, and building one from a model.

Parsing an envelope checks the kind vocabulary, never a cell's content.
``validate_tabular`` is the opt-in content check a producer runs in its own
tests (``assert validate_tabular(envelope) == []``). It reports at most one
finding per column, so it stays bounded on a table of any size.
``tabular_from_models`` builds a table from a pydantic model, so every
producer maps a field's type to a column kind the same way.
"""

from __future__ import annotations

import enum
import ipaddress
import json
import math
import re
import types
import typing
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime

from pydantic import (
    AwareDatetime,
    BaseModel,
    IPvAnyAddress,
    IPvAnyInterface,
    IPvAnyNetwork,
)

from octools.descriptor import OCToolError
from octools.envelopes import Cell, ColumnKind, TabularEnvelope
from octools.findings import Finding

_MAX_SAFE_INTEGER = 2**53 - 1
"""Largest magnitude an ``integer`` cell may hold; beyond it use ``big_integer``."""
_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})"
)
_LABEL_RE = re.compile(r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_MAC_RE = re.compile(r"[0-9A-Fa-f]{2}([:-])[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){4}")
_MAC_LONG_RE = re.compile(r"[0-9A-Fa-f]{2}([:-])[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){6}")
_BIG_INTEGER_RE = re.compile(r"-?(0|[1-9][0-9]*)")


def _is_int(cell: Cell) -> bool:
    """Return True for an ``int`` that is not a ``bool``."""
    return isinstance(cell, int) and not isinstance(cell, bool)


def _is_number(cell: Cell) -> bool:
    """Return True for an ``int`` or a finite ``float``, never a ``bool``."""
    return _is_int(cell) or (isinstance(cell, float) and math.isfinite(cell))


def _is_integer(cell: Cell) -> bool:
    """Return True for an ``int`` a JSON number carries exactly."""
    return (
        isinstance(cell, int)
        and not isinstance(cell, bool)
        and abs(cell) <= _MAX_SAFE_INTEGER
    )


def _is_timestamp(cell: Cell) -> bool:
    """Return True for an RFC 3339 ``date-time`` string with a real date and time."""
    if not (isinstance(cell, str) and _TIMESTAMP_RE.fullmatch(cell)):
        return False
    normalized = cell.upper().replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return True


def _is_ip(cell: Cell) -> bool:
    """Return True for a string ``ipaddress.ip_address`` accepts."""
    if not isinstance(cell, str):
        return False
    try:
        ipaddress.ip_address(cell)
    except ValueError:
        return False
    return True


def _is_fqdn(cell: Cell) -> bool:
    """Return True for dot-separated host labels, at most 253 characters."""
    if not isinstance(cell, str):
        return False
    name = cell.removesuffix(".")
    return 0 < len(name) <= 253 and all(
        _LABEL_RE.fullmatch(label) for label in name.split(".")
    )


def _is_mac(cell: Cell) -> bool:
    """Return True for six or eight hex pairs joined consistently by ``:`` or ``-``."""
    return isinstance(cell, str) and bool(
        _MAC_RE.fullmatch(cell) or _MAC_LONG_RE.fullmatch(cell)
    )


def _is_ip_block(cell: Cell) -> bool:
    """Return True for an address, a CIDR prefix, or a ``first-last`` range."""
    if not isinstance(cell, str):
        return False
    try:
        if "/" in cell:
            ipaddress.ip_network(cell, strict=False)
            return True
        if "-" in cell:
            first_text, _, last_text = cell.partition("-")
            first = ipaddress.ip_address(first_text)
            last = ipaddress.ip_address(last_text)
            return first.version == last.version and first <= last  # type: ignore[operator]
        ipaddress.ip_address(cell)
    except ValueError:
        return False
    return True


def _is_big_integer(cell: Cell) -> bool:
    """Return True for an ``int`` or a string of decimal digits with optional ``-``."""
    return _is_int(cell) or (
        isinstance(cell, str) and bool(_BIG_INTEGER_RE.fullmatch(cell))
    )


_CHECKS: dict[str, Callable[[Cell], bool]] = {
    "text": lambda cell: isinstance(cell, str),
    "number": _is_number,
    "integer": _is_integer,
    "boolean": lambda cell: isinstance(cell, bool),
    "timestamp": _is_timestamp,
    "ip": _is_ip,
    "fqdn": _is_fqdn,
    "mac": _is_mac,
    "ip_block": _is_ip_block,
    "big_integer": _is_big_integer,
}
"""One cell predicate per ``ColumnKind``; ``None`` cells never reach them."""


def validate_tabular(envelope: TabularEnvelope) -> list[Finding]:
    """Report each column holding a cell that does not fit its declared kind.

    Returns ``[]`` when ``column_kinds`` is absent. A ``None`` cell always
    fits. Each failing column yields one ``cell_kind`` finding, in column
    order, whose ``path`` points at the first bad cell (``/rows/3/2``) and
    whose message counts the bad cells and quotes the first. ``tool`` is
    ``None``; a caller may ``dataclasses.replace`` it.
    """
    if envelope.column_kinds is None:
        return []
    findings: list[Finding] = []
    total = len(envelope.rows)
    for column, (name, kind) in enumerate(
        zip(envelope.columns, envelope.column_kinds, strict=True)
    ):
        fits = _CHECKS[kind]
        first: int | None = None
        bad = 0
        for index, row in enumerate(envelope.rows):
            if row[column] is not None and not fits(row[column]):
                bad += 1
                first = index if first is None else first
        if first is not None:
            findings.append(
                Finding(
                    rule="cell_kind",
                    message=(
                        f"column {name!r} ({kind}): {bad} of {total} cells do not "
                        f"fit; first at row {first}: {envelope.rows[first][column]!r}"
                    ),
                    path=f"/rows/{first}/{column}",
                )
            )
    return findings


_TYPE_KINDS: Mapping[object, ColumnKind] = {
    AwareDatetime: "timestamp",
    ipaddress.IPv4Address: "ip",
    ipaddress.IPv6Address: "ip",
    IPvAnyAddress: "ip",
    ipaddress.IPv4Network: "ip_block",
    ipaddress.IPv6Network: "ip_block",
    ipaddress.IPv4Interface: "ip_block",
    ipaddress.IPv6Interface: "ip_block",
    IPvAnyNetwork: "ip_block",
    IPvAnyInterface: "ip_block",
}
"""Field types with a fixed kind; a plain ``datetime`` may lack an offset, so text."""


def _shared_kind(kinds: Iterable[ColumnKind]) -> ColumnKind:
    """Return the kind all share, ``number`` for a numeric mix, else text."""
    distinct = set(kinds)
    if len(distinct) == 1:
        return distinct.pop()
    return "number" if distinct == {"integer", "number"} else "text"


def _value_kind(value: object) -> ColumnKind:
    """Return the kind of one literal or enum value."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    return "number" if isinstance(value, float) else "text"


def _values_kind(values: Iterable[object]) -> ColumnKind:
    """Return the kind the non-null values share."""
    return _shared_kind(_value_kind(value) for value in values if value is not None)


def _column_kind(annotation: object) -> ColumnKind:
    """Return the column kind of a field annotation; anything unknown is text."""
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        return _column_kind(typing.get_args(annotation)[0])
    if origin in (typing.Union, types.UnionType):
        return _shared_kind(
            _column_kind(member)
            for member in typing.get_args(annotation)
            if member is not types.NoneType
        )
    if origin is typing.Literal:
        return _values_kind(typing.get_args(annotation))
    if not isinstance(annotation, type):
        return "text"
    if issubclass(annotation, enum.Enum):
        return _values_kind(member.value for member in annotation)
    if annotation in (bool, int, float):
        return _value_kind(annotation())
    return _TYPE_KINDS.get(annotation, "text")


def _model_cell(value: object, kind: ColumnKind) -> Cell:
    """Return a dumped value as a cell of ``kind``.

    A list or dict is compact JSON text, and so is any other non-string value
    in a text column, so a union such as ``int | str`` still fits its kind.
    """
    if isinstance(value, list | dict) or (
        kind == "text" and not isinstance(value, str | None)
    ):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return typing.cast(Cell, value)


def tabular_from_models(
    model: type[BaseModel],
    items: Iterable[BaseModel],
    *,
    column_kinds: Mapping[str, ColumnKind] | None = None,
    truncated: bool = False,
    next_cursor: str | None = None,
) -> TabularEnvelope:
    """Return ``items`` as a table with ``model``'s fields as columns.

    Columns are the fields in declaration order, under their field names, and
    a field marked ``exclude`` is left out; a value the dump omits is a null
    cell. Each kind comes from the field's annotation, ``Optional`` and
    ``Annotated`` unwrapped: ``AwareDatetime`` is ``timestamp``, since a plain
    ``datetime`` may lack the offset that kind requires; an address is ``ip``,
    a network or interface ``ip_block``; a union, enum or ``Literal`` takes
    the kind its members share, ``number`` for a mix of integers and numbers;
    anything else is ``text``. A list, dict or nested model is compact JSON
    text, as is any other non-string value in a text column. ``column_kinds``
    overrides per column, which is how a column becomes ``big_integer`` or
    ``fqdn``; a key that is not a column raises ``OCToolError``. Field
    descriptions fill ``column_descriptions`` when any field has one.
    ``truncated`` and ``next_cursor`` describe a capped read, under the
    envelope's own checks.
    """
    fields = {
        name: field for name, field in model.model_fields.items() if not field.exclude
    }
    overrides = dict(column_kinds or {})
    unknown = sorted(overrides.keys() - fields.keys())
    if unknown:
        raise OCToolError(f"column_kinds names unknown columns: {unknown}")
    kinds = [
        overrides.get(name, _column_kind(field.annotation))
        for name, field in fields.items()
    ]
    dumps = [item.model_dump(mode="json", by_alias=False) for item in items]
    descriptions = [field.description for field in fields.values()]
    return TabularEnvelope(
        columns=list(fields),
        rows=[
            [
                _model_cell(dump.get(name), kind)
                for name, kind in zip(fields, kinds, strict=True)
            ]
            for dump in dumps
        ],
        row_count=len(dumps),
        truncated=truncated,
        next_cursor=next_cursor,
        column_kinds=kinds,
        column_descriptions=descriptions if any(descriptions) else None,
    )


__all__ = ["tabular_from_models", "validate_tabular"]
