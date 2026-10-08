---
status: accepted
version: 1.1.1
date: 2026-10-08
decision-makers: OpsCogs maintainers
---

# OCTL-0001 descriptor origin

## Context and Problem Statement

Several OpsCogs libraries expose functions that an agent runtime calls as
tools. Each runtime speaks a different tool shape (MCP 2025-11-25 and
2026-07-28 `Tool`, Anthropic `tools[]`, OpenAI function tools, pydantic-ai and LangChain tool
definitions), and each library otherwise invents its own way to describe a
tool, its input and output schemas, its side effects and its sensitivity.

The libraries need one descriptor they can all publish, which a consumer can
validate and convert to any runtime's shape without importing the library
that defines the tool. The adopters cover a remote system of record, a local
read-only surface over tabular data whose columns come from SQL at run time,
and an artifact producer that writes to an injected destination rather than
calling a client.

## Decision Drivers

- One vocabulary that maps losslessly onto MCP, the most complete of the
  runtime shapes, and converts to the Anthropic shape as a plain dict.
- Input schemas every major runtime accepts in strict mode: only the
  keywords all of them accept, with bounds that fall outside that subset
  stated in the description and enforced in Python.
- Descriptions written for a model: two to four sentences.
- Platform-neutral access: a tool acts on local data or on a remote system
  of record, never on a named product.
- Result shapes for records, for tables whose columns are known only at run
  time, and for artifacts written to an injected destination.
- A per-field sensitivity hook, a free `meta` bag for library facts, and a
  rename path that keeps the old name alive as a deprecated alias.
- A home with no OpsCogs dependencies and no runtime SDK dependency, so
  every library can depend on it.

## Considered Options

- **A.** An MCP-vocabulary `OCTool` descriptor in a standalone `octools`
  package, with records, tabular and artifact envelopes.
- **B.** One runtime SDK's tool type (MCP, Anthropic or OpenAI) used
  directly as the descriptor.
- **C.** Framework-native tool definitions (pydantic-ai or LangChain).
- **D.** A records-only `AgentTool` descriptor whose access is
  `Literal["local", "<platform>"]`, housed in an existing OpsCogs library.

## Decision Outcome

Chosen option: **A, an MCP-vocabulary `OCTool` descriptor in a standalone
`octools` package**, because it maps onto every runtime shape as a plain dict,
covers all three adopter result shapes, and keeps the dependency direction
one way: every OpsCogs library may depend on `octools`, and `octools` depends
on `pydantic` only.

The descriptor is the `OCTool` dataclass:

- MCP vocabulary: `name`, optional `title`, `description`, `input_schema`,
  `output_schema`, and `read_only_hint`, `destructive_hint`,
  `idempotent_hint`.
- `name` matches `^[a-z][a-z0-9_]{0,47}$` (`NAME_RE`). Forty-eight
  characters leave room for a runtime prefix (`name_prefix` on the
  converters) under the tightest common tool-name limit, 64 characters. The
  converters check the prefixed name against each target's own rule: MCP's
  `^[A-Za-z0-9_.-]{1,128}$` and Anthropic's `^[a-zA-Z0-9_-]{1,128}$`.
- `description` is two to four sentences.
- Input schemas are strict-clean; `strict_clean` reports anything outside
  the subset every runtime accepts.
- `func(dependency, **args)`: the injected dependency comes first (a client,
  a workspace, or a sink), validated keyword arguments after. The contract
  says "dependency", not "client", because an artifact producer receives a
  destination rather than a client. `func` is a plain synchronous callable
  returning a JSON object; construction rejects a coroutine function or an
  async-generator function with `OCToolError`. An async or streaming
  variant arrives as a separate optional field that older runtimes ignore,
  never as a change to what `func` may be.
- `access` is `Literal["local", "remote"]` plus an optional
  `target: str | None`. The read-only hint describes the access target:
  writing through an injected sink is still read-only with respect to the
  system of record. A reader that meets an `access` value it does not know
  treats it as `"remote"`, the safer policy assumption.
- `result_kind` is `"records"` or `"artifact"`. `RecordsEnvelope` carries
  records with an item schema; `TabularEnvelope` is a shared `$ref` for
  records whose columns are known only at run time (the explicit schema
  escape for open columns from SQL); `ArtifactEnvelope` carries what the
  injected sink returned. A reader that meets a `result_kind` it does not
  know treats it as `"records"`. The fallback rule for every closed
  vocabulary is in [OCTL-0006](./OCTL-0006-tolerant-readers.md).
