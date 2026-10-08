# The TypeScript package

Version: **1.2.0** · Date: 2026-10-08

`@opscogs/octools` is `octools` for TypeScript and JavaScript. It covers
the whole public API of the Python package: the `OCTool` descriptor, the
result envelopes and their tolerant reader, the validators, the MCP and
Anthropic converters, the listing helpers, the schema helpers, and the
vocabularies, fallbacks and constants. Both packages pass the same
`spec/` conformance fixtures and are released together at the same
version (see [One contract, two languages](./index.md#one-contract-two-languages)).

Every page of this site shows each example in both languages. This page
covers what is specific to TypeScript: the runtime, the names, schemas
from zod, and the few places where the two languages behave differently.
The generated [TypeScript API reference](./api/typescript/index.html)
documents every export.

## Install and runtime

```sh
npm install @opscogs/octools zod
```

- **Node 22.18 or newer.** The package declares `engines.node >= 22.18.0`.
- **ESM only.** Load it with `import`; there is no CommonJS build, so a
  CommonJS module uses a dynamic `import()`. Type declarations ship in the
  package.
- **zod 4 is a peer dependency** (`^4.4.0`) and the only runtime
  dependency, so the zod your project already uses is the one the
  envelopes and schema helpers run on. Import it as
  `import * as z from "zod"`.
- **No SDK.** The package never depends on `@modelcontextprotocol/sdk`,
  `@anthropic-ai/sdk` or `openai`; the converters return plain objects.

## Names

API names follow TypeScript idiom: functions and fields in camelCase,
types in PascalCase, constants in upper snake case. Wire keys never
change: every key a descriptor, envelope, finding, listing row or
converter emits or reads is spelled exactly as the spec spells it
(`column_kinds`, `next_cursor`, `inputSchema`, `result_kind`). Each name
maps one to one onto a name in the Python package's `__all__`:

| Python                                                                 | TypeScript                                                                           |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `OCTool(name=..., input_schema=..., ...)`                              | `new OCTool({ name, inputSchema, ... })`, every field in camelCase                   |
| `ToolProvider` (`all_tools()`)                                         | interface `ToolProvider` (`allTools()`)                                              |
| `RecordsEnvelope[T]`                                                   | `RecordsEnvelope(item)`, a zod schema; type `RecordsEnvelope<T>`                     |
| `TabularEnvelope`, `ArtifactEnvelope`, `ArtifactRef`                   | the same names: a zod schema and its output type                                     |
| `Model.model_validate(data)`                                           | `Model.parse(data)`                                                                  |
| `read_envelope`, `validate_tabular`                                    | `readEnvelope`, `validateTabular`                                                    |
| `records_schema`, `tabular_schema`, `artifact_schema`                  | `recordsSchema`, `tabularSchema`, `artifactSchema`                                   |
| `schema_for(Model, mode=...)`, `input_schema_for`, `output_schema_for` | `schemaFor(schema, { io })`, `inputSchemaFor`, `outputSchemaFor`, taking zod schemas |
| `strict_clean`, `strip_keys(schema, keys=..., prefixes=...)`           | `strictClean`, `stripKeys(schema, { keys, prefixes })`                               |
| `strip_titles`, `close_objects`                                        | `stripTitles`, `closeObjects`                                                        |
| `NoTitleGenerator`                                                     | none: `schemaFor` strips titles itself                                               |
| `validate_tool`, `validate_provider`, `count_sentences`                | `validateTool`, `validateProvider`, `countSentences`                                 |
| `merge_providers`, `check_tool_listing`                                | `mergeProviders`, `checkToolListing`                                                 |
| `to_mcp_tool(tool, name_prefix=...)`, `to_anthropic_tool`              | `toMcpTool(tool, { namePrefix })`, `toAnthropicTool`                                 |
| `summarize_tool`, `summarize_provider(provider, access=...)`           | `summarizeTool`, `summarizeProvider(provider, { access })`                           |
| `render_listing(provider, style=..., access=..., pretty=...)`          | `renderListing(provider, { style, access, pretty })`                                 |
| `render_markdown_table`, `ToolSummary.as_row()`, `InputSummary`        | `renderMarkdownTable`, `ToolSummary.asRow()`, `InputSummary`                         |
| `Cell`, `ColumnKind`, `ColumnScale`, `Sensitivity`                     | the same type names                                                                  |
| `Access`, `ResultKind`, `ListingStyle`                                 | the same type names                                                                  |
| `Finding`, `OCToolError`                                               | the same class names                                                                 |
| constants such as `SPEC_VERSION`, `COLUMN_KINDS`, `NAME_RE`            | the same names                                                                       |

The `*_RE` constants are `RegExp` objects, the `STRICT_*` sets are
`ReadonlySet<string>`, and the vocabulary values are readonly arrays. Keyword
arguments become one options object (`{ namePrefix }`, `{ access }`,
`{ style, access, pretty }`). The public API is exactly the package
root's export list; a module path inside the package carries no
compatibility promise.

## Schemas from zod

The schema helpers take zod schemas where the Python helpers take
pydantic models, and emit the same JSON Schema 2020-12 dialect and the
same strict-clean output. zod metadata plays the role of pydantic field
extras:

- `.describe("...")` or `.meta({ description })` sets a field's
  `description`.
- `.meta({ "x-sensitivity": "identifier" })` on a result field emits the
  `x-sensitivity` extension key.
- `.meta({ format: "date-time" })` on a `z.string()` emits a `format`.
- `.meta({ id: "Name" })` on a model puts it in `$defs` under that name
  wherever it is nested and refers to it by `$ref`, as pydantic does for
  every nested model. The envelopes carry their own ids, so a
  `TabularEnvelope` field in an argument model becomes
  `{"$ref": "#/$defs/TabularEnvelope"}`.

`inputSchemaFor` closes every object with `additionalProperties: false`.
`outputSchemaFor` keeps each object as the schema declares it: a
`z.object` stays open, as a pydantic model does by default, and a
`z.strictObject` is closed. A schema describes what a parse accepts (the
wire shape), so a `.default()` over a schema with a transform states its
default only as `.prefault()`.

There is no `NoTitleGenerator`: the Python class exists only to steer
pydantic's schema generator, and `schemaFor` removes every `title`
itself.

## Envelopes are parses

Each envelope is a zod schema whose output type has the same name.
`TabularEnvelope.parse(data)` is the strict producer path: an unknown key
or vocabulary value throws `ZodError`, and the value it returns is the
envelope's wire form, ready for `JSON.stringify`, with unset optional
fields left out and `resumable` present only on a truncated list.
`readEnvelope(model, data)` is the tolerant reader for an envelope from
another process, with the same fallbacks as Python's `read_envelope`
(see [Reading envelopes from another process](./octools_descriptor.md#reading-envelopes-from-another-process)).

```ts
import { TabularEnvelope, readEnvelope, validateTabular } from "@opscogs/octools";

const result = TabularEnvelope.parse({
  columns: ["host", "hits"],
  column_kinds: ["fqdn", "integer"],
  rows: [["a.demo.example", 3]],
  row_count: 1,
  truncated: false,
});
validateTabular(result); // []

const read = readEnvelope(TabularEnvelope, JSON.stringify(result));
```

## Language differences

Both packages pass every `spec/` fixture, so they agree on everything the
fixtures pin down. Where JavaScript and Python differ underneath, the
packages differ as follows.

| Topic                       | Python `octools`                                                           | TypeScript `@opscogs/octools`                                                                      |
| --------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| JSON `1.0` and `1`          | `1.0` stays a float: a `1.0` cell fails the `integer` and `big_integer` kinds | `JSON.parse` reads both as the number `1`: an integral cell fits `integer` and `big_integer` however it was written |
| Integers above 2^53 − 1     | Read exactly in every integer field and cell                               | An integer field (`count`, `row_count`, `total_count`, `bytes`, `width`, `height`) beyond it fails the parse; a numeric cell is already rounded by `JSON.parse` |
| Type coercion               | pydantic's lax mode converts `"3"` to `3` and `"false"` to `false`         | No coercion: a value of the wrong JSON type throws `ZodError`, in `.parse` and in `readEnvelope`  |
| Bytes in `readEnvelope`     | UTF-8, UTF-16 or UTF-32, detected                                          | A `Uint8Array` is decoded as UTF-8, the JSON wire encoding, only; UTF-16 or UTF-32 bytes fail to read |
| String formats in schemas   | A pydantic format emits `format` only                                      | A zod format such as `z.iso.datetime()` also emits a `pattern`, which `strictClean` reports in an input schema; use `z.string().meta({ format: "date-time" })` |
| Foreign items in a listing  | Labelled with Python type names: `<int>`, `<str>`, `<NoneType>`, `<list>` | Labelled with JavaScript type names: `<number>`, `<string>`, `<null>`, `<array>`                   |
| Schema helpers              | Take pydantic models; field extras via `json_schema_extra`                 | Take zod schemas; field extras via `.meta()`                                                       |
| `NoTitleGenerator`          | Exported                                                                   | No counterpart                                                                                     |

What these mean in practice:

- **Send big integers as strings.** `total_count` and `big_integer`
  cells accept a decimal string, which both languages read exactly. A
  TypeScript reader cannot recover an integer cell beyond 2^53 − 1 that
  arrived as a JSON number, because the rounding happens in `JSON.parse`
  before `octools` sees the value.
- **Send the right JSON types.** An envelope a Python reader accepts
  through coercion (`"count": "3"`) fails in TypeScript. A producer's own
  strict parse in its tests catches this, in either language.
- **Foreign-item labels** appear in `not_octool` messages and in the
  `tool` field of a `duplicate_name` finding raised over two non-tool
  items, so a test that asserts on that `tool` value is language-specific.

Errors are JavaScript errors: `OCToolError` extends `Error`, an envelope
that fails a parse throws `ZodError`, malformed JSON text throws
`SyntaxError`, and `renderListing` throws `RangeError` for an unknown
style where Python raises `ValueError`.

The `octools list` command and the `octools.example` demo provider ship
with the Python package only. A TypeScript CLI renders the same listing
with `renderListing` (see
[Listing tools for people](./octools_listing.md#wiring-render_listing-into-your-own-cli)).

## API reference

The [TypeScript API reference](./api/typescript/index.html) is generated
by TypeDoc from the package's declarations and doc comments, for the
release this site documents.
