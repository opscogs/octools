"""Tests for octools.envelopes."""

import json
import typing

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError, computed_field

from octools import (
    COLUMN_KIND_FALLBACK,
    COLUMN_KINDS,
    COLUMN_SCALE_FALLBACK,
    COLUMN_SCALES,
    SENSITIVITY_FALLBACK,
    TABULAR_DEF_NAME,
    VOCABULARY_FALLBACKS,
    ArtifactEnvelope,
    ArtifactRef,
    RecordsEnvelope,
    TabularEnvelope,
    artifact_schema,
    input_schema_for,
    output_schema_for,
    read_envelope,
    records_schema,
    strict_clean,
    tabular_schema,
)


class Item(BaseModel):
    name: str
    size: int | None = None


PAGING_ERRORS = [
    ({"next_cursor": "c"}, "next_cursor is only given when truncated is true"),
    ({"stop_reason": "page_count"}, "stop_reason is only given when truncated is true"),
    ({"total_count": 0}, "total_count 0 is below the 1 returned"),
    ({"total_count": "0"}, "total_count 0 is below the 1 returned"),
    *[
        ({"total_count": bad}, "is not a non-negative decimal string")
        for bad in ["", "-1", "01", "1.0", "1e3", " 1"]
    ],
]


def test_records_envelope_dump_omits_unset_paging_fields():
    env = RecordsEnvelope[Item](records=[Item(name="a")], count=1, truncated=False)
    assert env.model_dump(mode="json") == {
        "records": [{"name": "a", "size": None}],
        "count": 1,
        "truncated": False,
    }


def test_records_envelope_paged_dump():
    env = RecordsEnvelope[Item](
        records=[Item(name="a")],
        count=1,
        truncated=True,
        total_count=3,
        next_cursor="opaque-1",
    )
    dumped = env.model_dump(mode="json")
    assert dumped["total_count"] == 3
    assert dumped["next_cursor"] == "opaque-1"
    assert dumped["resumable"] is True
    assert "stop_reason" not in dumped


def _records(**kwargs):
    fields = {"records": [Item(name="a")], "count": 1, "truncated": True, **kwargs}
    return RecordsEnvelope[Item](**fields)


def _table(**kwargs):
    fields = {"columns": ["c"], "rows": [[1]], "row_count": 1, "truncated": True}
    return TabularEnvelope(**{**fields, **kwargs})


PAGED_ENVELOPES = [
    pytest.param(_records, RecordsEnvelope[Item], id="records"),
    pytest.param(_table, TabularEnvelope, id="tabular"),
]
STOPS = [
    ({"stop_reason": "cursor_stalled"}, False),
    ({"stop_reason": "run_deadline", "next_cursor": "c"}, True),
    ({"next_cursor": "c"}, True),
    ({"truncated": False}, False),
]


@pytest.mark.parametrize(("build", "model"), PAGED_ENVELOPES)
@pytest.mark.parametrize(("kwargs", "resumable"), STOPS)
def test_paged_envelope_round_trips_its_dump(build, model, kwargs, resumable):
    env = build(**kwargs)
    dumped = env.model_dump(mode="json")
    assert dumped.get("resumable", False) is env.resumable is resumable
    assert ("resumable" in dumped) is env.truncated
    assert ("stop_reason" in dumped) is ("stop_reason" in kwargs)
    assert model.model_validate(dumped) == env
    assert model.model_validate_json(env.model_dump_json()) == env
    assert read_envelope(model, dumped) == env


def _def_accepts(schema: dict, name: str, instance: dict) -> bool:
    """Tell whether a closed ``$defs`` object schema admits ``instance``'s keys."""
    target = schema["$defs"][name]
    return (
        target["additionalProperties"] is False
        and set(instance) <= set(target["properties"])
        and set(target["required"]) <= set(instance)
    )


@pytest.mark.parametrize(("build", "model"), PAGED_ENVELOPES)
@pytest.mark.parametrize(("kwargs", "resumable"), STOPS)
def test_paged_envelope_dump_fits_a_consumer_input_schema(
    build, model, kwargs, resumable
):
    class Consumer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        data: model

    schema = input_schema_for(Consumer)
    name = schema["properties"]["data"]["$ref"].removeprefix("#/$defs/")
    dumped = build(**kwargs, warnings=["partial"]).model_dump(mode="json")
    assert _def_accepts(schema, name, dumped)
    assert schema["$defs"][name]["properties"]["resumable"]["type"] == "boolean"
    assert strict_clean(schema) == []
    assert Consumer.model_validate({"data": dumped}).data.resumable is resumable


