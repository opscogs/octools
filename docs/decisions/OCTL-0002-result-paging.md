---
status: accepted
version: 1.4.1
date: 2026-10-08
decision-makers: OpsCogs maintainers
---

# OCTL-0002 result paging

## Context and Problem Statement

A list-shaped tool result is often too large to return in one call.
`truncated` on `RecordsEnvelope` and `TabularEnvelope` says that more
exists, but not how to continue, how much there is, or why the read
stopped. A caller paging through a large result needs a way to ask for the
next page and to know when a truncated read cannot continue, and a
consumer showing "N of M" needs the full size when the source knows it.

Result paging is part of the descriptor format; it is not on the 1.x scope
fence in [OCTL-0001](./OCTL-0001-descriptor-origin.md).

## Decision Drivers

- Match the paging vocabulary of the protocols tools are published to.
- Keep what a model has to do to page as simple as possible.
- Never require a number the backend cannot produce cheaply or exactly.
- Stay correct on data that is being appended to while it is paged.
- Carry any exact total a source can report, including one past 2^53 that
  a JSON number cannot hold exactly.
- Say plainly whether a truncated read can continue, and why it stopped
  short, without a reader having to understand the reason to page
  correctly.

## Considered Options

- **A.** An opaque cursor, with an optional exact total
- **B.** Offset and total beside the existing `count`

For checking that a tool publishing `next_cursor` accepts it back:

- **C.** The input convention, confirmed by the producer's own paging test
- **D.** A validator rule tying `next_cursor` in the output schema to a
  `cursor` input
- **E.** A descriptor flag declaring that a tool pages, with a validator rule
  keyed on it

For how `resumable` appears in a dump:

- **F.** Dump `resumable` only when `truncated` is true, and declare it
  optional in every schema
- **G.** Always dump `resumable`, and declare it only in the input-mode
  schema

## Decision Outcome

Chosen option: **A, an opaque cursor, with an optional exact total**, because
it is the only paging vocabulary MCP defines, a model only has to echo a
token, and no backend is forced to compute a total. `total_count` is an
integer or a decimal string, the rule `big_integer` uses
([OCTL-0005](./OCTL-0005-column-kinds-ip-block-big-integer.md)), so a total
past 2^53 stays exact.

`RecordsEnvelope` and `TabularEnvelope` carry three optional fields, each
defaulting to `None`, and one computed field:

| Field         | Type                 | Meaning                                                                                                                                                                                                                          |
| ------------- | -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `total_count` | `int \| str \| None` | Exact size of the full result, given only when the source knows it exactly; omitted when unknown or approximate. A JSON integer up to 2^53 - 1, a non-negative decimal string (`^(0\|[1-9][0-9]*)$`) above it.                   |
| `next_cursor` | `str \| None`        | Opaque token for the next page, present only when `truncated` is true; the caller echoes it back unchanged.                                                                                                                      |
| `stop_reason` | `str \| None`        | Why the read stopped early, present only when `truncated` is true; omitted when the read ended naturally or the caller's `limit` simply cut it. A free string; the well-known values include those below.                        |
| `resumable`   | `bool` (computed)    | `next_cursor is not None`, dumped only when `truncated` is true; absent reads as false. True: following `next_cursor` reads more. False: this read is over whatever `truncated` says; do not call again with the same arguments. |

Validation, in the models:

- `next_cursor` without `truncated=True` is a `ValueError`, and so is
  `stop_reason` without `truncated=True`.
- `total_count` whose numeric value is below `count` (records) or
  `row_count` (tabular) is a `ValueError`, whichever form it takes. A
  string that is not a non-negative decimal integer is a `ValueError`. A
  producer may send a string for any value; readers compare numerically.
- `truncated=True` with no cursor is allowed: a hard cap with no
  continuation is still an honest result.
- `count` must equal `len(records)` and `row_count` must equal
  `len(rows)`, so `total_count` is compared with a verified number, not
  a caller-supplied one.
- `total_count`, `next_cursor` and `stop_reason` are left out of
  serialized output when `None` (pydantic `exclude_if` on the field), so
  "omitted when unknown" is a property of the envelope and adopters never
  reach for `exclude_none`, which would also strip optional record fields.
- `resumable` is a pydantic `computed_field`: it is never stored, and it is
  dumped only when `truncated` is true, as `true` or `false`. An untruncated
  result leaves it out, so it dumps exactly the 1.0 shape and passes the
  strict input schema of a consumer built against octools 1.0. A reader
  treats an absent `resumable` as false. Strict input accepts a `resumable` key so a dump round-trips
  through `model_validate` under `extra="forbid"`; the value must be a bool
  equal to `next_cursor is not None`, and a contradiction is a `ValueError`.
  `read_envelope` applies the same check, because a contradiction is
  corrupt data, not version skew
  ([OCTL-0006](./OCTL-0006-tolerant-readers.md)).
- `records_schema(item)` and `tabular_schema()` describe the dumped shape:
  `resumable` is an optional boolean property, not in `required`, and
  `stop_reason` an optional string property.
