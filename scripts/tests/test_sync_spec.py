"""Test scripts/sync_spec.py."""

import json
from pathlib import Path

import pytest

import octools
from scripts.tests.support import load_script, unload_script


@pytest.fixture(scope="module")
def sync_spec():
    """Load the spec-sync script under a private module name."""
    name, module = load_script("sync_spec.py")
    yield module
    unload_script(name)


GENERATED = [
    "spec/vocabulary.json",
    *(
        f"spec/schema/{stem}.schema.json"
        for stem in (
            "artifact_envelope",
            "descriptor",
            "finding",
            "records_envelope",
            "tabular_envelope",
            "tool_summary",
        )
    ),
]


def test_sync_writes_checks_and_prunes(sync_spec, tmp_path: Path, capsys):
    main = sync_spec.main
    assert main(["--root", str(tmp_path), "--check"]) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [f"missing: {path}" for path in GENERATED]
    assert "out of date" in captured.err
    assert main(["--root", str(tmp_path)]) == 0
    assert main(["--root", str(tmp_path), "--check"]) == 0
    capsys.readouterr()
    vocabulary = tmp_path / "spec/vocabulary.json"
    vocabulary.write_text("{}\n")
    extra = tmp_path / "spec/schema/old.schema.json"
    extra.write_text("{}\n")
    fixture = tmp_path / "spec/fixtures/op/case.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("{}\n")
    assert main(["--root", str(tmp_path), "--check"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "stale: spec/vocabulary.json",
        "extra: spec/schema/old.schema.json",
    ]
    assert main(["--root", str(tmp_path)]) == 0
    assert not extra.exists()
    assert fixture.exists()
    assert main(["--root", str(tmp_path), "--check"]) == 0


def test_vocabulary_matches_the_package(sync_spec):
    vocabulary = sync_spec.vocabulary()
    assert vocabulary["spec_version"] == octools.SPEC_VERSION
    fallbacks = {
        name: entry["fallback"] for name, entry in vocabulary["vocabularies"].items()
    }
    assert fallbacks == {
        **octools.VOCABULARY_FALLBACKS,
        "access": octools.ACCESS_FALLBACK,
        "result_kind": octools.RESULT_KIND_FALLBACK,
    }
    for entry in vocabulary["vocabularies"].values():
        assert entry["type"] in octools.__all__
        assert entry["fallback_constant"] in octools.__all__
        if entry["values_constant"] is not None:
            values = getattr(octools, entry["values_constant"])
            assert entry["values"] == list(values)
    assert set(vocabulary["constants"]) <= set(octools.__all__)


def test_schemas_name_the_dialect_and_close_the_descriptor(sync_spec, tmp_path):
    files = sync_spec.expected_files(tmp_path)
    for path, text in files.items():
        if path.parent.name == "schema":
            assert json.loads(text)["$schema"] == octools.SCHEMA_DIALECT
    descriptor = json.loads(files[tmp_path / "spec/schema/descriptor.schema.json"])
    assert descriptor["additionalProperties"] is False
    assert "func" not in descriptor["properties"]
    assert descriptor["properties"]["name"]["pattern"] == octools.NAME_RE.pattern
    assert set(descriptor["required"]) == {
        "name",
        "description",
        "input_schema",
        "access",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({}, "{}\n"),
        ([], "[]\n"),
        ({"a": [], "b": {}}, '{\n  "a": [],\n  "b": {}\n}\n'),
        ({"a": ["x", 1, None, True]}, '{\n  "a": ["x", 1, null, true]\n}\n'),
        ({"a": [{"b": 1}]}, '{\n  "a": [\n    {\n      "b": 1\n    }\n  ]\n}\n'),
        ([["a", "b"], ["c", "d"]], '[\n  ["a", "b"],\n  ["c", "d"]\n]\n'),
        ([["a", "b"], ["c"]], '[["a", "b"], ["c"]]\n'),
        ({"k": "é"}, '{\n  "k": "é"\n}\n'),
    ],
)
def test_render_json_layout(sync_spec, value, expected):
    assert sync_spec.render_json(value) == expected


@pytest.mark.parametrize(
    ("length", "comma", "flat"),
    [(69, False, True), (70, False, False), (68, True, True), (69, True, False)],
)
def test_render_json_wraps_at_the_print_width(sync_spec, length, comma, flat):
    # '  "k": ["' and '"]' take 11 columns; a trailing comma takes one more.
    item = "a" * length
    value = {"k": [item], "z": 0} if comma else {"k": [item]}
    tail = "," if comma else ""
    expected = (
        f'  "k": ["{item}"]{tail}' if flat else f'  "k": [\n    "{item}"\n  ]{tail}'
    )
    assert expected in sync_spec.render_json(value)