@pytest.mark.parametrize(("build", "model"), PAGED_ENVELOPES)
@pytest.mark.parametrize(
    ("kwargs", "claimed", "match"),
    [
        ({}, True, "resumable True contradicts next_cursor"),
        ({"next_cursor": "c"}, False, "resumable False contradicts next_cursor"),
        ({}, "no", "resumable 'no' contradicts next_cursor"),
        ({"next_cursor": "c"}, 1, "resumable 1 contradicts next_cursor"),
    ],
)
def test_paged_envelope_rejects_a_contradicting_resumable(
    build, model, kwargs, claimed, match
):
    data = {**build(**kwargs).model_dump(mode="json"), "resumable": claimed}
    with pytest.raises(ValidationError, match=match):
        model.model_validate(data)
    with pytest.raises(ValidationError, match=match):
        read_envelope(model, data)


class OwnResumableRecords[T](RecordsEnvelope[T]):
    @computed_field(description="Always published.")  # type: ignore[prop-decorator]
    @property
    def resumable(self) -> bool:
        return self.next_cursor is not None


class OwnResumableTable(TabularEnvelope):
    @computed_field(description="Always published.")  # type: ignore[prop-decorator]
    @property
    def resumable(self) -> bool:
        return self.next_cursor is not None


class InheritedResumableTable(TabularEnvelope):
    note: str | None = None


def _own_records(**kwargs):
    fields = {"records": [Item(name="a")], "count": 1, "truncated": True, **kwargs}
    return OwnResumableRecords[Item](**fields)


def _own_table(**kwargs):
    fields = {"columns": ["c"], "rows": [[1]], "row_count": 1, "truncated": True}
    return OwnResumableTable(**{**fields, **kwargs})


def _inherited_table(**kwargs):
    fields = {"columns": ["c"], "rows": [[1]], "row_count": 1, "truncated": True}
    return InheritedResumableTable(**{**fields, **kwargs})


RESUMABLE_OWNERS = [
    pytest.param(_records, RecordsEnvelope[Item], False, id="records"),
    pytest.param(_table, TabularEnvelope, False, id="tabular"),
    pytest.param(_inherited_table, InheritedResumableTable, False, id="inherited"),
    pytest.param(_own_records, OwnResumableRecords[Item], True, id="own-records"),
    pytest.param(_own_table, OwnResumableTable, True, id="own-tabular"),
]


@pytest.mark.parametrize(("build", "model", "own"), RESUMABLE_OWNERS)
@pytest.mark.parametrize(("kwargs", "resumable"), STOPS)
def test_a_subclass_defining_resumable_always_dumps_it(
    build, model, own, kwargs, resumable
):
    env = build(**kwargs)
    dumped = env.model_dump(mode="json")
    assert ("resumable" in dumped) is (own or env.truncated)
    assert dumped.get("resumable", False) is resumable
    assert model.model_validate(dumped) == env
    assert model.model_validate_json(env.model_dump_json()) == env
    assert read_envelope(model, dumped) == env
    with pytest.raises(ValidationError, match="contradicts next_cursor"):
        model.model_validate({**dumped, "resumable": not resumable})


@pytest.mark.parametrize(("build", "model", "own"), RESUMABLE_OWNERS)
def test_a_subclass_defining_resumable_requires_it_in_its_output_schema(
    build, model, own
):
    schema = output_schema_for(model)
    assert ("resumable" in schema["required"]) is own
    assert schema["properties"]["resumable"]["type"] == "boolean"
    assert build().model_dump(mode="json").keys() <= schema["properties"].keys()


@pytest.mark.parametrize(("build", "model", "own"), RESUMABLE_OWNERS)
@pytest.mark.parametrize(("kwargs", "resumable"), STOPS)
def test_every_resumable_owner_passes_a_closed_input_schema(
    build, model, own, kwargs, resumable
):
    output = output_schema_for(model)
    assert ("resumable" in output["required"]) is own

    class Consumer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        data: model

    schema = input_schema_for(Consumer)
    name = schema["properties"]["data"]["$ref"].removeprefix("#/$defs/")
    dumped = build(**kwargs).model_dump(mode="json")
    assert _def_accepts(schema, name, dumped)
    assert "resumable" not in schema["$defs"][name]["required"]
    assert Consumer.model_validate({"data": dumped}).data.resumable is resumable


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"count": 2}, "count 2 does not match the 1 records returned"),
        *PAGING_ERRORS,
    ],
)
def test_records_envelope_rejects_inconsistent_paging(kwargs, match):
    fields = {"records": [Item(name="a")], "count": 1, "truncated": False, **kwargs}
    with pytest.raises(ValidationError, match=match):
        RecordsEnvelope[Item](**fields)