- `input_schema_for` on a model that nests an envelope by `$ref` declares
  `resumable` as an optional boolean property too, so a result passed
  unchanged into another tool's envelope-typed argument passes that
  schema's `additionalProperties: false`.
- These dump and schema rules apply to the `resumable` that
  `RecordsEnvelope` and `TabularEnvelope` define. A subclass that defines
  its own `resumable` computed field keeps pydantic's output handling of
  it: its dump carries `resumable` always and its output schema lists it
  as required. That is the output shape such a subclass had under octools
  1.0, so its output does not change when a consumer upgrades within 1.x.
  Its input-mode schema declares `resumable` as an optional boolean, so its
  dump passes an envelope-typed closed input schema too. Strict and tolerant input still accept and
  check a `resumable` key on every subclass.

The dump rule is chosen as **F**: a field added in a minor is left out of
the dump when it carries nothing new, the general rule in
[OCTL-0006](./OCTL-0006-tolerant-readers.md). `resumable` carries nothing
on an untruncated read, which is always over.

`stop_reason` well-known values include the following, documented and not
enforced:

| Value            | Meaning                                                                                                                                          |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `run_deadline`   | the read ran out of time                                                                                                                         |
| `page_count`     | the read hit its limit on backend pages                                                                                                          |
| `record_limit`   | the read stopped at a record or row cap; with no `next_cursor` when the producer cannot resume past it, such as a server-side row cap on a query |
| `interrupted`    | the read was cancelled                                                                                                                           |
| `cursor_stalled` | the backend returned a cursor that made no progress, so the read is over                                                                         |

`stop_reason` is a free string, not a closed vocabulary. Nothing in paging
depends on it: `resumable` and `next_cursor` say whether and how to
continue, so a reader that does not know a reason loses only the
explanation and needs no fallback. A producer can report a new reason
without an octools release.

`ArtifactEnvelope` does not page. There is no `offset` field.

Both list envelopes also carry `warnings`, a list of non-fatal problems the
caller should relay, left out of the dump when empty, so a multi-source
read can report a partial failure beside the rows it did return. The field
and the dump rule are in [OCTL-0006](./OCTL-0006-tolerant-readers.md).

The input side is a convention, chosen as **C**, not a validator rule. A
tool that can return a `next_cursor` takes:

- `cursor`: an optional argument typed `string` or `null`, absent on the
  first page, described as the `next_cursor` from a previous page. The tool
  treats it as its own opaque encoding, validates it like any other
  argument, and raises a `ValueError` naming `cursor` when it is malformed.
- `limit`: an integer page size, with its bounds in the description.

A tool whose result is never cut short with a continuation takes no
`cursor`, even though its envelope schema carries `next_cursor`. Whether a
cursor survives across processes (a stateless encoding) is the tool's
choice.

The producer's own test confirms the convention: call the tool with a
`limit` that cuts the list, pass the returned `next_cursor` back as
`cursor`, and check that the next page follows and the last page has no
`next_cursor`. The validator has no paging rule, because every records and
tabular schema carries `next_cursor` whether or not the tool pages, so
the output schema cannot tell a paged tool from an unpaged one.

### Consequences

- Good: the field matches MCP's `nextCursor`, so a tool's paging
  maps directly onto the protocol.
- Good: a model pages by echoing a token, with no arithmetic.
- Good: `resumable` tells a model in one boolean whether to keep
  paging, and `stop_reason` tells a person why a read stopped short.
- Good: a cursor can encode a stable position in data that is
  being appended to (logs, events).
- Good: a total of any size is exact end to end, and a small one
  needs no parsing.
- Bad: `total_count` has two JSON forms, so a reader converts a
  string to an integer before comparing or doing arithmetic.
- Bad: a caller cannot jump to an arbitrary page; it must walk
  the cursors.
- Bad: each tool owns its cursor encoding, and `validate_provider`
  does not check that a tool publishing `next_cursor` also accepts
  `cursor`; the producer's paging test is that check.
- Good: an untruncated result dumps exactly the 1.0 shape, so a
  consumer built against octools 1.0 accepts it in an envelope-typed
  argument, and any result passes a 1.1 input schema unchanged.
- Bad: `resumable` is absent from most dumps, so a reader that reads the
  dump directly treats an absent key as false.
- Bad: both envelope schemas carry `resumable`, so a consumer that asserts
  on a whole schema updates its expectation; consumers assert on the keys
  they need.

### Confirmation

The envelope models enforce the validation rules above on construction,
and on strict and tolerant input a `resumable` that contradicts
`next_cursor` is rejected. A dump round-trips through `model_validate`.
For both envelopes, truncated and untruncated, a test checks that `resumable`
is dumped exactly when `truncated` is true and that the dump's keys fit the
envelope-typed input schema: every key a declared property and every
required property present. A second test checks that a subclass defining
its own `resumable` dumps it on every read, lists it as required in its
output schema, fits a closed envelope-typed input schema, and still
round-trips.
Output schemas are not held to the strict subset. The example provider's `echo_records` tool follows the
input convention and its test walks the cursors to the last page: it
accepts `cursor`, returns `total_count`, and sets `next_cursor` only when
`limit` cut the list short. `block_sizes` returns a tabular envelope and,
never continuing, takes no `cursor`.

