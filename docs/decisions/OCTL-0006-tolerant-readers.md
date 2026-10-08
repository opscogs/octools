---
status: accepted
version: 1.3.1
date: 2026-10-08
decision-makers: OpsCogs maintainers
---

# OCTL-0006 tolerant readers

## Context and Problem Statement

Every envelope model sets `extra="forbid"`, and every vocabulary
(`result_kind`, `access`, `column_kinds`, `column_scales`, `sensitivity`)
is a closed `Literal`. That is right for a producer: a misspelled key or
kind fails in its own tests. It is wrong for a reader. A tool result crosses a process boundary (an MCP
server built against one `octools`, an agent runtime built against another),
and a strict reader rejects the whole result whenever the producer's
`octools` is one minor release ahead with one optional field or one new
kind.

Strict readers force lockstep upgrades: every additive release obliges every
reader to raise its floor before any producer can use the addition. With
several OpsCogs libraries depending on `octools`, and runtimes consuming
tools from several of them, one library cannot upgrade until every library
whose output it reads has upgraded.

How does a reader parse an envelope it partly predates, what may a minor
release add, and how do consumers declare their `octools` dependency, so
that a newer producer never forces an older reader to upgrade and no two
OpsCogs libraries ever need upgrading together?

## Decision Drivers

- No lockstep upgrades across OpsCogs libraries: a newer producer never
  forces an older reader to upgrade.
- Producers keep their typo check: a misspelled key or vocabulary value
  fails in the producer's own tests.
- Published output schemas stay closed (`additionalProperties: false`), so
  an MCP client validating `structuredContent` still catches a stray key.
- Security-relevant values fail safe: an unknown marker reads as its most
  conservative value, never as a less restrictive one.
- Tolerance covers additions, never corruption: every other check still
  runs on read.
- One model per envelope, not two kept in sync by hand.

## Considered Options

- **A.** Strict producers with a tolerant `read_envelope` entry point
- **B.** `extra="ignore"` on every envelope
- **C.** `extra="allow"` on every envelope
- **D.** Separate reader models
- **E.** Readers parse plain dicts
- **F.** Lockstep releases coordinated across OpsCogs libraries

## Decision Outcome

Chosen option: **A, strict producers with a tolerant `read_envelope` entry
point**, because it is the only option that makes readers tolerant while
producers keep their typo check and the published schemas stay closed, with
one model per envelope and every check except the two that block
compatibility still applied. Minor releases may only add things a tolerant
reader can safely ignore.

### Producers

Constructing an envelope, or calling `model_validate` on one, is strict:
unknown keys and unknown vocabulary values raise. The published output
schema is closed (`additionalProperties: false`), because it describes what
this producer emits, which is exact. A producer's typo fails in the
producer's own tests.

A derived (computed) field is dumped but not stored. Strict input accepts
its key, so a dump round-trips through `model_validate`, and checks the
value against the fields it derives from: a contradiction is a
`ValueError`. `resumable` on the list envelopes
([OCTL-0002](./OCTL-0002-result-paging.md)) is such a field.

A field added in a minor is left out of the dump when it carries nothing
new: `None`, an empty list, or a derived value a reader infers from the
key's absence. A result that does not use the field therefore dumps the
older shape and passes an older consumer's strict input schema, so a newer
producer never forces a consumer to upgrade just to accept its output. The
output schemas (`records_schema`, `tabular_schema`) and the input-mode
schema `input_schema_for` builds for a model nesting an envelope declare
such a field as an optional property, never in `required`, so a result
passed unchanged into another tool's envelope-typed argument validates.
`resumable` is dumped only when `truncated` is true, and absent reads as
false ([OCTL-0002](./OCTL-0002-result-paging.md)).

Every envelope carries `warnings`, a list of non-fatal problems the caller
should relay, one per entry. A multi-source read uses it to report a
partial failure (one source missing a table) beside the result it did
return, rather than failing the call. `RecordsEnvelope` and
`TabularEnvelope` leave it out of the dump when empty, under the rule
above. `ArtifactEnvelope` always dumps it, as it does in 1.0. A reader
treats an absent `warnings` as empty.

### Readers