def test_records_envelope_truncated_without_cursor_is_allowed():
    env = RecordsEnvelope[Item](records=[], count=0, truncated=True, total_count=0)
    assert env.next_cursor is None


def test_records_schema_shape():
    schema = records_schema(Item)
    assert schema["required"] == ["records", "count", "truncated"]
    assert schema["properties"]["records"]["items"] == {"$ref": "#/$defs/Item"}
    assert {"total_count", "next_cursor", "stop_reason"} <= set(schema["properties"])
    assert schema["properties"]["next_cursor"] == {
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "default": None,
        "description": schema["properties"]["next_cursor"]["description"],
    }
    assert "title" not in schema
    assert schema["$defs"]["Item"]["properties"]["name"] == {"type": "string"}


@pytest.mark.parametrize(
    ("schema", "items"),
    [(records_schema(Item), "records"), (tabular_schema(), "rows")],
)
def test_paged_schema_declares_stop_reason_and_resumable(schema, items):
    stop, resumable = (
        schema["properties"]["stop_reason"],
        schema["properties"]["resumable"],
    )
    assert not {"stop_reason", "resumable", "warnings"} & set(schema["required"])
    assert stop["anyOf"] == [{"type": "string"}, {"type": "null"}]
    assert stop["default"] is None
    assert stop["description"].startswith("Why the read stopped early. Well-known")
    assert resumable == {"type": "boolean", "description": resumable["description"]}
    assert f"reads more {items};" in resumable["description"]
    assert resumable["description"].endswith(
        "Present only when truncated is true; absent reads as false."
    )
    assert (
        schema["properties"]["warnings"] == artifact_schema()["properties"]["warnings"]
    )
    for name in ("truncated", "next_cursor", "stop_reason", "resumable", "warnings"):
        assert "e.g." not in schema["properties"][name]["description"]


def test_tabular_envelope_valid():
    env = TabularEnvelope(
        columns=["host", "count"],
        rows=[["a", 1], ["b", None]],
        row_count=2,
        truncated=False,
        column_kinds=["fqdn", "integer"],
    )
    assert env.row_count == 2
    assert "column_kinds" not in env.model_copy(
        update={"column_kinds": None}
    ).model_dump(mode="json")
    assert env.model_dump(mode="json").keys() == {
        "columns",
        "rows",
        "row_count",
        "truncated",
        "column_kinds",
    }


def test_column_kinds_vocabulary_is_closed():
    kinds = list(COLUMN_KINDS)
    env = TabularEnvelope(
        columns=kinds,
        rows=[],
        row_count=0,
        truncated=False,
        column_kinds=kinds,
    )
    assert env.column_kinds == kinds
    with pytest.raises(ValidationError, match="column_kinds"):
        TabularEnvelope(
            columns=["h"],
            rows=[],
            row_count=0,
            truncated=False,
            column_kinds=["hostname"],
        )


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"rows": [["a"]]}, "row 0 has 1 cells, expected 2"),
        ({"row_count": 2}, "row_count 2 does not match the 1 rows returned"),
        ({"column_kinds": ["text"]}, "column_kinds has 1 entries, expected 2"),
        (
            {"column_kinds": ["text", "integer"], "column_scales": ["log2"]},
            "column_scales has 1 entries, expected 2",
        ),
        ({"column_scales": [None, "log2"]}, "column_scales needs column_kinds"),
        (
            {"column_kinds": ["fqdn", "integer"], "column_scales": ["log2", None]},
            "column 'host' has scale 'log2' but kind 'fqdn'",
        ),
        (
            {"column_kinds": ["text", "integer"], "column_scales": [None, "ln"]},
            "column_scales",
        ),
        (
            {"column_descriptions": ["h"]},
            "column_descriptions has 1 entries, expected 2",
        ),
        ({"column_descriptions": ["h", 2]}, "column_descriptions"),
        ({"rows": [["a", {"nested": 1}]]}, "rows"),
        ({"extra": 1}, "extra"),
        *PAGING_ERRORS,
    ],
)
def test_tabular_envelope_invalid(kwargs, match):
    fields = {
        "columns": ["host", "count"],
        "rows": [["a", 1]],
        "row_count": 1,
        "truncated": False,
    }
    fields.update(kwargs)
    with pytest.raises(ValidationError, match=match):
        TabularEnvelope(**fields)


