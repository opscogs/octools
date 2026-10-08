"""A demo tool provider for trying ``octools list`` and for reading a conformant one.

``octools list octools.example`` lists it wherever octools is installed. Four
tools: ``echo_records`` (records envelope, paged), its deprecated alias
``echo``, ``block_sizes`` (tabular envelope) and ``render_badge`` (artifact
envelope written through an injected sink). The tools may change in any
release; this module is not part of the 1.x public API and ``octools.__all__``
does not include it.
"""

import ipaddress
from collections.abc import Callable

from pydantic import BaseModel, Field

from octools.descriptor import OCTool
from octools.envelopes import (
    ArtifactEnvelope,
    ArtifactRef,
    RecordsEnvelope,
    TabularEnvelope,
    artifact_schema,
    records_schema,
    tabular_schema,
)
from octools.schema import input_schema_for

Sink = Callable[[bytes, str], str]


class EchoArgs(BaseModel):
    """Input of ``echo_records``."""

    values: list[str] = Field(description="Strings to echo back, one record each.")
    limit: int = Field(
        default=10,
        description="Maximum records to return, 1 to 100; the tool enforces it.",
    )
    cursor: str | None = Field(
        default=None,
        description="next_cursor from a previous page; omit for the first page.",
    )


class EchoRecord(BaseModel):
    """One record of ``echo_records``: an input string and its position."""

    value: str = Field(
        description="The echoed string.",
        json_schema_extra={"x-sensitivity": "free_text"},
    )
    position: int = Field(description="Zero-based position in the input.")


def echo_records(
    _dependency: None, *, values: list[str], limit: int = 10, cursor: str | None = None
) -> dict[str, object]:
    """Return ``values`` as records, ``limit`` at a time from ``cursor``."""
    args = EchoArgs(values=values, limit=limit, cursor=cursor)
    if not 1 <= args.limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if args.cursor is not None and not args.cursor.isdigit():
        raise ValueError("cursor must be a next_cursor from a previous page")
    start = int(args.cursor) if args.cursor is not None else 0
    stop = start + args.limit
    records = [
        EchoRecord(value=value, position=index)
        for index, value in enumerate(args.values[start:stop], start=start)
    ]
    truncated = stop < len(args.values)
    return RecordsEnvelope[EchoRecord](
        records=records,
        count=len(records),
        truncated=truncated,
        total_count=len(args.values),
        next_cursor=str(stop) if truncated else None,
    ).model_dump(mode="json")


class BlockArgs(BaseModel):
    """Input of ``block_sizes``."""

    prefixes: list[str] = Field(
        description="CIDR prefixes, IPv4 or IPv6, one row each; host bits allowed."
    )


def block_sizes(_dependency: None, *, prefixes: list[str]) -> dict[str, object]:
    """Return each prefix normalized, with its length and address count."""
    args = BlockArgs(prefixes=prefixes)
    rows: list[list[str | int | float | bool | None]] = []
    for prefix in args.prefixes:
        network = ipaddress.ip_network(prefix, strict=False)
        size = network.num_addresses
        rows.append(
            [str(network), network.prefixlen, size if size < 2**53 else str(size)]
        )
    return TabularEnvelope(
        columns=["prefix", "prefix_len", "size"],
        rows=rows,
        row_count=len(rows),
        truncated=False,
        column_kinds=["ip_block", "integer", "big_integer"],
        column_scales=[None, None, "log2"],
    ).model_dump(mode="json")


class BadgeArgs(BaseModel):
    """Input of ``render_badge``."""

    label: str = Field(description="Text on the left half of the badge.")
    value: str = Field(description="Text on the right half of the badge.")


def render_badge(sink: Sink, *, label: str, value: str) -> dict[str, object]:
    """Render a two-part SVG badge, write it through ``sink`` and cite it."""
    args = BadgeArgs(label=label, value=value)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="20">'
        f"<text x='4' y='14'>{args.label}</text><text x='64' y='14'>{args.value}</text>"
        "</svg>"
    ).encode()
    reference = sink(svg, "image/svg+xml")
    return ArtifactEnvelope(
        artifact=ArtifactRef(
            reference=reference,
            media_type="image/svg+xml",
            bytes=len(svg),
            width=120,
            height=20,
        )
    ).model_dump(mode="json")


ECHO_RECORDS = OCTool(
    name="echo_records",
    title="Echo strings as records",
    description=(
        "Return each input string as one record with its position. Use it to "
        "check that a tool round-trip works before calling anything real. "
        "Returns a records envelope; when limit cut the list, truncated is true "
        "and next_cursor fetches the next page."
    ),
    input_schema=input_schema_for(EchoArgs),
    output_schema=records_schema(EchoRecord),
    func=echo_records,
    access="local",
)
ECHO_ALIAS = OCTool(
    name="echo",
    description=(
        "Deprecated alias of echo_records kept for one major version. "
        "Call echo_records instead."
    ),
    input_schema=ECHO_RECORDS.input_schema,
    output_schema=ECHO_RECORDS.output_schema,
    func=echo_records,
    access="local",
    deprecated=True,
    meta={"alias_of": "echo_records"},
)
BLOCK_SIZES = OCTool(
    name="block_sizes",
    title="Address block sizes",
    description=(
        "Return each CIDR prefix normalized, with its length and address count. "
        "Use it to compare how large address blocks are before planning a split. "
        "Returns a tabular envelope; a size beyond 2^53 - 1 is a decimal string."
    ),
    input_schema=input_schema_for(BlockArgs),
    output_schema=tabular_schema(),
    func=block_sizes,
    access="local",
)
RENDER_BADGE = OCTool(
    name="render_badge",
    description=(
        "Render a two-part SVG badge and write it through the injected sink. "
        "Use it when a report needs a small status marker rather than a chart. "
        "Returns an artifact envelope citing the reference the sink returned."
    ),
    input_schema=input_schema_for(BadgeArgs),
    output_schema=artifact_schema(),
    result_kind="artifact",
    func=render_badge,
    access="local",
    meta={"renderer": "svgstatic"},
)
TOOLS: tuple[OCTool, ...] = (ECHO_RECORDS, ECHO_ALIAS, BLOCK_SIZES, RENDER_BADGE)


def all_tools() -> tuple[OCTool, ...]:
    """Return the demo tools; this module is itself a provider."""
    return TOOLS


class ExampleProvider:
    """Class-shaped provider over the same tools as the module."""

    def all_tools(self) -> tuple[OCTool, ...]:
        """Return the demo tools."""
        return TOOLS


def memory_sink(store: dict[str, bytes]) -> Sink:
    """Return a sink that keeps artifacts in ``store`` under ``mem://`` refs."""

    def sink(data: bytes, media_type: str) -> str:
        """Store ``data`` and return its reference."""
        reference = f"mem://{len(store)}.{media_type.split('/')[-1].split('+')[0]}"
        store[reference] = data
        return reference

    return sink


__all__: list[str] = [
    "BLOCK_SIZES",
    "ECHO_ALIAS",
    "ECHO_RECORDS",
    "RENDER_BADGE",
    "TOOLS",
    "ExampleProvider",
    "all_tools",
    "block_sizes",
    "echo_records",
    "memory_sink",
    "render_badge",
]