```python
def read_envelope(model: type[E], data: Mapping[str, object] | str | bytes) -> E: ...
```

A function exported from the package root, for any code parsing an envelope
it did not construct. `E` is `RecordsEnvelope` (any parametrization),
`TabularEnvelope` or `ArtifactEnvelope`; a `str` or `bytes` argument is
parsed as JSON. It validates the same model with a validation context that
relaxes exactly two things:

- **Unknown keys are dropped**, at the envelope level and in nested
  `octools` models (`ArtifactRef`). They are not reported: a reader cannot
  act on a field it does not know, and a field a minor release may add is by
  definition one a reader may ignore (below). Keys inside `records` are not
  touched; the record model `T` belongs to the consumer, and its own config
  decides.
- **Unknown vocabulary values degrade to a declared fallback**, per
  vocabulary (table below).

Everything else is still checked: types, required fields, row widths, the
paging rules, and a derived field against the fields it derives from (a
contradiction is corrupt data, not version skew). Tolerance covers
additions, never corruption. One cross-field
check follows the fallback: a non-null `column_scales` entry on a column
whose kind is not numeric, or whose kind degraded to `text`, reads as `None`
rather than failing. Strict validation still rejects it.

### Fallbacks

Every closed vocabulary declares the value an unknown value reads as:

| Vocabulary                     | Unknown value reads as              | Why                                                                                                                            |
| ------------------------------ | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `result_kind`                  | `"records"`                         | a future kind degrades to the records shape, which tabular tools use                                                           |
| `access`                       | `"remote"`                          | the safer policy assumption                                                                                                    |
| `column_kinds`                 | `"text"`                            | every cell is at least displayable text                                                                                        |
| `column_scales`                | `None`                              | the renderer's data rule always applies                                                                                        |
| `sensitivity`                  | `"inherits_input"`                  | the most conservative reading; only values less restrictive than it may be added, so degrading an unknown value is always safe |
| `x-sensitivity` (a convention) | the most sensitive value (`secret`) | fail safe                                                                                                                      |

Each fallback is a constant beside its values: `RESULT_KIND_FALLBACK`,
`ACCESS_FALLBACK`, `COLUMN_KIND_FALLBACK`, `COLUMN_SCALE_FALLBACK` (`None`)
and `SENSITIVITY_FALLBACK`. `read_envelope` applies the envelope
vocabularies (`column_kinds`, `column_scales`, `sensitivity`). `octools` does
not parse descriptors from the wire, so the `result_kind` and `access`
fallbacks are the rule for any reader of an MCP tool's `_meta` and for any
future descriptor reader, and `x-sensitivity` is the rule for a runtime
reading an input schema's extension keys.

A fallback is always the most conservative reading of its vocabulary, so a
reader that degrades a value it does not know never treats data as less
sensitive or a tool as more contained than it is. A new vocabulary cannot
ship without a fallback.

`model_validate` is not tolerant by default, because that would take
strictness away from producers. One model, two entry points.

### What a minor release may add

The compatibility contract for every release within a major:

- **May add**, in a minor: an optional envelope or descriptor field whose
  absence means exactly what it meant before; a vocabulary value whose
  fallback reading is safe (a `sensitivity` value only when it is less
  restrictive than `"inherits_input"`); a function, a helper or an export.
- **Validator rules.** A new `validate_tool`, `validate_provider` or
  `strict_clean` rule, or a tighter existing one (a smaller
  `STRICT_KEYWORDS`, a lower `MAX_SENTENCES`, a stricter `NAME_RE`), ships
  opt-in within a major, the way `validate_tabular` does; loosening a rule
  is allowed in a minor. Consumers assert `validate_provider(p) == []`, so a
  default-on new rule would break their CI.
- **Converter output.** `to_mcp_tool` and `to_anthropic_tool` output may
  gain keys in a minor (`openWorldHint`, `icons`, `input_examples`).
  Consumers assert on the keys they need, not whole-dict equality. An
  existing key never changes meaning or disappears within a major.
