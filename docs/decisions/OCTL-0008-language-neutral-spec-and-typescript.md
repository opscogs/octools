---
status: accepted
version: 1.0.0
date: 2026-10-08
decision-makers: OpsCogs maintainers
---

# OCTL-0008 language-neutral spec and TypeScript package

## Context and Problem Statement

The descriptor, the envelopes, the closed vocabularies and their fallbacks,
the validator rules and the converter output are a wire format: an MCP
server, an agent runtime and a tool library each read or write it, and
none of them has to be written in Python. A TypeScript producer or reader
today has to restate that format by hand from the published docs, and a
hand-written copy drifts from the Python models the first time a minor
release adds a field or a vocabulary value.

The format also has no statement of its own outside the Python package.
The models are the definition, so "conforms to `octools`" means "behaves
like this Python code", which another implementation can only check by
reading that code.

Where does the format live so that more than one language can implement it
and prove conformance, what does the TypeScript package cover, and how are
the two packages versioned and released?

## Decision Drivers

- One definition of the wire format, checked by machine, that any
  implementation can test against without reading another language's code.
- A TypeScript producer and reader get the same guarantees a Python one
  has: strict producers, tolerant `read_envelope`, the same validator
  findings and the same converter output.
- The dependency-direction rule holds in every language: one schema
  library at most, never an SDK, converters return plain data.
- The [OCTL-0006](./OCTL-0006-tolerant-readers.md) compatibility contract
  means the same thing to a consumer whichever package it installs.
- A change to the format cannot land in one language and not the other.
- Releases need no long-lived registry credentials.

## Considered Options

Repository layout:

- **A1.** One monorepo holding both packages and the spec.
- **A2.** Separate repositories per language, with the spec in one of them.

TypeScript scope:

- **B1.** Types only: declarations of the wire shapes.
- **B2.** Types and a tolerant reader.
- **B3.** Full parity with the language-neutral public API.

TypeScript schema library:

- **C1.** zod v4.
- **C2.** TypeBox.
- **C3.** No schema library: hand-written validation and JSON Schema.

Versioning:

- **D1.** Lockstep: one version for both packages.
- **D2.** Independent versions per package.

## Decision Outcome

Chosen options: **A1, one monorepo**; **B3, full parity**; **C1, zod v4**;
**D1, lockstep versioning**, because together they give one checked
definition of the format, one compatibility contract and one release that
cannot ship a format change to one language only.

### Repository and license

`octools` is an open-source repository under the MIT license, holding three
parts:

- `python/`: the Python package, published to PyPI as `octools`.
- `typescript/`: the TypeScript package, published to npm as
  `@opscogs/octools`.
- `spec/`: the language-neutral contract both packages implement.

### The spec is the conformance authority

`spec/` defines what conforming means for every implementation:

- **`spec/vocabulary.json`** holds `SPEC_VERSION`, every closed vocabulary
  with its declared fallback, and the shared constants (name patterns,
  sentence limits, strict-mode keyword and format sets, meta keys).
- **`spec/schema/*.schema.json`** holds the JSON Schemas of the descriptor
  and the envelopes.
- **`spec/fixtures/<operation>/<case>.json`** holds curated golden cases,
  one file per case, each with `description`, `input` and `expected`. An
  error or a validator finding is expressed as data in `expected`, never
  as a language-specific exception type.

`spec/vocabulary.json` and `spec/schema/` are generated from the Python
models by `scripts/sync_spec.py`. CI runs it with `--check`, and the test
suite fails while a generated file is stale. The fixtures are written by
hand and reviewed like code.

Every implementation's test suite loads every fixture under
`spec/fixtures/` and passes all of them. No fixture is skipped, marked
expected-to-fail or filtered by language; an implementation that cannot
pass a fixture does not ship.

The Python models stay the source the generated files come from. A change
to the wire format lands in one change that updates the models, the
regenerated spec, the new or changed fixtures, and both implementations.

### TypeScript scope

The TypeScript package implements every language-neutral name in the
Python package's `__all__`: the descriptor and its errors, the three
envelopes and `ArtifactRef`, `read_envelope`, `validate_tabular`,
`validate_tool`, `validate_provider` and `check_tool_listing`,
`merge_providers`, the MCP and Anthropic converters, the listing helpers,
the schema helpers, and the vocabularies, fallbacks and constants.

- **Names** follow TypeScript idiom: functions and fields in camelCase
  (`readEnvelope`, `validateProvider`, `toMcpTool`), types in PascalCase,
  constants in upper snake case. The mapping from each Python name is
  one to one and documented.
- **Wire keys never change.** Every key a descriptor, envelope, finding or
  converter emits or reads is spelled exactly as the spec spells it, in
  both packages (`column_kinds`, `next_cursor`, `inputSchema`).
- **Schema helpers** take zod schemas where the Python helpers take
  pydantic models, and emit the same JSON Schema dialect and strict-clean
  output. A Python helper that exists only to steer pydantic's schema
  generator, such as `NoTitleGenerator`, has no TypeScript counterpart.

The public API of the TypeScript package is exactly its root export list,
under the same rule [OCTL-0006](./OCTL-0006-tolerant-readers.md) sets for
the Python `__all__`.

### Dependencies and runtime floors

The TypeScript package mirrors the Python dependency rule:

- Its only runtime dependency is zod v4, declared as a peer dependency so
  the consumer's own zod is the one in use.
- It never depends on an SDK (`@modelcontextprotocol/sdk`,
  `@anthropic-ai/sdk`, `openai`), and its converters return plain objects.
