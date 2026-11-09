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
- The namespace names the product. A consumer may qualify it with a vendor
  outside tool names, as `<vendor>_<namespace>`, which is also the prefix a
  host applies with `prefix_tools` to settle a namespace collision
  (`acme_demo_get_rows`).
- `NAME_RE` (48 characters) applies to the published name, namespace
  included. The 16 characters to the 64 limit stay for the prefix an agent
  host adds when it routes to a server.
- `prefix_tools(tools, name_prefix)` returns renamed copies, each keeping its
  own `func`:
  - The prefix is lowercased, and one without a trailing underscore gets one,
    so a host passes `Demo`, `demo` or `demo_` and gets the same names.
  - A name that already starts with the prefix counts as published and is
    kept, so applying the prefix twice changes nothing. A bare name that
    happens to start with the prefix (`demo_mode_status` under `demo_`) is
    therefore indistinguishable from a published one; a provider keeps its
    bare names free of its own namespace, which octools cannot check after
    publication.
  - An empty prefix renames nothing. A malformed prefix (`demo-`, `_`)
    yields names that break `NAME_RE` and raises `OCToolError`.
  - `meta["alias_of"]` is prefixed the same way, as a name, not rewritten as
    text.
  - Sibling references are rewritten in exactly three places: the tool's
    `description`, every `description` inside `input_schema`, and every
    `description` inside `output_schema`. Nothing else is rewritten: not the
    tool's `title`, not schema `title` keywords, not instance data or
    property keys, and not `meta` values other than `alias_of`. A provider
    that names a sibling anywhere else renames it there itself.
  - Every whole-word reference to a sibling in those descriptions becomes the
    sibling's published name. A reference is the sibling's listed name or,
    for a sibling already published, its bare form (`get_rows` for
    `demo_get_rows`), so a listing that mixes published and bare tools,
    such as a merge, ends with no reference to a tool that is not offered.
    The output schema is covered because the MCP converter publishes it, and
    its field descriptions point an agent at the next call as often as the
    input's do. A word is a run of ASCII letters, digits and underscores, so
    an occurrence that is already prefixed, or part of a longer name, is
    left alone, as are words that name no sibling.
  - How a reference is matched depends on the name being matched, the
    sibling's listed name or its bare form. A name holding an underscore
    (`get_rows`) is rewritten wherever it stands as a whole word. A name
    without one (`ping`, `status`) is rewritten only inside a code span, text
    between single backticks, so "ping the server" stays prose and `` `ping` ``
    becomes `` `demo_ping` ``. A one-word tool name is usually an ordinary
    word too, and only the backticks say it names a tool. A provider
    therefore writes a one-word sibling name in backticks.
  - Instance data in the schema (`const`, `default`, `enum`, `examples`) is
    never rewritten; under `properties`, `$defs`, `definitions`,
    `patternProperties` and `dependentSchemas` the keys are names and are
    never rewritten either.
  - Two tools that would publish under one name (`get_rows` and
    `demo_get_rows` under `demo_`) raise `OCToolError` naming both. A host
    prefixes after merging, so `merge_providers` does not see this
    collision; `prefix_tools` must.
  - A published name that breaks `NAME_RE`, or an item that is not an
    `OCTool`, raises `OCToolError`.
  - The guarantee: the published names are unique, and every whole-word
    sibling reference, bare or prefixed, names a published tool.
- A host that publishes a provider behind its own prefix calls
  `prefix_tools` on the listing and registers and dispatches by the returned
  names. The converters' `name_prefix` stays plain concatenation with the
  target's name rule, for a host that needs only a renamed wire name.
- `validate_namespace(provider, namespace)` reports `namespace_missing` when
  `namespace` is empty, `namespace_pattern` when it breaks `NAMESPACE_RE`
  (either stops the check), and otherwise `name_outside_namespace` for each
  tool whose name does not match `^<namespace>_[a-z][a-z0-9_]*$`: the name
  starts with the namespace and an underscore, and what follows is itself a
  name, so `demo_`, `demo__rows` and `demo_1rows` are outside `demo`. The
  finding's message says which part failed. It is opt-in under
  [OCTL-0006](./OCTL-0006-tolerant-readers.md); `validate_provider` is
  unchanged. A consumer library makes it a conformance requirement of its
  own.
  - It checks tool names only. An alias target outside the namespace is
    already a missing tool to `validate_provider`, and a bare name that
    repeats the namespace (`demo_demo_rows`) is visible only to the consumer
    that holds the bare names, so neither is checked here.

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
  tool names, in a `title`, or in a `meta` value stays unprefixed, and the
  provider publishes that value itself.

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
