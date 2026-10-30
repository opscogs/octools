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
- **D.** `tags`, plus a toolset type naming a collection of tags.

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
- Nesting two `select_tools` calls requires a tag from each set. There is no
  exclusion form; one arrives only on a consumer's request.
- `to_mcp_tool` publishes tags as `_meta["com.opscogs.octools/tags"]` when any
  are set. `to_anthropic_tool` does not, because that shape has no slot for
  them; a host filters with `select_tools` first, then converts.
- A provider may use its own domain tags. `validate_tags(provider, allowed=...)`
  reports each tag outside `TOOL_TAGS` and `allowed` as `unknown_tag`, so no
  naming convention is needed and the caller states what it accepts. It is
  opt-in under [OCTL-0006](./OCTL-0006-tolerant-readers.md), and
  `validate_provider` does not report tags.
- Tags describe a tool; they do not instruct a runtime. `defer_loading` stays on
  the scope fence in [OCTL-0001](./OCTL-0001-descriptor-origin.md), and what a
  host loads remains its own choice.
- octools defines no toolset type. A named collection of tags is a host's
  loading choice, so a host keeps it as a set and passes it to `select_tools`.
  A shared type needs its own decision record, and is justified when two hosts
  need the same named set across repositories, or when users pick sets by name
  in a listing. Hosts or a shared package own those definitions, not providers.

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

### D. A toolset type over `tags`

- Good: a curated selection has one shared, discoverable name.
- Bad: a tag-based set is open, so any new tool carrying one of its tags joins
  it; a fixed selection needs tool names, which `select_tools` does not take.
- Bad: providers declaring toolset types would need a `merge_providers` rule for two
  definitions of one name, and `ToolProvider` is part of the 1.x contract.

## More Information

Ships in octools 1.3.0 with `SPEC_VERSION` `"1.2"`.