- It runs on Node 22 or later, ships ESM only, and ships its type
  declarations.

The Python package keeps its floor of Python 3.12 and its single
dependency on pydantic.

### Lockstep versioning

- One release tag publishes both packages at the same version, recorded in
  one changelog.
- `SPEC_VERSION` major and minor are the same in both packages for every
  release.
- The [OCTL-0006](./OCTL-0006-tolerant-readers.md) compatibility contract
  applies to both packages identically: within a major, a minor adds only
  what a tolerant reader can drop or read as its fallback, and the
  consumer dependency-range rule (floor at the oldest release with every
  name used, ceiling at the next major) applies to npm ranges as it does
  to Python ones.
- A fix in one language still releases both, so a version number names
  one state of the whole repository.

### Publishing

Both registries publish through trusted publishing: the release workflow
authenticates to PyPI and npm with OpenID Connect, and no registry token is
stored. The npm package is published with provenance.

### Consequences

- Good: conformance is a set of files any implementation can test
  against, not a reading of the Python code.
- Good: a TypeScript producer or reader gets the same strictness,
  tolerance, findings and converter output as a Python one.
- Good: a format change cannot ship to one language only, because the
  fixtures and the stale-spec check fail until both implement it.
- Good: a consumer reads one version number and one changelog, and the
  compatibility contract means the same thing in both registries.
- Good: releases hold no long-lived registry credentials.
- Bad: every decision record and every vocabulary or field change ships in
  both languages, which raises the cost of each change.
- Bad: a fix in one language produces a release of the other with no
  change in it.
- Bad: a TypeScript consumer brings zod v4; one already on another schema
  library carries both.
- Neutral: the 1.x scope fence in
  [OCTL-0001](./OCTL-0001-descriptor-origin.md) is unchanged; a second
  language adds no descriptor field or envelope capability.
- Neutral: the dependency-direction rule now covers both packages: every
  OpsCogs library may depend on `octools` in its language, and neither
  package depends on an OpsCogs package or an SDK.

### Confirmation

- `scripts/sync_spec.py --check` runs in CI and in the Python test suite,
  and fails while `spec/vocabulary.json` or `spec/schema/` differs from
  what the models generate.
- Both test suites load every fixture under `spec/fixtures/` and fail on
  any fixture they do not pass; a check counts the fixtures each suite ran
  against the files on disk, so a skipped fixture fails the build.
- The TypeScript suite checks that its exported vocabularies, fallbacks
  and constants equal `spec/vocabulary.json`, and that the JSON Schemas it
  emits equal `spec/schema/`.
- A tag build checks that both package manifests carry the tag's version
  before either package publishes.
- Review checks that a pull request changing the wire format touches the
  models, the spec, the fixtures and both implementations together.

## Pros and Cons of the Options

### A1. One monorepo (chosen)

- Good: a format change, its fixtures and both implementations land in one
  reviewed change.
- Good: one issue tracker, one changelog and one release workflow.
- Bad: contributors to one language check out the other.

### A2. Separate repositories per language

- Good: each package has its own history and tooling.
- Bad: a format change spans repositories, so one language can ship it
  before the other.
- Bad: the spec lives in one repository and the other pins a copy, which
  drifts.

### B1. Types only

- Good: smallest package to maintain.
- Bad: a TypeScript reader has no tolerant reader and no validation, so it
  either rejects newer envelopes or accepts corrupt ones.
- Bad: a TypeScript producer has no validator or converters.

### B2. Types and a tolerant reader

- Good: covers the most common TypeScript use, reading tool results.
- Bad: a TypeScript producer still restates the descriptor rules and the
  converters by hand.

### B3. Full parity (chosen)

- Good: a producer or reader in either language gets the whole contract.
- Good: the fixtures cover one API surface, not a per-language subset.
- Bad: the largest package to maintain.

### C1. zod v4 (chosen)

- Good: the most widely used TypeScript schema library, so consumers often
  have it already.
- Good: v4 emits JSON Schema itself, as pydantic does for the Python
  models.
- Bad: a runtime peer dependency for every consumer.

### C2. TypeBox

- Good: schemas are JSON Schema objects, so emitting them needs no
  conversion.
- Bad: a smaller user base than zod, so more consumers carry a second
  schema library.

### C3. No schema library

- Good: no runtime dependency at all.
- Bad: validation and JSON Schema generation are written and maintained by
  hand, in parallel with the models they must match.

### D1. Lockstep versioning (chosen)

- Good: one version names one state of the format and of both packages.
- Good: the compatibility contract and the dependency-range rule read the
  same in both registries.
- Bad: a release of one package may carry no change for it.

### D2. Independent versions

- Good: a package releases only when it changes.
- Bad: a consumer needs a mapping from each package version to
  `SPEC_VERSION` to know which packages interoperate.
- Bad: the changelog splits, and a format change can reach one registry
  before the other.

## More Information

Ships in octools 1.2.0, the first release published to both PyPI and npm.
Adding `spec/` and the TypeScript package adds no descriptor or envelope
field and no vocabulary value, so it needs no `SPEC_VERSION` change of its
own.

Related records: [OCTL-0001](./OCTL-0001-descriptor-origin.md) (the
descriptor, the dependency direction and the 1.x scope fence, unchanged)
and [OCTL-0006](./OCTL-0006-tolerant-readers.md) (the compatibility
contract, now applied to both packages). Every later record that changes
the wire format names its spec and fixture changes under Confirmation.

The parity scope is the public API, the root export list in each language.
The `octools list` command is outside `__all__` and outside this decision.
