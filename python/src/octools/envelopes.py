"""Result envelopes every ``OCTool`` result is wrapped in.

A tool result is always a JSON object. Record-shaped results use
``RecordsEnvelope``; column-shaped results whose columns are only known at
run time use ``TabularEnvelope``, published once here so a tool that
consumes another tool's table declares its argument by ``$ref`` instead of
redefining ``columns`` and ``rows``; file-producing tools use
``ArtifactEnvelope``. All three are pydantic models so their schemas are
generated, never hand-written.

The two list-shaped envelopes page the same way (OCTL-0002): ``truncated``
says the list was cut short, an opaque ``next_cursor`` says how to fetch
the rest, and ``total_count`` is given only when the source knows it
exactly. ``stop_reason`` names what stopped a truncated read early, and
the computed ``resumable`` (``next_cursor is not None``) says whether the
read can go on: a truncated read with ``resumable`` false is over. A dump
carries ``resumable`` only when ``truncated`` is true, so a complete result
keeps the 1.0 shape; an absent ``resumable`` reads as false. A subclass
that defines its own ``resumable`` dumps it always and requires it in its
output schema. Both list envelopes carry ``warnings`` beside the data,
left out of the dump when empty. A paged tool accepts ``cursor`` and
``limit`` arguments by convention; the envelope carries the response half
only.

Constructing an envelope or calling ``model_validate`` is strict: unknown
keys and unknown vocabulary values raise, so a producer's typo fails in its
own tests. A dumped list envelope validates again: a ``resumable`` key on
input is checked against ``next_cursor`` and not stored. ``read_envelope``
is the tolerant entry point for an envelope from another process
(OCTL-0006): it drops unknown keys and reads an unknown vocabulary value as
that vocabulary's fallback, and checks everything else.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    SerializerFunctionWrapHandler,
    ValidationInfo,
    computed_field,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from octools.schema import output_schema_for

Cell = str | int | float | bool | None
"""A tabular cell: scalars only, so the envelope stays strict-clean."""
ColumnKind = Literal[
    "text",
    "number",
    "integer",
    "boolean",
    "timestamp",
    "ip",
    "fqdn",
    "mac",
    "ip_block",
    "big_integer",
]
"""The closed ``column_kinds`` vocabulary; ``COLUMN_KINDS`` lists the same values."""
COLUMN_KINDS: tuple[str, ...] = get_args(ColumnKind)
"""Every ``ColumnKind`` value, in documentation order."""
COLUMN_KIND_FALLBACK: ColumnKind = "text"
"""How ``read_envelope`` reads a kind it does not know: every cell is text."""
_NUMERIC_KINDS: tuple[str, ...] = ("number", "integer", "big_integer")
"""The kinds a non-null ``column_scales`` entry may apply to."""
ColumnScale = Literal["linear", "log10", "log2"]
"""The closed ``column_scales`` vocabulary; ``COLUMN_SCALES`` lists the same values."""
COLUMN_SCALES: tuple[str, ...] = get_args(ColumnScale)
"""Every ``ColumnScale`` value, in documentation order."""
COLUMN_SCALE_FALLBACK: ColumnScale | None = None
"""How ``read_envelope`` reads a scale it does not know: no hint."""
Sensitivity = Literal["inherits_input"]
"""The closed ``ArtifactEnvelope.sensitivity`` vocabulary."""
SENSITIVITY_FALLBACK: Sensitivity = "inherits_input"
"""How ``read_envelope`` reads a sensitivity it does not know.

``inherits_input`` is the most conservative reading, and only values less
restrictive than it may be added, so degrading to it is always fail-safe.
"""
VOCABULARY_FALLBACKS: Mapping[str, str | None] = {
    "column_kinds": COLUMN_KIND_FALLBACK,
    "column_scales": COLUMN_SCALE_FALLBACK,
    "sensitivity": SENSITIVITY_FALLBACK,
}
"""Every closed envelope vocabulary, by field name, with its fallback."""
_DECIMAL_RE = re.compile(r"0|[1-9][0-9]*")
TABULAR_DEF_NAME = "TabularEnvelope"
"""The ``$defs`` key under which ``TabularEnvelope`` appears when nested."""
_TOLERANT = "octools.tolerant"
"""Validation-context key under which ``read_envelope`` relaxes parsing."""


def _tolerant(info: ValidationInfo) -> bool:
    """Return True when validation runs under ``read_envelope``."""
    return isinstance(info.context, Mapping) and info.context.get(_TOLERANT) is True


class _Envelope(BaseModel):
    """Base for every envelope: closed objects, no unknown keys."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_unknown_keys(cls, data: object, info: ValidationInfo) -> object:
        """Under ``read_envelope``, drop keys this model does not declare.

        Computed fields count as declared, so the model checks them.
        """
        if _tolerant(info) and isinstance(data, Mapping):
            known = cls.model_fields.keys() | cls.model_computed_fields.keys()
            return {key: data[key] for key in data if key in known}
        return data