- **Envelope dumps and schemas.** An envelope's output schema
  (`records_schema`, `tabular_schema`) may gain optional properties in a
  minor, and a dump may gain a key only when the new field carries
  something; a field that carries nothing new is left out of the dump, as
  above. Consumers assert on the keys they need, not whole-dump or
  whole-schema equality. A dump rule shapes only the field `octools`
  defines: a consumer subclass that defines the same field itself keeps
  the dump and schema it had before the rule, as `resumable` does
  ([OCTL-0002](./OCTL-0002-result-paging.md)).
- **`Finding`** may gain optional fields defaulting to `None` in a minor.
- **`ToolProvider`** is frozen within a major: no new required members.
- **Envelope subclasses.** Consumers may subclass envelopes and
  `ArtifactRef`. The field names `role` and `source` are reserved for
  `octools`, as is every field an envelope already carries, `warnings`
  among them. `ArtifactRef` defines `role` as optional free text naming
  what the artifact is to the run, such as `csv`, `plan` or `summary`,
  left out of the dump when unset; it is not a closed vocabulary, so it
  has no fallback, and an `ArtifactRef` subclass uses it rather than a
  field of its own. A consumer's own
  subclass fields use a consumer prefix
  (`<pkg>_...`) unless the field is being proposed upstream, and a subclass
  field that collides with a later `octools` field is the consumer's to
  rename.
- **The public API** of every 1.x release is exactly the package root's
  `__all__`. A name outside it carries no compatibility promise.
- **Must not**, before a new major: remove or rename a field, value or
  export; make an optional field required; change what an existing field or
  value means; add a field a reader must understand to read the rest
  correctly (a flag meaning "rows are deltas" would silently corrupt a
  tolerant reader); add a vocabulary value whose fallback reading is less
  safe than the value (a `sensitivity` value more restrictive than
  `"inherits_input"`); tighten a check on parse (a new opt-in check such as
  `validate_tabular` is fine); turn on a new or tighter validator rule by
  default; change or remove a converter output key; add a required member to
  `ToolProvider`.

The test for any addition: a reader that drops it, or reads it as its
fallback, still reads the rest of the envelope correctly. An addition that
fails the test needs a new major.

`SPEC_VERSION` major `1` marks this contract, starting at `"1.0"` in
octools 1.0.0: a spec minor is additive and a spec major is the "must not"
list. A reader checks the major only. The spec version and the package
version are independent: a release that adds a helper leaves
`SPEC_VERSION` alone, and a release that adds an envelope or descriptor
field raises its minor. A consumer test that pins the exact value updates
with each spec minor; one that checks the major does not.

### Consumers' dependency ranges

Every OpsCogs library declares `octools` the same way:

```toml
dependencies = ["octools >= 1.0, < 2"]
```

- **The floor** is the oldest release that has every `octools` name the
  library uses. It rises when the library starts using a new name, never
  just because a release came out.
- **The ceiling** is the next major and nothing tighter. No `==`, no `~=`,
  and no caret on a `0.x` version (`^0.3` means `< 0.4`), which
  reintroduces lockstep.
- Because every minor is additive under the contract above, the newest
  `octools` satisfies every library's floor at once, so a resolver can
  always find one version for the whole environment. Two libraries can only
  conflict across a major.
- `octools` holds itself to the same rule for its own dependency:
  `pydantic >= 2.12, < 3`, a ceiling at the next pydantic major and nothing
  tighter.

### Consequences

- Good: a reader on 1.0.0 or later reads any newer producer within
  the major without upgrading.
- Good: producers keep their typo check and the published schemas
  stay closed.
- Good: the newest `octools` satisfies every library's floor, so a
  resolver always finds one version for the whole environment.
- Good: an unknown `sensitivity` marker degrades to the most
  conservative value, so a tolerant reader never under-protects data.
- Good: a minor upgrade never breaks a consumer's
  `validate_provider(p) == []` assertion or its converter-key assertions.
- Good: a result that does not use a field added in a minor passes
  the strict input schema of a consumer built against the older minor.
- Good: a list result can report a partial failure in `warnings`
  instead of failing the call.
- Bad: any code that parses envelopes from another process needs
  `octools >= 1.0`, the first release with `read_envelope`, and must call
  it instead of `model_validate`.