## Pros and Cons of the Options

### A. An opaque cursor, with an optional exact total (chosen)

- Good: MCP 2025-11-25 and 2026-07-28 page their list operations
  with an opaque `nextCursor` and have no offset or total; Anthropic and OpenAI tool
  schemas say nothing about result paging.
- Good: `truncated` already says "more exists", and the cursor is
  the missing "how to continue".
- Good: an optional exact total serves a "showing N of M" line
  without obliging any backend to produce one.
- Bad: pages are reachable only in order.

### B. Offset and total beside `count`

- Good: it is the shape a classic offset-paged API returns.
- Bad: a model has to do arithmetic and reason about a total,
  which is more error-prone than echoing a token.
- Bad: totals are expensive or unavailable on the backends these
  tools front: object-store listings have no total, search engines return
  approximate totals, SQL needs a second `COUNT`. Requiring one invites
  tools to guess or to pay for it on every call.
- Bad: offsets are unstable on data that is being appended to.
- Bad: no source protocol defines an offset for results.

### C. The input convention, confirmed by the producer's paging test (chosen)

- Good: it tests the behaviour that matters, a `next_cursor` that
  actually reads the next page, which no schema check can see.
- Good: the paging adopters already follow it uniformly: each paged tool
  takes an optional `cursor: str | None` with the same description.
- Good: no descriptor field and no new API.
- Bad: a producer that skips the test learns of a missing `cursor` only
  when a caller tries to continue.

### D. A validator rule tying `next_cursor` to a `cursor` input

- Good: it runs with the conformance check every producer already uses.
- Bad: every records and tabular schema carries `next_cursor`, so the
  rule fires on every list tool that never pages, `block_sizes` in the
  example provider among them. Opt-in or not, a rule that is wrong for a
  whole class of correct tools is noise.

### E. A descriptor flag declaring that a tool pages

- Good: a rule keyed on the flag would have no false positives.
- Bad: it is a new descriptor field, which the 1.x scope fence in
  [OCTL-0001](./OCTL-0001-descriptor-origin.md) admits only by a new
  decision, to state what the `cursor` argument already states.
- Bad: a flag can be wrong in the same way a missing `cursor` can,
  so the producer test is still needed.

### F. Dump `resumable` only when truncated, optional in every schema (chosen)

- Good: an untruncated result is byte-for-byte the 1.0 shape, so a
  consumer built against octools 1.0 accepts it under a strict input
  schema, and no reader has to upgrade in step with a producer.
- Good: a same-version pass-through validates, because the input-mode
  schema declares `resumable`.
- Good: an untruncated read loses nothing: it is always over, which is what
  an absent `resumable` reads as.
- Bad: the key is sometimes present, so a reader checks for it rather than
  indexing it.

### G. Always dump `resumable`, declared only in the input-mode schema

- Good: every dump has the same keys.
- Good: it fixes a same-version pass-through into an envelope-typed
  argument.
- Bad: every result from a 1.1 producer, truncated or not, carries a key a
  1.0-built consumer's strict input schema does not declare, so that
  consumer rejects all of them. That is the lockstep upgrade
  [OCTL-0006](./OCTL-0006-tolerant-readers.md) exists to prevent.

## More Information

Correspondence with the sources:

| Concept   | Source                           | Here                                                                           |
| --------- | -------------------------------- | ------------------------------------------------------------------------------ |
| Next page | MCP `nextCursor`                 | `next_cursor`, snake_case per the descriptor's MCP-vocabulary rule             |
| Total     | none in MCP                      | optional exact `total_count`, because a consumer wants a "showing N of M" line |
| Offset    | none in MCP, Anthropic or OpenAI | not provided                                                                   |

The fields ship in octools 0.1.0 and are part of the first released
format. The string form of `total_count` ships in octools 1.0.0
(`SPEC_VERSION` `"1.0"`), so a Python reader needs `octools >= 1.0` to read
a string total; the type holds for the whole 1.x series. `stop_reason` and
`resumable` ship in octools 1.1.0 with `SPEC_VERSION` `"1.1"`. Both pass the minor-release test in
[OCTL-0006](./OCTL-0006-tolerant-readers.md): a reader that drops either
still pages correctly from `truncated` and `next_cursor`. The `resumable`
dump rule, its optional declaration in the output and input-mode schemas,
and `warnings` on both list envelopes ship in the same release. A consumer subclass that defines its own
`stop_reason` can remove it and inherit this one; a subclass that keeps
its own `resumable` keeps its 1.0 dump and schema.
The published descriptor page documents the paging fields and the input
convention in the Paging subsection of its Result envelopes section.