class _PagedEnvelope(_Envelope):
    """Base for the list envelopes: ``resumable`` is dumped only when truncated.

    Both schema modes declare ``resumable`` as an optional boolean, so a dump
    passes a closed input schema that nests the envelope by ``$ref``. A
    subclass that defines its own ``resumable`` keeps pydantic's handling of
    it: dumped always, and required in its output schema.
    """

    @classmethod
    def _owns_resumable(cls) -> bool:
        """Return True when ``resumable`` is one ``octools`` itself defines."""
        field = cls.model_computed_fields["resumable"]
        return field.wrapped_property in _OCTOOLS_RESUMABLE

    @model_serializer(mode="wrap")
    def _dump_resumable_when_truncated(  # noqa: ANN202
        self, handler: SerializerFunctionWrapHandler
    ):
        """Dump ``resumable`` only beside a ``truncated`` that is true.

        The return type is left unannotated so pydantic keeps the model's own
        serialization schema rather than one built from the annotation.
        """
        data = handler(self)
        if self._owns_resumable() and data.get("truncated") is not True:
            data.pop("resumable", None)
        return data

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """Declare ``resumable`` as an optional boolean in both schema modes.

        A subclass that defines its own ``resumable`` keeps its output schema
        as pydantic builds it; its input schema still declares the key, so a
        dump passes a closed input schema that nests the envelope by ``$ref``.
        """
        json_schema = handler(core_schema)
        owns = cls._owns_resumable()
        if not owns and handler.mode != "validation":
            return json_schema
        target = handler.resolve_ref_schema(json_schema)
        target["properties"]["resumable"] = {
            "description": cls.model_computed_fields["resumable"].description,
            "type": "boolean",
        }
        if not owns:
            return json_schema
        target["required"] = [
            name for name in target["required"] if name != "resumable"
        ]
        return json_schema

    @model_validator(mode="before")
    @classmethod
    def _consume_resumable(cls, data: object) -> object:
        """Check a ``resumable`` key against ``next_cursor``, then drop it.

        ``resumable`` is computed on output, so a truncated dump carries it;
        reading it back checks it rather than storing it, in strict and
        tolerant mode alike, because a contradiction is corrupt data, not
        version skew.
        """
        if not (isinstance(data, Mapping) and "resumable" in data):
            return data
        data = dict(data)
        claimed = data.pop("resumable")
        if claimed is not (data.get("next_cursor") is not None):
            raise ValueError(f"resumable {claimed!r} contradicts next_cursor")
        return data


def _check_paging(
    *,
    returned: int,
    truncated: bool,
    total_count: int | str | None,
    next_cursor: str | None,
    stop_reason: str | None,
) -> None:
    """Raise when the paging fields contradict the list they describe."""
    if next_cursor is not None and not truncated:
        raise ValueError("next_cursor is only given when truncated is true")
    if stop_reason is not None and not truncated:
        raise ValueError("stop_reason is only given when truncated is true")
    if isinstance(total_count, str) and not _DECIMAL_RE.fullmatch(total_count):
        raise ValueError(
            f"total_count {total_count!r} is not a non-negative decimal string"
        )
    if total_count is not None and int(total_count) < returned:
        raise ValueError(f"total_count {total_count} is below the {returned} returned")


def _descriptions_fit(descriptions: object, columns: object) -> bool:
    """Return True when ``descriptions`` is absent or one str-or-None per column."""
    if descriptions is None:
        return True
    return (
        isinstance(descriptions, list)
        and isinstance(columns, list)
        and len(descriptions) == len(columns)
        and all(entry is None or isinstance(entry, str) for entry in descriptions)
    )


def _is_none(value: object) -> bool:
    """Tell the serializer to omit an optional envelope field that is unset."""
    return value is None


