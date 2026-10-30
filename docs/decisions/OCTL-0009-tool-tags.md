---
status: accepted
version: 1.0.0
date: 2026-10-30
decision-makers: OpsCogs maintainers
---

# OCTL-0009 tool tags

## Context and Problem Statement

A host that merges several providers loads some tools by default and others
only on request. The descriptor has no field for that distinction, so each
provider would carry its own `meta` key, a host would have to know those keys,
and the validator could not check them. How does a provider say what a tool is
in a way every host reads the same?

## Decision Drivers

- One field every provider fills the same way, surviving `merge_providers`.
- A host selects tools without knowing any consumer's `meta` key.
- The 1.x contract: an optional field, a declared fallback, an opt-in check.
- The Anthropic tool shape rejects keys it does not define.

## Considered Options

- **A.** `tags`, a tuple of strings, with well-known values.
- **B.** `tool_set`, one value from a closed vocabulary.
- **C.** A documented `meta["tool_set"]` convention, with no field.

## Decision Outcome

Chosen option: **A, `tags`**, because a tool may need more than one label over
time, and a reader that ignores what it does not know stays safe.

- `OCTool.tags` is an optional tuple of non-empty strings, empty by default.
- `TOOL_TAGS` lists the well-known values, `recommended` (load by default) and
  `advanced` (load on request). `TOOL_TAG_FALLBACK` is `None`: a reader ignores
  a tag it does not know, so a tool carrying only unknown tags is never loaded
  by default.
- `select_tools(provider, tags=...)` returns a provider listing the tools that
  carry any given tag, in order. It returns a provider, so listings, converters
  and validators compose with it, and it works on a merged provider.
- `to_mcp_tool` publishes tags as `_meta["com.opscogs.octools/tags"]` when any
  are set. `to_anthropic_tool` does not, because that shape has no slot for
  them; a host filters with `select_tools` first, then converts.
- `validate_tags` reports each tag outside `TOOL_TAGS` as `unknown_tag`. It is
  opt-in under [OCTL-0006](./OCTL-0006-tolerant-readers.md), and
  `validate_provider` does not report tags.
- Tags describe a tool; they do not instruct a runtime. `defer_loading` stays on
  the scope fence in [OCTL-0001](./OCTL-0001-descriptor-origin.md), and what a
  host loads remains its own choice.

### Consequences

- Good: a host loads a merged provider's recommended tools with one call.
- Good: `ToolSummary` rows carry `tags` when set, so listings stay unchanged
  for an untagged tool.
- Bad: a tool may carry both `recommended` and `advanced`; `select_tools` then
  matches it on either.
- Bad: a provider using a `meta` key moves to `tags` to be selectable.

### Confirmation

Spec fixtures under `select_tools`, `validate_tags`, `OCTool`, `to_mcp_tool`,
`to_anthropic_tool` and `summarize_tool` pass in both implementations.

## Pros and Cons of the Options

### A. `tags` (chosen)

- Good: open to new well-known values in a minor, each with the same fallback.
- Bad: nothing at construction limits a tool to one of the two values.

### B. `tool_set`

- Good: exactly one value per tool.
- Bad: a second dimension of grouping would need another field.

### C. A `meta` convention

- Good: no descriptor change.
- Bad: no validation, and every host depends on an agreed private key.

## More Information

Ships in octools 1.3.0 with `SPEC_VERSION` `"1.2"`.
