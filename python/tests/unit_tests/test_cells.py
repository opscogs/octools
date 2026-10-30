"""Tests for validate_tabular."""

import enum
import ipaddress
from datetime import date
from typing import Literal

import pytest
from pydantic import BaseModel, Field, IPvAnyAddress

from octools import (
    COLUMN_KINDS,
    Finding,
    TabularEnvelope,
    tabular_from_models,
    validate_tabular,
)

BIG = 2**53
CELLS = {
    "text": (["", "a b"], [1, True, 1.5]),
    "number": ([0, -3, 1.5, BIG], [True, float("nan"), float("inf"), "1"]),
    "integer": ([0, -(BIG - 1), BIG - 1], [BIG, -BIG, 1.0, False, "1"]),
    "boolean": ([True, False], [0, 1, "true"]),
    "timestamp": (
        ["2026-09-26T12:00:00Z", "2026-09-26t12:00:00.123+02:00"],
        ["2026-09-26", "2026-09-26T12:00:00", "2026-13-01T00:00:00Z", 0],
    ),
    "ip": (["192.0.2.1", "2001:db8::1"], ["192.0.2.0/24", "host", 3232235521]),
    "fqdn": (
        ["localhost", "a-b.example.test.", "x" * 63 + ".test"],
        [
            "",
            ".",
            "-a.test",
            "a-.test",
            "a..test",
            "x" * 64,
            "a_b.test",
            ("a" * 63 + ".") * 4,
            1,
        ],
    ),
    "mac": (
        ["00:1a:2B:3c:4d:5e", "00-1a-2b-3c-4d-5e", "00:1a:2b:3c:4d:5e:6f:70"],
        ["00:1a-2b:3c:4d:5e", "001a2b3c4d5e", "00:1a:2b:3c:4d", "00:1a:2b:3c:4d:5g"],
    ),
    "ip_block": (
        [
            "192.0.2.1",
            "192.0.2.1/24",
            "2001:db8::/32",
            "192.0.2.1-192.0.2.9",
            "2001:db8::1-2001:db8::1",
        ],
        [
            "192.0.2.9-192.0.2.1",
            "192.0.2.1-2001:db8::1",
            "192.0.2.0/33",
            "192.0.2.1-",
            "a-b-c",
            "host",
            1,
        ],
    ),
    "big_integer": (
        [0, -1, BIG * BIG, "0", "-12", str(2**128)],
        ["", "-", "01", "-0x1", "1.0", " 1", "1\n", True, 1.5],
    ),
}


def table(kind: str, cells: list) -> TabularEnvelope:
    return TabularEnvelope(
        columns=["c"],
        rows=[[cell] for cell in cells],
        row_count=len(cells),
        truncated=False,
        column_kinds=[kind],
    )


def test_cells_cover_every_kind():
    assert set(CELLS) == set(COLUMN_KINDS)


@pytest.mark.parametrize(
    ("kind", "cell"),
    [(kind, cell) for kind, (good, _) in CELLS.items() for cell in [*good, None]],
)
def test_cell_fits(kind, cell):
    assert validate_tabular(table(kind, [cell])) == []


@pytest.mark.parametrize(
    ("kind", "cell"), [(kind, cell) for kind, (_, bad) in CELLS.items() for cell in bad]
)
def test_cell_does_not_fit(kind, cell):
    (finding,) = validate_tabular(table(kind, [cell]))
    assert finding.rule == "cell_kind"
    assert finding.path == "/rows/0/0"
    assert finding.message.startswith(f"column 'c' ({kind}):")
    assert "row 0" in finding.message


def test_no_column_kinds_has_nothing_to_check():
    env = TabularEnvelope(columns=["c"], rows=[[1]], row_count=1, truncated=False)
    assert validate_tabular(env) == []


def test_one_finding_per_column_in_column_order():
    rows = [["a", 1, "2001:db8::/64"], [None, "n/a", "x"], ["b", "n/a", None]] * 2
    env = TabularEnvelope(
        columns=["name", "size", "block"],
        rows=rows,
        row_count=len(rows),
        truncated=False,
        column_kinds=["text", "big_integer", "ip_block"],
    )
    assert validate_tabular(env) == [
        Finding(
            rule="cell_kind",
            message="column 'size' (big_integer): 4 of 6 cells do not fit; first at "
            "row 1: 'n/a'",
            path="/rows/1/1",
        ),
        Finding(
            rule="cell_kind",
            message="column 'block' (ip_block): 2 of 6 cells do not fit; first at "
            "row 1: 'x'",
            path="/rows/1/2",
        ),
    ]


class _Color(enum.Enum):
    RED = "red"


class _Rank(enum.IntEnum):
    LOW = 1


class _Row(BaseModel):
    color: _Color
    rank: _Rank
    addr: IPvAnyAddress
    net: ipaddress.IPv6Network
    hidden: str = Field(default="x", exclude=True)
    day: date = date(2026, 1, 1)
    on: Literal[True] = True
    half: float | None = 0.5


def test_tabular_from_models_reads_enums_and_skips_excluded_fields():
    row = _Row(color=_Color.RED, rank=_Rank.LOW, addr="10.0.0.1", net="2001:db8::/32")
    table = tabular_from_models(_Row, [row])
    assert table.columns == ["color", "rank", "addr", "net", "day", "on", "half"]
    assert table.column_kinds == [
        "text",
        "integer",
        "ip",
        "ip_block",
        "text",
        "boolean",
        "number",
    ]
    assert table.rows == [
        ["red", 1, "10.0.0.1", "2001:db8::/32", "2026-01-01", True, 0.5]
    ]
    assert table.column_descriptions is None
    assert validate_tabular(table) == []