- Sensitivity is the `x-sensitivity` extension key on input fields;
  artifacts carry `sensitivity: "inherits_input"`.
- Domain facts go in `meta`. `deprecated=True` marks an alias kept alive
  after a rename.
- `SPEC_VERSION` is the descriptor format version, and a provider's
  `all_tools()` listing is deterministic.

### Converters

1.x core ships two converters, `to_mcp_tool` and `to_anthropic_tool`. Each
returns a plain dict and imports no runtime SDK. An OpenAI converter is not
part of 1.x core until a consumer asks for one through an upstream request.
When one does, it arrives in a minor release as an additive
`to_openai_tool` export, which [OCTL-0006](./OCTL-0006-tolerant-readers.md)
allows: a plain dict, no SDK dependency, applying the OpenAI strict-mode
transform, in which every property is listed in `required` and an optional
property becomes a union with `null`.

### Deliberate deviations from the sources

Each item below is a place where this descriptor settles something the MCP
specification and the industry-practice mapping above leave open or state
differently.

| Topic         | Industry-practice baseline       | This descriptor                                                 |
| ------------- | -------------------------------- | --------------------------------------------------------------- |
| Class name    | `AgentTool`                      | `OCTool`                                                        |
| Access values | `Literal["local", "<platform>"]` | `Literal["local", "remote"]` plus `target: str \| None`         |
| Result kinds  | records envelope only            | `result_kind: "records" \| "artifact"`, artifact envelope added |
| Tabular shape | records with item schema         | records **and** a shared `TabularEnvelope` for run-time columns |
| Package home  | left open                        | standalone `octools`, no OpsCogs dependencies                   |

- **`title` is an optional field.** MCP carries it and the mapping is
  lossless.
- **`func` is typed `Callable[..., Any]`, not
  `Callable[..., dict[str, Any]]`.** The result is still required to be a
  JSON object, but typing it as `Any` lets libraries return a pydantic
  `model_dump()` result without a cast and avoids a promise the type checker
  cannot verify.
- **Structural versus policy validation.** Construction raises
  `OCToolError` for anything that makes a descriptor unusable (bad name,
  non-object schema root, non-callable or asynchronous `func`, unknown
  literal). Policy (sentence count, strict-clean, escape reason, alias) is
  reported by `validate_tool` / `validate_provider` as `Finding` data, so a
  library sees every problem in one run.
- **`meta["schema_escape"]`** is the explicit record of a schema escape: the
  escape must be explicit, never accidental. `meta["alias_of"]` likewise
  names an alias's target.
- **`input_schema_for` closes only model objects.** It adds
  `additionalProperties: false` to objects that declare `properties`; a
  free-form `dict` field is left open so its meaning is not silently
  changed, and `strict_clean` reports it.
- **MCP `_meta` carries `com.opscogs.octools/spec_version`,** so a consumer
  can check the major without importing the library. The prefix carries the
  package label because MCP allows only one slash in a `_meta` key, so
  `com.opscogs/octools/...` would not conform; sibling OpsCogs packages use
  `com.opscogs.<package>/` to keep their keys apart.
- **`to_mcp_tool` does not emit `openWorldHint`.** The concept is on the
  scope fence below, and the converter follows the fence.
- **`pattern` is outside the strict subset.** The subset admits only
  keywords every runtime accepts, and `pattern` is not among them, so
  `strict_clean` flags it.
- **No descriptor depends on annotation keywords under a runtime's strict
  mode.** `strict_clean` reports every keyword outside the strict subset,
  and `to_anthropic_tool` strips `title` and `x-` keys, so whether a strict
  mode tolerates them never matters.
- **`ArtifactEnvelope.sensitivity`** is `Literal["inherits_input"]` only,
  the most conservative reading and the value an unknown one reads as. A
  second value is additive when it is less restrictive than
  `"inherits_input"`. An unknown `x-sensitivity` value reads as the most
  sensitive value. [OCTL-0006](./OCTL-0006-tolerant-readers.md) holds the
  rule.
- **`Finding` is defined apart from the descriptor,** so the schema checker
  does not import the descriptor.