_TOTAL_COUNT_DESCRIPTION = (
    "Exact size of the full result when the source knows it, as an integer, or "
    "as a decimal string when above 2^53 - 1; omitted when unknown or "
    "approximate."
)
_TRUNCATED_DESCRIPTION = (
    "True when a cap, a stop or an interrupted read cut the result short. "
    "A truncated read whose resumable is false is the terminal case: it "
    "ended for good and there is nothing left to follow."
)
_NEXT_CURSOR_DESCRIPTION = (
    "Opaque token that resumes the read where it stopped, present only "
    "when resumable is true; pass it back as the tool's cursor argument, "
    "unchanged."
)


def _stop_reason_description(items: str) -> str:
    """Describe ``stop_reason`` for a list of ``items``."""
    return (
        "Why the read stopped early. Well-known values include run_deadline, "
        "page_count, record_limit, interrupted and cursor_stalled; omitted when "
        "the read ended naturally or the limit simply cut it. A cursor_stalled read "
        "publishes no next_cursor, because following it would serve the same "
        f"{items} again."
    )


def _resumable_description(items: str) -> str:
    """Describe ``resumable`` for a list of ``items``."""
    return (
        f"True when next_cursor is present and following it reads more {items}; "
        "false when this read is over: do not call again with the same "
        "arguments. Present only when truncated is true; absent reads as false."
    )


def _is_empty(value: object) -> bool:
    """Tell the serializer to omit a list-envelope ``warnings`` that is empty."""
    return value == []


_WARNINGS_DESCRIPTION = "Non-fatal problems the caller should relay, one per entry."


class RecordsEnvelope[T](_PagedEnvelope):
    """Records whose keys follow the item schema, with an honest cap."""

    records: list[T] = Field(
        description="Result records; keys and order follow the item schema."
    )
    count: int = Field(
        description="Number of records returned, after any cap; equals len(records)."
    )
    truncated: bool = Field(description=_TRUNCATED_DESCRIPTION)
    total_count: int | str | None = Field(
        default=None, exclude_if=_is_none, description=_TOTAL_COUNT_DESCRIPTION
    )
    next_cursor: str | None = Field(
        default=None, exclude_if=_is_none, description=_NEXT_CURSOR_DESCRIPTION
    )
    stop_reason: str | None = Field(
        default=None,
        exclude_if=_is_none,
        description=_stop_reason_description("records"),
    )
    warnings: list[str] = Field(
        default_factory=list, exclude_if=_is_empty, description=_WARNINGS_DESCRIPTION
    )

    @computed_field(description=_resumable_description("records"))  # type: ignore[prop-decorator]
    @property
    def resumable(self) -> bool:
        """True when ``next_cursor`` is present, so following it reads more."""
        return self.next_cursor is not None

    @model_validator(mode="after")
    def _check_paged(self) -> RecordsEnvelope[T]:
        """Require count to match the records and the paging fields to agree."""
        if len(self.records) != self.count:
            raise ValueError(
                f"count {self.count} does not match the {len(self.records)} "
                "records returned"
            )
        _check_paging(
            returned=self.count,
            truncated=self.truncated,
            total_count=self.total_count,
            next_cursor=self.next_cursor,
            stop_reason=self.stop_reason,
        )
        return self