def test_tabular_schema_is_strict_clean_and_shared_ref():
    schema = tabular_schema()
    assert schema["required"] == [
        "columns",
        "rows",
        "row_count",
        "truncated",
    ]
    assert {"total_count", "next_cursor", "stop_reason"} <= set(schema["properties"])
    kinds = schema["properties"]["column_kinds"]["anyOf"][0]
    assert kinds["items"] == {"enum": list(COLUMN_KINDS), "type": "string"}
    assert strict_clean(input_schema_for(TabularEnvelope)) == []

    class Consumer(BaseModel):
        data: TabularEnvelope

    consumer = input_schema_for(Consumer)
    assert consumer["properties"]["data"] == {"$ref": f"#/$defs/{TABULAR_DEF_NAME}"}
    assert TABULAR_DEF_NAME in consumer["$defs"]
    assert strict_clean(consumer) == []


def test_artifact_envelope_defaults():
    env = ArtifactEnvelope(
        artifact=ArtifactRef(
            reference="mem://1.svg", media_type="image/svg+xml", bytes=12
        )
    )
    dumped = env.model_dump(mode="json")
    assert dumped["artifacts"] == []
    assert dumped["warnings"] == []
    assert dumped["sensitivity"] == "inherits_input"
    assert "width" not in dumped["artifact"] and "height" not in dumped["artifact"]
    ref = artifact_schema()["$defs"]["ArtifactRef"]["properties"]
    assert ref["width"]["default"] is None


@pytest.mark.parametrize(
    ("role", "dumped_ref"),
    [
        (None, {"reference": "r", "media_type": "text/csv", "bytes": 1}),
        (
            "csv",
            {"reference": "r", "media_type": "text/csv", "bytes": 1, "role": "csv"},
        ),
    ],
)
def test_artifact_ref_role_is_dumped_only_when_set(role, dumped_ref):
    ref = ArtifactRef(reference="r", media_type="text/csv", bytes=1, role=role)
    env = ArtifactEnvelope(artifact=ref, artifacts=[ref])
    dumped = env.model_dump(mode="json")
    assert dumped["artifact"] == dumped["artifacts"][0] == dumped_ref
    assert ArtifactEnvelope.model_validate(dumped) == env
    assert read_envelope(ArtifactEnvelope, json.dumps(dumped)).artifact.role == role
    prop = artifact_schema()["$defs"]["ArtifactRef"]["properties"]["role"]
    assert prop["anyOf"] == [{"type": "string"}, {"type": "null"}]
    assert prop["description"] == (
        "What the artifact is to the run, such as csv, plan or summary."
    )
    assert "role" not in VOCABULARY_FALLBACKS


@pytest.mark.parametrize(("build", "model"), PAGED_ENVELOPES)
def test_list_envelope_warnings_are_dumped_only_when_present(build, model):
    assert "warnings" not in build().model_dump(mode="json")
    env = build(warnings=["snapshot b lacks table t"])
    dumped = env.model_dump(mode="json")
    assert dumped["warnings"] == ["snapshot b lacks table t"]
    assert model.model_validate(dumped) == env == read_envelope(model, dumped)


@pytest.mark.parametrize("descriptions", [["Host name.", None], [None, None]])
def test_column_descriptions_round_trip(descriptions):
    env = TabularEnvelope(
        columns=["host", "size"],
        rows=[["a", 1]],
        row_count=1,
        truncated=False,
        column_descriptions=descriptions,
    )
    dumped = env.model_dump(mode="json")
    assert dumped["column_descriptions"] == descriptions
    assert read_envelope(TabularEnvelope, dumped) == env
    assert "column_descriptions" not in _table().model_dump(mode="json")
    field = tabular_schema()["properties"]["column_descriptions"]
    assert field["anyOf"][0]["items"] == {
        "anyOf": [{"type": "string"}, {"type": "null"}]
    }
    assert "e.g." not in field["description"]


@pytest.mark.parametrize(
    "descriptions", ["Host name.", ["one"], ["a", "b", "c"], ["a", 2], {"a": "b"}]
)
def test_read_envelope_drops_malformed_column_descriptions(descriptions):
    data = {
        "columns": ["host", "size"],
        "rows": [],
        "row_count": 0,
        "truncated": False,
        "column_descriptions": descriptions,
    }
    assert read_envelope(TabularEnvelope, data).column_descriptions is None
    with pytest.raises(ValidationError, match="column_descriptions"):
        TabularEnvelope.model_validate(data)