- **`column_kinds` is a closed vocabulary** (`COLUMN_KINDS`: `text`,
  `number`, `integer`, `boolean`, `timestamp`, `ip`, `fqdn`, `mac`), the
  kinds a tabular UI needs for column alignment and chart axis choice, so a
  second reader never guesses. Each maps onto a JSON Schema type or format
  (`timestamp` is `string`/`date-time`, `ip` is `string`/`ipv4` or `ipv6`,
  `fqdn` is `string`/`hostname`, `mac` is `string`, the rest are the type of
  the same name). [OCTL-0005](./OCTL-0005-column-kinds-ip-block-big-integer.md)
  adds `ip_block` and `big_integer`.

### The 1.x scope fence

The descriptor does not carry the following. Each item is classified by how
it could arrive; the list changes only by a new decision record, never by a
quiet field:

- **Additive later**, as an optional field or a converter key: timeouts,
  cost and latency hints, `input_examples`, `strict` and `defer_loading`
  flags, `openWorldHint`, `icons`, translated descriptions.
- **Additive only as advisory markers**, with runtime policy authoritative
  as it is for the hints: approval class, redaction rules.
- **Additive only as a separate optional field**, beside a synchronous
  `func`: async variants, streaming and progress.
- **Needs a new major:** non-JSON result content.
- **Closed, not added:** per-tool `version`; a rename with a deprecated
  alias covers it.

Result paging is outside the fence: [OCTL-0002](./OCTL-0002-result-paging.md)
decides it.

### Consequences

- Good: a consumer validates and converts any library's tools with
  one package and no SDK dependency.
- Good: strict-clean schemas and two-to-four-sentence descriptions
  behave the same under every runtime's strict mode.
- Good: one closed `column_kinds` vocabulary and shared envelopes
  mean a second reader never guesses a result's shape.
- Bad: bounds outside the strict subset (`pattern`, for example) live
  in descriptions and Python validation rather than in the schema.
- Bad: every item on the scope fence waits for a decision record
  even when a single consumer needs it.

### Confirmation

Construction raises `OCToolError` on structural faults. `validate_tool` and
`validate_provider` return `Finding` data for policy faults, and
`strict_clean` reports schema keywords outside the strict subset. The
package's end-to-end example provider (a records tool, an artifact tool and a
deprecated alias) must validate with no findings and round-trip through both
converters.

## Pros and Cons of the Options

### A. MCP-vocabulary `OCTool` in a standalone package (chosen)

- Good: MCP is the most complete runtime shape and the others
  convert from it as plain dicts.
- Good: the package imports no OpsCogs library and no runtime SDK.
- Neutral: each runtime shape needs a converter.
- Bad: the package owns a descriptor format and its versioning.

### B. One runtime SDK's tool type

- Good: no conversion is needed for that runtime.
- Bad: every library then depends on that SDK.
- Bad: no SDK's type carries the records, tabular and artifact
  envelopes, the sensitivity hook or the deprecated-alias rule.

### C. Framework-native tool definitions

- Good: the framework already runs the tool.
- Bad: each framework ties every library to it, and a consumer on
  another framework cannot read the definitions.

### D. Records-only `AgentTool` in an existing library

- Good: it is the smallest shape that fits a single remote adopter.
- Bad: a platform name in `access` does not fit a second platform or
  a local surface.
- Bad: records alone cannot describe run-time tabular columns or an
  artifact written to a sink.
- Bad: housing it in an OpsCogs library makes every other library
  depend on that one.

## More Information

This decision ships in octools 0.1.0 with `SPEC_VERSION` `"0.1"`.
`SPEC_VERSION` major `1`, from `"1.0"` in octools 1.0.0, is the
compatibility contract in [OCTL-0006](./OCTL-0006-tolerant-readers.md).
Consumers check the major; a spec minor adds only what that contract
allows.

Related records: [OCTL-0002](./OCTL-0002-result-paging.md) decides result
paging (`next_cursor`, `total_count` on `RecordsEnvelope` and
`TabularEnvelope`; `ArtifactEnvelope` is unchanged).
[OCTL-0004](./OCTL-0004-merge-providers.md) adds `merge_providers`.
[OCTL-0005](./OCTL-0005-column-kinds-ip-block-big-integer.md) extends
`column_kinds`. [OCTL-0006](./OCTL-0006-tolerant-readers.md) decides
tolerant readers, vocabulary fallbacks and the compatibility contract.