class TabularEnvelope(_PagedEnvelope):
    """Columns and rows for results whose shape is only known at run time."""

    columns: list[str] = Field(description="Column names, in row order.")
    rows: list[list[Cell]] = Field(
        description="Rows of scalar cells; each row has one cell per column."
    )
    row_count: int = Field(
        description="Number of rows returned, after any cap; equals len(rows)."
    )
    truncated: bool = Field(description=_TRUNCATED_DESCRIPTION)
    column_kinds: list[ColumnKind] | None = Field(
        default=None,
        exclude_if=_is_none,
        description=(
            "Optional per-column kind, one per column, from COLUMN_KINDS: text, "
            "number, integer, boolean, timestamp (RFC 3339 date-time), ip (v4 or "
            "v6), fqdn, mac, ip_block (address, CIDR prefix or first-last range), "
            "big_integer (integer, or a decimal string beyond 2^53 - 1)."
        ),
    )
    column_scales: list[ColumnScale | None] | None = Field(
        default=None,
        exclude_if=_is_none,
        description=(
            "Optional per-column chart scale hint, one per column, from "
            "COLUMN_SCALES: linear, log10, log2; only on number, integer and "
            "big_integer columns, null for no hint."
        ),
    )
    column_descriptions: list[str | None] | None = Field(
        default=None,
        exclude_if=_is_none,
        description=(
            "One short description per column, in column order; null where a "
            "column has none."
        ),
    )
    total_count: int | str | None = Field(
        default=None, exclude_if=_is_none, description=_TOTAL_COUNT_DESCRIPTION
    )
    next_cursor: str | None = Field(
        default=None, exclude_if=_is_none, description=_NEXT_CURSOR_DESCRIPTION
    )
    stop_reason: str | None = Field(
        default=None,
        exclude_if=_is_none,
        description=_stop_reason_description("rows"),
    )
    warnings: list[str] = Field(
        default_factory=list, exclude_if=_is_empty, description=_WARNINGS_DESCRIPTION
    )

    @computed_field(description=_resumable_description("rows"))  # type: ignore[prop-decorator]
    @property
    def resumable(self) -> bool:
        """True when ``next_cursor`` is present, so following it reads more."""
        return self.next_cursor is not None

    @model_validator(mode="before")
    @classmethod
    def _read_unknown_vocabulary(cls, data: object, info: ValidationInfo) -> object:
        """Under ``read_envelope``, read unknown kinds and scales as fallbacks.

        A scale reads as ``None`` too when its column's kind is not numeric
        after that (including a kind read as text) or ``column_kinds`` is
        absent, since a scale hint is always safe to drop. A malformed
        ``column_descriptions`` is dropped for the same reason.
        """
        if not (_tolerant(info) and isinstance(data, Mapping)):
            return data
        data = dict(data)
        if not _descriptions_fit(data.get("column_descriptions"), data.get("columns")):
            data.pop("column_descriptions", None)
        kinds, scales = data.get("column_kinds"), data.get("column_scales")
        if isinstance(kinds, list):
            kinds = [
                COLUMN_KIND_FALLBACK
                if isinstance(kind, str) and kind not in COLUMN_KINDS
                else kind
                for kind in kinds
            ]
            data["column_kinds"] = kinds
        if isinstance(scales, list):
            numeric = [
                isinstance(kinds, list)
                and index < len(kinds)
                and kinds[index] in _NUMERIC_KINDS
                for index in range(len(scales))
            ]
            data["column_scales"] = [
                scale
                if not isinstance(scale, str)
                or (scale in COLUMN_SCALES and numeric[index])
                else COLUMN_SCALE_FALLBACK
                for index, scale in enumerate(scales)
            ]
        return data

    @model_validator(mode="after")
    def _check_consistent(self) -> TabularEnvelope:
        """Rows, row_count and column_kinds agree with columns; paging fields agree."""
        if len(self.rows) != self.row_count:
            raise ValueError(
                f"row_count {self.row_count} does not match the {len(self.rows)} "
                "rows returned"
            )
        width = len(self.columns)
        for index, row in enumerate(self.rows):
            if len(row) != width:
                raise ValueError(f"row {index} has {len(row)} cells, expected {width}")
        if self.column_kinds is not None and len(self.column_kinds) != width:
            raise ValueError(
                f"column_kinds has {len(self.column_kinds)} entries, expected {width}"
            )
        if self.column_scales is not None:
            self._check_scales(width)
        if (
            self.column_descriptions is not None
            and len(self.column_descriptions) != width
        ):
            raise ValueError(
                f"column_descriptions has {len(self.column_descriptions)} entries, "
                f"expected {width}"
            )
        _check_paging(
            returned=self.row_count,
            truncated=self.truncated,
            total_count=self.total_count,
            next_cursor=self.next_cursor,
            stop_reason=self.stop_reason,
        )
        return self

    def _check_scales(self, width: int) -> None:
        """Require one scale per column, and non-null scales on numeric kinds."""
        scales = self.column_scales or []
        if len(scales) != width:
            raise ValueError(
                f"column_scales has {len(scales)} entries, expected {width}"
            )
        for index, scale in enumerate(scales):
            if scale is None:
                continue
            if self.column_kinds is None:
                raise ValueError("column_scales needs column_kinds")
            kind = self.column_kinds[index]
            if kind not in _NUMERIC_KINDS:
                raise ValueError(
                    f"column {self.columns[index]!r} has scale {scale!r} but kind "
                    f"{kind!r}; scales apply to {', '.join(_NUMERIC_KINDS)}"
                )


