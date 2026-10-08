---
status: accepted
version: 1.1.1
date: 2026-10-08
decision-makers: OpsCogs maintainers
---

# OCTL-0004 merging providers

## Context and Problem Statement

`validate_provider` answers a question about one listing: are these names
unique, is this order stable, is every descriptor conformant. A runtime does
not register one listing. It registers one library's tools beside another's,
and the interesting failure - two libraries that give a tool the same name -
exists only in the union. Without a union to validate, the `duplicate_name`
rule fires only on a listing where a collision is impossible.

`NAME_RE` is flat and has no namespace, so the collision is a real
possibility rather than a theoretical one, and the consumer merging the
listings is the only party who can see it.

## Decision Drivers

- A name collision between providers must reach `validate_provider` as a
  `duplicate_name` finding, never be hidden.
- The merged listing must stay deterministic, so `unstable_order` keeps its
  meaning.
- No change to the descriptor format or `SPEC_VERSION`.
- `octools` describes and validates tools; it does not run them.

## Considered Options

- **A.** `merge_providers`: concatenate the members' listings in argument
  order.
- **B.** A merge that deduplicates by name.
- **C.** A registry lookup, `get_tool(name)`.
- **D.** A dispatcher that calls a tool by name.

For telling which member listed a tool a finding names:

- **E.** Findings name the tool only; a consumer validates each member
  separately beside the merge.
- **F.** Record member provenance on `Finding` now.

## Decision Outcome

Chosen option: **A, `merge_providers` concatenating the members' listings
in argument order**, because it puts a collision in front of the validator and
leaves the decision with the consumer, who alone can make it.

```python
def merge_providers(*providers: ToolProvider) -> ToolProvider: ...
```

Returns a provider whose `all_tools()` is the concatenation of its members'
listings, in argument order. It is core surface because it takes any
`ToolProvider`: a module, an object, or another merge.

- **Nothing is deduplicated.** A name two providers share stays listed twice,
  so `validate_provider` reports `duplicate_name` and the consumer decides.
- **Order is argument order**, so the merged listing is deterministic as long
  as its members are, and `unstable_order` still fires when a member is not.
- **Merging nothing lists nothing.** `merge_providers()` is a legal empty
  provider rather than an error; it is the identity a fold needs.
- The result is a frozen dataclass holding the members. It carries no state
  and adds no descriptor field, so `SPEC_VERSION` is untouched.

Findings on a merge name the tool only, chosen as **E**: a merge carries no
member provenance in 1.x core. A consumer that needs to know which member
listed a tool runs `validate_provider` on each member as well as on the
merge. A finding the members also report belongs to the member that reports
it; a finding only the merge reports, such as a `duplicate_name` across
members, names a tool the consumer looks up in the members' listings. When a
consumer asks for provenance on the merged findings, it arrives as an
optional `Finding` field defaulting to `None` in a minor release, which
[OCTL-0006](./OCTL-0006-tolerant-readers.md) allows.

### Consequences

- Good: a consumer validates exactly the listing its runtime
  registers, collisions included.
- Good: merges nest and an empty merge is legal, so a consumer can
  fold any number of sources.
- Bad: merging is shallow: a finding names only the tool, not which
  member listed it, so a consumer that needs provenance validates each
  member separately as well as the merge.

### Confirmation

`validate_provider` on a merge of two providers that share a name reports
`duplicate_name`; a merge of deterministic members raises no
`unstable_order`; `merge_providers()` lists no tools.

## Pros and Cons of the Options

### A. `merge_providers` concatenating in argument order (chosen)

- Good: a collision surfaces as a `duplicate_name` finding.
- Good: it adds one function and no descriptor field.
- Neutral: the consumer resolves a collision itself.

### B. A merge that deduplicates by name

- Good: the merged listing always has unique names.
- Bad: silently dropping one of two same-named tools is exactly the
  failure the validator exists to catch; a merge helper that hid it would be
  worse than no helper.

### C. A registry lookup, `get_tool(name)`

- Good: a caller can fetch a tool by a string name.
- Bad: a lookup map has to import every tool to be built, and moves
  a spelling mistake to run time. A direct import of the descriptor is
  checked by the type checker, fails on a typo at import instead of at call
  time, and loads only the module asked for.

### D. A dispatcher that calls a tool by name

- Good: a runtime would not need its own registry.
- Bad: owning dispatch means owning argument validation,
  dependency injection and error mapping, which this package does not do.
  `to_mcp_tool` drops `func` because the runtime's registry keeps it, and
  the descriptor documentation tells runtime authors to look a tool up by
  name and call `func(dependency, **args)`.

### E. Findings name the tool only, with per-member validation (chosen)

- Good: `Finding` and the merge stay as they are, with no new field.
- Good: `validate_provider` on each member already answers which member a
  finding belongs to, using the API every consumer runs.
- Neutral: a consumer that needs provenance runs the validator once per
  member as well as on the merge.
- Bad: a `duplicate_name` across members names the tool, and the consumer
  finds the members that list it itself.

### F. Record member provenance on `Finding` now

- Good: each merged finding names its member directly.
- Bad: no consumer needs it, and per-member validation already answers
  the question.
- Bad: a nested merge needs a provenance path rather than one member, a
  shape better settled against a real consumer's need.

## More Information

Additive: a new function and one new export. `SPEC_VERSION` is the
descriptor format version and no descriptor field changes, so this decision
needs no `SPEC_VERSION` change of its own. Ships in octools 0.2.0.
