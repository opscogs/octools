"""Cell-level check of a ``TabularEnvelope`` against its ``column_kinds``.

Parsing an envelope checks the kind vocabulary, never a cell's content.
``validate_tabular`` is the opt-in content check a producer runs in its own
tests (``assert validate_tabular(envelope) == []``). It reports at most one
finding per column, so it stays bounded on a table of any size.
"""

from __future__ import annotations

import ipaddress
import math
import re
from collections.abc import Callable
from datetime import datetime

from octools.envelopes import Cell, TabularEnvelope
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


__all__ = ["validate_tabular"]