- Bad: every closed vocabulary carries a fallback, and `sensitivity`
  can only gain values less restrictive than `"inherits_input"` within a
  major.
- Bad: a new or tighter validator rule stays opt-in until the next
  major.
- Bad: consumer subclass fields avoid the reserved names and carry a
  consumer prefix.
- Bad: a consumer that asserts on a whole envelope dump or schema
  updates its expectation when a minor adds a key.
- Bad: a field a reader must understand to read the rest correctly
  can only arrive in a new major.

### Confirmation

- A "future envelope" test fixture carries an extra key at each level, an
  unknown `column_kinds` value, an unknown `column_scales` value, an unknown
  `sensitivity` value, and a scale on a column whose kind is non-numeric or
  degraded to `text`, and asserts `read_envelope` reads it (the scale as
  `None`, the sensitivity as `"inherits_input"`) and strict validation
  rejects it.
- A dump carrying a derived field round-trips through strict
  `model_validate`, and a contradicting value is rejected by both
  `model_validate` and `read_envelope`.
- For both list envelopes, truncated and untruncated, a dump's keys are
  declared properties of the envelope-typed input schema and cover its
  `required` list; `resumable` and an empty `warnings` are absent from an
  untruncated, warning-free dump.
- A vocabulary test enumerates every closed vocabulary and checks that each
  has a fallback.
- The contract is written into the published versioning section, so
  reviewers of a release can check an addition against it.

## Pros and Cons of the Options

### A. Strict producers with a tolerant `read_envelope` entry point (chosen)

- Good: readers become tolerant of additions without producers
  losing strictness.
- Good: the published schemas stay closed.
- Good: one model serves both entry points, so nothing drifts.
- Good: every check except unknown keys and unknown vocabulary
  values, and the scale check that follows a degraded kind, still runs on
  read.
- Bad: readers must choose the right entry point: `model_validate`
  on a foreign envelope is still strict.

### B. `extra="ignore"` on every envelope

- Good: readers become tolerant with no new API.
- Bad: producers lose their typo check.
- Bad: the published schemas stop saying
  `additionalProperties: false`, so an MCP client that validates
  `structuredContent` against the output schema, as the MCP specification
  recommends, no longer catches a stray key either.

### C. `extra="allow"` on every envelope

- Good: readers become tolerant and nothing is lost.
- Bad: unknown keys stay on the model, where they become an
  unofficial API that nothing documents or validates.
- Bad: producers lose their typo check.

### D. Separate reader models

- Good: producer models stay strict and reader models can be
  lenient.
- Bad: every envelope exists twice, kept in sync by hand, and the
  two drift.
- Bad: it doubles the public surface.

### E. Readers parse plain dicts

- Good: a reader never rejects a newer envelope.
- Bad: it throws away every check, not just the two that block
  compatibility.

### F. Lockstep releases coordinated across OpsCogs libraries

- Good: it needs no change to `octools`.
- Bad: one library cannot upgrade until every library whose output
  it reads has upgraded, which is the coordination this record removes.

## More Information

Additive: one function, the fallback constants, and the compatibility
contract. It ships in octools 1.0.0 beside
[OCTL-0005](./OCTL-0005-column-kinds-ip-block-big-integer.md), with
`SPEC_VERSION` `"1.0"`. Strict acceptance of derived fields, the envelope
dump and schema rule, `warnings` on every envelope, the reserved names
`role` and `source`, and `ArtifactRef.role` ship in octools 1.1.0 with
`SPEC_VERSION` `"1.1"`, beside `stop_reason` and `resumable`
([OCTL-0002](./OCTL-0002-result-paging.md)).

The published docs carry the contract (descriptor versioning section), the
per-vocabulary fallback table, the reserved subclass field names, the
`read_envelope` guidance (envelopes section), and the dependency rule; the
upstream-requests page asks consumers to state their declared range.

octools 1.0.0 is the first release under this contract. Semantic
versioning lets `0.x` minors break, so dependency tooling treats `0.3` to
`0.4` as a breaking step; from 1.0.0 the tools and the contract agree, and
the surface of 1.0.0 is the baseline every 1.x release keeps.