def test_artifact_envelope_rejects_other_sensitivity():
    with pytest.raises(ValidationError, match="sensitivity"):
        ArtifactEnvelope(
            artifact=ArtifactRef(reference="r", media_type="image/png", bytes=1),
            sensitivity="none",
        )


def test_artifact_schema_shape():
    schema = artifact_schema()
    assert set(schema["properties"]) == {
        "artifact",
        "artifacts",
        "warnings",
        "sensitivity",
    }
    assert schema["required"] == ["artifact"]
    assert schema["properties"]["sensitivity"]["const"] == "inherits_input"
    assert "ArtifactRef" in schema["$defs"]


@pytest.mark.parametrize("total", [2, "2", str(2**64)])
def test_total_count_is_an_integer_or_a_decimal_string(total):
    env = RecordsEnvelope[Item](
        records=[Item(name="a")], count=1, truncated=True, total_count=total
    )
    assert env.model_dump(mode="json")["total_count"] == total
    schema = records_schema(Item)["properties"]["total_count"]
    assert schema["anyOf"][:2] == [{"type": "integer"}, {"type": "string"}]


@pytest.mark.parametrize("kind", ["number", "integer", "big_integer"])
@pytest.mark.parametrize("scale", [*COLUMN_SCALES, None])
def test_column_scales_on_numeric_kinds(kind, scale):
    env = TabularEnvelope(
        columns=["name", "size"],
        rows=[["a", 1]],
        row_count=1,
        truncated=False,
        column_kinds=["text", kind],
        column_scales=[None, scale],
    )
    assert env.model_dump(mode="json")["column_scales"] == [None, scale]


def test_column_scales_omitted_when_unset_and_strict_clean():
    env = TabularEnvelope(columns=["c"], rows=[], row_count=0, truncated=False)
    assert "column_scales" not in env.model_dump(mode="json")
    scales = tabular_schema()["properties"]["column_scales"]["anyOf"][0]
    assert scales["items"]["anyOf"][0] == {
        "enum": list(COLUMN_SCALES),
        "type": "string",
    }


class StrictItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


class OpenItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str


FUTURE_TABULAR = {
    "columns": ["prefix", "share", "size", "note"],
    "column_kinds": ["cidr_set", "decimal", "big_integer", "text"],
    "column_scales": [None, "log10", "ln", "log2"],
    "rows": [["192.0.2.0/24", "0.5", "256", "x"]],
    "row_count": 1,
    "truncated": True,
    "next_cursor": "c",
    "stop_reason": "producer_reason",
    "resumable": True,
    "role": "chart",
    "source": "snapshot-a",
}
FUTURE_ARTIFACT = {
    "artifact": {
        "reference": "r",
        "media_type": "image/png",
        "bytes": 1,
        "checksum": "abc",
    },
    "artifacts": [{"reference": "s", "media_type": "image/png", "bytes": 2, "dpi": 1}],
    "sensitivity": "public_derived",
    "role": "chart",
}
FUTURE_RECORDS = {
    "records": [{"name": "a", "added": 1}],
    "count": 1,
    "truncated": False,
    "resumable": False,
    "warnings": ["partial"],
}


@pytest.mark.parametrize("encode", [dict, json.dumps, lambda d: json.dumps(d).encode()])
def test_read_envelope_reads_a_future_tabular_envelope(encode):
    env = read_envelope(TabularEnvelope, encode(FUTURE_TABULAR))
    assert env.column_kinds == [COLUMN_KIND_FALLBACK, "text", "big_integer", "text"]
    assert env.column_scales == [None, None, COLUMN_SCALE_FALLBACK, None]
    assert env.rows == FUTURE_TABULAR["rows"]
    assert env.next_cursor == "c"
    assert env.stop_reason == "producer_reason"
    with pytest.raises(ValidationError) as caught:
        TabularEnvelope.model_validate(FUTURE_TABULAR)
    assert {e["loc"][0] for e in caught.value.errors()} == {
        "column_kinds",
        "column_scales",
        "role",
        "source",
    }


def test_read_envelope_reads_a_future_artifact_envelope():
    env = read_envelope(ArtifactEnvelope, FUTURE_ARTIFACT)
    assert env.sensitivity == SENSITIVITY_FALLBACK
    assert env.artifact == ArtifactRef(reference="r", media_type="image/png", bytes=1)
    assert env.artifacts[0].bytes == 2
    with pytest.raises(ValidationError, match="sensitivity"):
        ArtifactEnvelope.model_validate(FUTURE_ARTIFACT)


