---
status: accepted
version: 1.0.0
date: 2026-11-09
decision-makers: OpsCogs maintainers
---

# OCTL-0010 provider namespaces and `prefix_tools`

## Context and Problem Statement

A tool name is the one handle an agent, a log line, a document and a command
line share. When a host publishes a provider's tools under a prefix it chose
(`acme_list_tables`), the name an agent sees differs from the name the
provider's documentation uses, and every description that points at a sibling
tool ("use `describe_table` for one table's columns") names a tool the host
does not offer. Two providers built for the same product also collide on
generic names. Who owns the prefix, and how does a published listing stay
consistent with itself?

## Decision Drivers

- One canonical tool name everywhere: agent docs, descriptions, CLI help, MCP
  listings and logs.
- A description that names a sibling tool must name it as published.
- The converters stay pure and per-tool; nothing in 1.x changes their output.
- No descriptor field and no `SPEC_VERSION` change.
- A provider keeps its internal tables and dispatch keyed by short names.

## Considered Options

- **A.** The provider declares a namespace; `prefix_tools` applies it once at
  publication, renaming tools and rewriting sibling references; an opt-in
  `validate_namespace` checks it.
- **B.** A `siblings` argument on each converter, rewriting references during
  conversion.
- **C.** A `namespace` field on `OCTool`.
- **D.** Hosts keep prefixing, and descriptions avoid naming sibling tools.

## Decision Outcome

Chosen option: **A**, because the listing an agent sees is then built once,
by the party that owns the names, and every wire format converts the same
renamed descriptors.

- A provider publishes its tools under a namespace: a product name matching
  `NAMESPACE_RE` (`^[a-z][a-z0-9]{0,15}$`), joined to the tool name by one
  underscore (`demo_get_rows`). The namespace holds no underscore, so the
  first underscore ends it. Providers built for one product share its
  namespace; a collision between them is a `duplicate_name` finding on their
  merge ([OCTL-0004](./OCTL-0004-merge-providers.md)).
- `NAME_RE` (48 characters) applies to the published name, namespace
  included. The 16 characters to the 64 limit stay for the prefix an agent
  host adds when it routes to a server.
- `prefix_tools(tools, name_prefix)` returns renamed copies, each keeping its
  own `func`:
  - A prefix without a trailing underscore gets one, so a host passes the
    bare namespace (`demo`) or the namespace with its underscore (`demo_`)
    and gets the same names.
  - A name that already starts with the prefix is kept, so applying the
    prefix twice changes nothing.
  - `meta["alias_of"]` is prefixed the same way.
  - Every whole-word occurrence of a sibling's original name in `description`
    and in any `description` inside `input_schema` or `output_schema` becomes
    the sibling's published name. The output schema is covered because the
    MCP converter publishes it, and its field descriptions point an agent at
    the next call as often as the input's do. A word is a run of ASCII letters, digits and underscores,
    so an occurrence that is already prefixed, or part of a longer name, is
    left alone, as are words that name no sibling.
  - Instance data in the schema (`const`, `default`, `enum`, `examples`) is
    never rewritten; under `properties`, `$defs`, `definitions`,
    `patternProperties` and `dependentSchemas` the keys are names and are
    never rewritten either.
  - A published name that breaks `NAME_RE`, or an item that is not an
    `OCTool`, raises `OCToolError`.
- A host that publishes a provider behind its own prefix calls
  `prefix_tools` on the listing and registers and dispatches by the returned
  names. The converters' `name_prefix` stays plain concatenation with the
  target's name rule, for a host that needs only a renamed wire name.
- `validate_namespace(provider, namespace)` reports `namespace_missing` when
  `namespace` is empty, `namespace_pattern` when it breaks `NAMESPACE_RE`
  (either stops the check), and otherwise `name_outside_namespace` for each
  tool whose name does not start with `<namespace>_`. It is opt-in under
  [OCTL-0006](./OCTL-0006-tolerant-readers.md); `validate_provider` is
  unchanged. A consumer library makes it a conformance requirement of its
  own.

### Consequences

- Good: an agent follows a description's pointer to a sibling tool and finds
  it on the first call.
- Good: MCP and Anthropic listings carry the same names, because both convert
  the renamed descriptors.
- Good: providers keep short names internally; the namespace is applied in
  one place.
- Bad: a name is rewritten only where it stands as a whole word; a sibling
  named in prose by another spelling (`describe table`) is not found.
- Bad: rewriting is limited to descriptions; a sibling named in an `enum` of
  tool names, or in `title`, stays unprefixed, and the provider publishes
  that value itself.

### Confirmation

Spec fixtures under `prefix_tools` and `validate_namespace` pass in both
implementations; the example provider, prefixed, passes `validate_provider`
and `validate_namespace` and converts under both converters with its names
unchanged.

## Pros and Cons of the Options

### A. Provider namespace, `prefix_tools`, opt-in `validate_namespace` (chosen)

- Good: one helper serves every wire format and every host.
- Good: idempotent, so a host prefix equal to the namespace is harmless.
- Neutral: the converters' `name_prefix` remains for wire-only renaming.

### B. A `siblings` argument on the converters

- Good: no new function.
- Bad: every converter call needs the full listing, and each wire format
  repeats the rewrite.
- Bad: the host's registry still holds the unprefixed descriptors, so the
  dispatch name and the listed name differ.

### C. A `namespace` field on `OCTool`

- Good: a reader sees the namespace without parsing the name.
- Bad: a descriptor field needs a `SPEC_VERSION` minor and a fallback, for a
  fact the name already carries.

### D. Hosts keep prefixing, and descriptions avoid sibling names

- Good: no change to octools.
- Bad: descriptions lose the pointers that guide an agent to the right
  tool, and each host picks its own prefix, so names differ between surfaces.

## More Information

Ships in octools 1.4.0 with `SPEC_VERSION` `"1.3"` unchanged: no descriptor
field changes. `NAMESPACE_RE` joins the constants in `spec/vocabulary.json`.
