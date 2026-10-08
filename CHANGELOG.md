# octools Changelog

All notable changes to this project will be documented in this file.

## [1.2.0] - 2026-10-08

### Added 1.2.0

- octools is open source under the MIT license, with the Python package on PyPI as `octools` and a TypeScript package on npm as `@opscogs/octools` released at the same version (OCI-640)
- Language-neutral `spec/`: JSON Schemas for the descriptor and envelopes, `vocabulary.json` with `SPEC_VERSION`, vocabularies and fallbacks, and conformance fixtures every implementation passes, per OCTL-0008 (OCI-640)

### Fixed 1.2.0

- `OCTool`, `validate_tool`, `to_mcp_tool` and `to_anthropic_tool` reject a tool name that ends in a newline, which the name patterns accepted (OCI-640)
- `scripts/sync_claude_config.py` reads a `globs` value wrapped over several lines (flow or block list) and fails on front matter it cannot assign, instead of writing an always-on rule (OCI-640) (BKP-UR-0001)

## [1.1.0] - 2026-09-27

### Added 1.1.0

- Listing helpers (`summarize_provider`, `summarize_tool`, `ToolSummary`, `InputSummary`, `render_listing`, `render_markdown_table`, `LISTING_STYLES`) render a provider's tools as `table` / `md` / `txt` / `json` listings, with a `pages` flag for tools that take a `cursor`
- `octools list SPEC` CLI (`python -m octools list`, console script `octools`) prints one of those listings for a provider named as a module, a `module:attr` object or a zero-argument factory, with `--output-format`, `-o/--output-file`, `--pretty` and `--access`, exit codes 0 / 1 / 2 / 130 and a JSON error object under `--output-format json`
- `RecordsEnvelope` and `TabularEnvelope` carry `stop_reason` and a computed `resumable`, and strict input accepts a `resumable` that agrees with `next_cursor`
- Envelope input and output schemas declare `resumable` as optional, and it is dumped only when `truncated` is true, so an untruncated result keeps the 1.0 shape
- `TabularEnvelope.column_descriptions`, one optional description per column
- `warnings` on `RecordsEnvelope` and `TabularEnvelope`, left out of the dump when empty
- `ArtifactRef.role`, optional free text naming what an artifact is to the run
- `octools.example`, a demo provider for `octools list octools.example` smoke tests; not part of the public API

### Changed 1.1.0

- `SPEC_VERSION` is `"1.1"`; a consumer test pinning `"1.0"` must update
- Truncated records and tabular dumps, `records_schema` and `tabular_schema` include `resumable`; assert on the keys you need, not whole dumps
- Reserved envelope subclass field names are `role` and `source`; a subclass defining `stop_reason` or `warnings` drops them and inherits the octools fields
- A subclass that defines its own `resumable` keeps dumping it always, with it required in its output schema, exactly as under 1.0; the truncated-only dump and optional schema apply to the octools `resumable` only

## [1.0.0] - 2026-09-26

### Added 1.0.0

- `to_mcp_tool` takes `name_prefix` like `to_anthropic_tool`, checked against the new `MCP_NAME_RE`
- Column kinds `ip_block` and `big_integer`, and the optional `column_scales` chart hint (`ColumnScale`, `COLUMN_SCALES`) on `TabularEnvelope`
- `validate_tabular` opt-in cell check against `column_kinds`, one `cell_kind` finding per failing column
- `read_envelope` tolerant reader for envelopes from another process: drops unknown keys and reads unknown vocabulary values as their fallback
- Fallback constants for every closed vocabulary: `COLUMN_KIND_FALLBACK`, `COLUMN_SCALE_FALLBACK`, `SENSITIVITY_FALLBACK`, `RESULT_KIND_FALLBACK`, `ACCESS_FALLBACK`, and `VOCABULARY_FALLBACKS`
- Published compatibility contract for 1.x, reserved envelope subclass field names, the 1.x scope fence and the `octools >= 1.0, < 2` dependency-range rule
- Release tags move the cited `ur:planned` upstream requests in the tag's milestone to `ur:delivered` (`scripts/deliver_upstream_requests.py`)

### Changed 1.0.0

- `SPEC_VERSION` is `"1.0"`; a consumer test pinning `"0.1"` must update
- `total_count` accepts a non-negative decimal string for counts above 2^53 - 1
- `OCTool` rejects a coroutine or async-generator `func` with `OCToolError`
- `ANTHROPIC_NAME_RE` allows 128 characters
- `TabularEnvelope` omits `column_kinds` from the dump when unset
- pydantic dependency is `>= 2.12, < 3`

## [0.2.0] - 2026-09-13

### Added 0.2.0

- `merge_providers` concatenates listings without deduplicating so `validate_provider` sees collisions in the union

## [0.1.1] - 2026-09-09

### Added 0.1.1

- Consumer upstream-request intake: GitHub issue form, `ur:` states, and `scripts/sync_upstream_requests.py` JSONL mirror (`docs/dev/upstream_requests.md`)

### Changed 0.1.1

- Changelog rule tags bullets with a Linear key or a GitHub issue key

### Fixed 0.1.1

- Raise the declared pydantic floor to `>= 2.12` so it matches `Field(exclude_if=...)` on the result envelopes

## [0.1.0] - 2026-09-04

### Added 0.1.0

- Result paging on `RecordsEnvelope` and `TabularEnvelope`: optional `total_count` and opaque `next_cursor` (present only when `truncated`), with the `cursor` / `limit` input convention; design note `OCTL-0002`
- `OCTool` frozen keyword-only descriptor (spec v0.1): name rule, description, `input_schema` / `output_schema`, `result_kind`, `access` / `target`, MCP safety hints, `deprecated`, `meta`, `func`; `OCToolError`; `ToolProvider` protocol and `check_tool_listing`
- Schema helpers: `input_schema_for` / `output_schema_for` / `schema_for`, `strip_titles` / `strip_keys` / `close_objects`, and `strict_clean`
- Result envelopes as pydantic models: `RecordsEnvelope[T]`, `TabularEnvelope`, `ArtifactRef` / `ArtifactEnvelope` with `sensitivity: "inherits_input"`
- Converters with no SDK dependency: `to_mcp_tool` (lossless, `_meta` under `com.opscogs.octools/`) and `to_anthropic_tool`
- `validate_tool` / `validate_provider` returning `Finding` data
