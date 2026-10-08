# Decision log

The current state of every octools architecture decision record (ADR), plus a
dated history of changes. See [README](README.md) for the versioning and status
rules.

Status key: ✅ accepted · 📝 proposed · ❌ rejected · ⚠️ deprecated ·
🔁 superseded

## Current decisions

| ADR                                                            | Title                                        | Status      | Version | Updated    |
| -------------------------------------------------------------- | -------------------------------------------- | ----------- | ------- | ---------- |
| [OCTL-0001](OCTL-0001-descriptor-origin.md)                    | Descriptor origin                            | ✅ accepted | 1.1.1   | 2026-10-08 |
| [OCTL-0002](OCTL-0002-result-paging.md)                        | Result paging                                | ✅ accepted | 1.4.1   | 2026-10-08 |
| [OCTL-0004](OCTL-0004-merge-providers.md)                      | Merging providers                            | ✅ accepted | 1.1.1   | 2026-10-08 |
| [OCTL-0005](OCTL-0005-column-kinds-ip-block-big-integer.md)    | Column kinds `ip_block` and `big_integer`    | ✅ accepted | 1.1.1   | 2026-10-08 |
| [OCTL-0006](OCTL-0006-tolerant-readers.md)                     | Tolerant readers                             | ✅ accepted | 1.3.1   | 2026-10-08 |
| [OCTL-0007](OCTL-0007-human-readable-listings.md)              | Human-readable listings                      | ✅ accepted | 1.0.1   | 2026-10-08 |
| [OCTL-0008](OCTL-0008-language-neutral-spec-and-typescript.md) | Language-neutral spec and TypeScript package | ✅ accepted | 1.0.0   | 2026-10-08 |

## History

Newest entries first.