def test_read_envelope_leaves_record_keys_to_the_record_model():
    open_env = read_envelope(RecordsEnvelope[OpenItem], FUTURE_RECORDS)
    assert open_env.records[0].model_extra == {"added": 1}
    assert (
        read_envelope(
            RecordsEnvelope[Item], {**FUTURE_RECORDS, "records": [{"name": "a"}]}
        ).count
        == 1
    )
    with pytest.raises(ValidationError, match=r"records\.0\.added"):
        read_envelope(RecordsEnvelope[StrictItem], FUTURE_RECORDS)


def test_read_envelope_keeps_a_scale_on_a_numeric_kind():
    data = {
        "columns": ["a", "b"],
        "column_kinds": ["integer", "fqdn"],
        "column_scales": ["log2", "log10"],
        "rows": [],
        "row_count": 0,
        "truncated": False,
    }
    assert read_envelope(TabularEnvelope, data).column_scales == ["log2", None]
    no_kinds = {k: v for k, v in data.items() if k != "column_kinds"}
    assert read_envelope(TabularEnvelope, no_kinds).column_scales == [None, None]


VALID_RECORDS = {
    "records": [{"name": "a"}],
    "count": 1,
    "truncated": False,
    "resumable": False,
}


@pytest.mark.parametrize(
    ("model", "data", "match"),
    [
        (
            TabularEnvelope,
            {**FUTURE_TABULAR, "row_count": 2},
            "row_count 2 does not match",
        ),
        (
            TabularEnvelope,
            {**FUTURE_TABULAR, "column_kinds": [1, "text", "text", "text"]},
            "column_kinds",
        ),
        (
            TabularEnvelope,
            {**FUTURE_TABULAR, "column_scales": [None, None, 2, None]},
            "column_scales",
        ),
        (TabularEnvelope, {**FUTURE_TABULAR, "total_count": "many"}, "decimal string"),
        (
            TabularEnvelope,
            {"columns": ["a"], "rows": [], "row_count": 0},
            "truncated",
        ),
        (TabularEnvelope, ["not", "an", "object"], "TabularEnvelope"),
        (TabularEnvelope, "[1]", "TabularEnvelope"),
        (
            RecordsEnvelope[Item],
            {**VALID_RECORDS, "count": 2},
            "count 2 does not match",
        ),
        (
            RecordsEnvelope[Item],
            {**VALID_RECORDS, "total_count": "many"},
            "decimal string",
        ),
        (
            RecordsEnvelope[Item],
            {
                "records": [{"name": "a"}],
                "count": 1,
                "truncated": False,
                "next_cursor": "c",
            },
            "next_cursor is only given when truncated is true",
        ),
        (RecordsEnvelope[Item], ["not", "an", "object"], "RecordsEnvelope"),
        (RecordsEnvelope[Item], "[1]", "RecordsEnvelope"),
    ],
)
def test_read_envelope_still_rejects_corruption(model, data, match):
    with pytest.raises(ValidationError, match=match):
        read_envelope(model, data)


def test_read_envelope_rejects_an_unknown_sensitivity_type():
    with pytest.raises(ValidationError, match="sensitivity"):
        read_envelope(ArtifactEnvelope, {**FUTURE_ARTIFACT, "sensitivity": 3})


@pytest.mark.parametrize("model", [Item, dict, "TabularEnvelope"])
def test_read_envelope_needs_an_envelope_model(model):
    with pytest.raises(TypeError, match="octools envelope model"):
        read_envelope(model, {})


def _literal_fields(model: type[BaseModel]) -> dict[str, tuple]:
    found = {}
    for name, field in model.model_fields.items():
        stack = [field.annotation]
        while stack:
            annotation = stack.pop()
            if typing.get_origin(annotation) is typing.Literal:
                found[name] = typing.get_args(annotation)
            stack.extend(typing.get_args(annotation))
    return found


def test_every_closed_envelope_vocabulary_declares_a_fallback():
    vocabularies: dict[str, tuple] = {}
    for model in (
        RecordsEnvelope[Item],
        TabularEnvelope,
        ArtifactRef,
        ArtifactEnvelope,
    ):
        vocabularies.update(_literal_fields(model))
    assert set(vocabularies) == set(VOCABULARY_FALLBACKS)
    for name, values in vocabularies.items():
        fallback = VOCABULARY_FALLBACKS[name]
        assert fallback is None or fallback in values, name