_OCTOOLS_RESUMABLE = frozenset(
    model.model_computed_fields["resumable"].wrapped_property
    for model in (RecordsEnvelope, TabularEnvelope)
)
"""The ``resumable`` properties whose dump and schema ``_PagedEnvelope`` shapes."""


class ArtifactRef(_Envelope):
    """Where one produced artifact lives and what it is."""

    reference: str = Field(
        description="Reference the caller can cite: the path or id the sink returned."
    )
    media_type: str = Field(description="IANA media type, e.g. 'image/svg+xml'.")
    bytes: int = Field(description="Size of the artifact in bytes.")
    width: int | None = Field(
        default=None,
        exclude_if=_is_none,
        description="Pixel width when the artifact is an image; omitted otherwise.",
    )
    height: int | None = Field(
        default=None,
        exclude_if=_is_none,
        description="Pixel height when the artifact is an image; omitted otherwise.",
    )
    role: str | None = Field(
        default=None,
        exclude_if=_is_none,
        description="What the artifact is to the run, such as csv, plan or summary.",
    )


class ArtifactEnvelope(_Envelope):
    """Result of a tool that produces a file rather than data to read."""

    artifact: ArtifactRef = Field(description="The primary artifact produced.")
    artifacts: list[ArtifactRef] = Field(
        default_factory=list,
        description="Further artifacts produced alongside the primary, if any.",
    )
    warnings: list[str] = Field(default_factory=list, description=_WARNINGS_DESCRIPTION)
    sensitivity: Sensitivity = Field(
        default="inherits_input",
        description=(
            "Per-field extras cannot annotate a file, so the artifact is treated "
            "as containing every input column."
        ),
    )

    @field_validator("sensitivity", mode="before")
    @classmethod
    def _read_unknown_sensitivity(cls, value: object, info: ValidationInfo) -> object:
        """Under ``read_envelope``, read an unknown sensitivity as the fallback."""
        if _tolerant(info) and isinstance(value, str):
            return value if value in get_args(Sensitivity) else SENSITIVITY_FALLBACK
        return value


def read_envelope[E: _Envelope](
    model: type[E], data: Mapping[str, object] | str | bytes
) -> E:
    """Parse an envelope another process produced, tolerating newer additions.

    ``model`` is ``RecordsEnvelope[T]``, ``TabularEnvelope`` or
    ``ArtifactEnvelope``; a ``str`` or ``bytes`` ``data`` is parsed as JSON.
    Unknown keys are dropped at the envelope level and in nested envelope
    models, but not inside ``records``, whose model decides for itself. An
    unknown value in a vocabulary reads as its ``VOCABULARY_FALLBACKS`` entry,
    and a scale on a column that is not numeric reads as ``None``. Every
    other check still runs and raises ``ValidationError``.
    """
    if not (isinstance(model, type) and issubclass(model, _Envelope)):
        raise TypeError(f"read_envelope needs an octools envelope model, got {model!r}")
    parsed = json.loads(data) if isinstance(data, str | bytes) else data
    if isinstance(parsed, Mapping):
        parsed = dict(parsed)
    return model.model_validate(parsed, context={_TOLERANT: True})


def records_schema(item: type[BaseModel]) -> dict[str, Any]:
    """Return the ``output_schema`` of a records envelope over ``item`` records."""
    return output_schema_for(RecordsEnvelope[item])  # type: ignore[valid-type]


def tabular_schema() -> dict[str, Any]:
    """Return the shared tabular envelope schema (the published ``$ref`` target)."""
    return output_schema_for(TabularEnvelope)


def artifact_schema() -> dict[str, Any]:
    """Return the artifact envelope schema."""
    return output_schema_for(ArtifactEnvelope)


__all__ = [
    "COLUMN_KINDS",
    "COLUMN_KIND_FALLBACK",
    "COLUMN_SCALES",
    "COLUMN_SCALE_FALLBACK",
    "SENSITIVITY_FALLBACK",
    "TABULAR_DEF_NAME",
    "VOCABULARY_FALLBACKS",
    "ArtifactEnvelope",
    "ArtifactRef",
    "Cell",
    "ColumnKind",
    "ColumnScale",
    "RecordsEnvelope",
    "Sensitivity",
    "TabularEnvelope",
    "artifact_schema",
    "read_envelope",
    "records_schema",
    "tabular_schema",
]