| Date       | ADR       | Version | Status      | Change                                                                                                                                                                                                                    |
| ---------- | --------- | ------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-10-08 | OCTL-0008 | 1.0.0   | ✅ accepted | Accepted; MIT monorepo with `python/`, `typescript/` and the `spec/` conformance authority; full TypeScript parity on zod v4; lockstep versions; trusted publishing; octools 1.2.0                                        |
| 2026-10-08 | OCTL-0007 | 1.0.1   | ✅ accepted | Wording: CLI rules stated in the record; consumers named generically; neutral decision-makers                                                                                                                             |
| 2026-10-08 | OCTL-0006 | 1.3.1   | ✅ accepted | Remove internal request identifiers; neutral decision-makers                                                                                                                                                              |
| 2026-10-08 | OCTL-0005 | 1.1.1   | ✅ accepted | Remove internal request identifiers; neutral decision-makers                                                                                                                                                              |
| 2026-10-08 | OCTL-0004 | 1.1.1   | ✅ accepted | Neutral decision-makers                                                                                                                                                                                                   |
| 2026-10-08 | OCTL-0002 | 1.4.1   | ✅ accepted | Remove internal request identifiers; neutral decision-makers                                                                                                                                                              |
| 2026-10-08 | OCTL-0001 | 1.1.1   | ✅ accepted | Neutral decision-makers                                                                                                                                                                                                   |
| 2026-09-27 | OCTL-0006 | 1.3.0   | ✅ accepted | `ArtifactRef.role`, optional free text naming what an artifact is to the run, no fallback; a dump rule shapes only the field `octools` defines                                                                            |
| 2026-09-27 | OCTL-0002 | 1.4.0   | ✅ accepted | A subclass that defines its own `resumable` dumps it always and requires it in its output schema, as under 1.0                                                                                                            |
| 2026-09-27 | OCTL-0006 | 1.2.0   | ✅ accepted | A field added in a minor is left out of the dump when it carries nothing new and is optional in output and input-mode schemas; `warnings` on every envelope; reserved subclass fields are `role`, `source`                |
| 2026-09-27 | OCTL-0005 | 1.1.0   | ✅ accepted | `column_descriptions` on `TabularEnvelope`: one entry per column, tolerant on read, first page only when paged                                                                                                            |
| 2026-09-27 | OCTL-0002 | 1.3.0   | ✅ accepted | `resumable` dumped only when truncated, optional in output and input-mode schemas; one `record_limit` definition; `warnings` on list envelopes                                                                            |
| 2026-09-27 | OCTL-0004 | 1.1.0   | ✅ accepted | Open question closed: findings on a merge name the tool only; per-member `validate_provider` gives provenance; an optional `Finding` field arrives in a minor if a consumer asks                                          |
| 2026-09-27 | OCTL-0001 | 1.1.0   | ✅ accepted | Open question closed: 1.x core ships the MCP and Anthropic converters; `to_openai_tool` arrives in a minor on a consumer's upstream request                                                                               |
| 2026-09-27 | OCTL-0002 | 1.2.0   | ✅ accepted | Open question closed: the `cursor` input is a convention confirmed by the producer's paging test; no validator rule and no paging flag                                                                                    |
| 2026-09-27 | OCTL-0006 | 1.1.0   | ✅ accepted | Strict input accepts and checks derived fields, as `read_envelope` does; envelope dumps and schemas may gain keys in a minor; reserved subclass fields are `warnings`, `role`; `SPEC_VERSION` `"1.1"`                     |
| 2026-09-27 | OCTL-0002 | 1.1.0   | ✅ accepted | `stop_reason` (free string, well-known values) and computed `resumable` on both list envelopes; octools 1.1.0                                                                                                             |
| 2026-09-27 | OCTL-0001 | 1.0.1   | ✅ accepted | Wording: `SPEC_VERSION` major `1` is the compatibility contract                                                                                                                                                           |
| 2026-09-27 | OCTL-0007 | 1.0.0   | ✅ accepted | Accepted; `ToolSummary` data summaries, `render_listing` styles, `octools list` command; octools 1.1.0                                                                                                                    |
| 2026-09-26 | OCTL-0006 | 1.0.0   | ✅ accepted | 1.0 stability: contract covers validator rules, converter keys, `Finding`, `ToolProvider`, reserved subclass fields, `__all__`; fallback per vocabulary; tolerant `column_scales`; `SPEC_VERSION` `"1.0"`; `pydantic < 3` |
| 2026-09-26 | OCTL-0005 | 1.0.0   | ✅ accepted | 1.0 stability: tolerant `column_scales`; `SPEC_VERSION` `"1.0"`; `total_count` cross-reference                                                                                                                            |
| 2026-09-26 | OCTL-0004 | 1.0.0   | ✅ accepted | 1.0 stability: optional `Finding` field allowed in a minor                                                                                                                                                                |
| 2026-09-26 | OCTL-0002 | 1.0.0   | ✅ accepted | 1.0 stability: `total_count` is an integer or a decimal string                                                                                                                                                            |
| 2026-09-26 | OCTL-0001 | 1.0.0   | ✅ accepted | 1.0 stability: `result_kind` and `access` fallbacks; synchronous `func`; the 1.x scope fence; name rules; MCP 2026-07-28                                                                                                  |
| 2026-09-26 | OCTL-0006 | 1.0.0   | ✅ accepted | Accepted; octools 1.0.0 is the first release under the contract                                                                                                                                                           |
| 2026-09-26 | OCTL-0005 | 1.0.0   | ✅ accepted | Accepted                                                                                                                                                                                                                  |
| 2026-09-26 | OCTL-0006 | 0.1.0   | 📝 proposed | Tolerant readers (`read_envelope`), minor-release contract, consumer dependency ranges                                                                                                                                    |
| 2026-09-26 | OCTL-0005 | 0.1.0   | 📝 proposed | `ip_block` and `big_integer` kinds, `validate_tabular`, `column_scales`, charting guidance                                                                                                                                |
| 2026-09-26 | OCTL-0004 | 1.0.0   | ✅ accepted | MADR format with versioned front matter                                                                                                                                                                                   |
| 2026-09-26 | OCTL-0002 | 1.0.0   | ✅ accepted | MADR format with versioned front matter                                                                                                                                                                                   |
| 2026-09-26 | OCTL-0001 | 1.0.0   | ✅ accepted | MADR format with versioned front matter                                                                                                                                                                                   |
