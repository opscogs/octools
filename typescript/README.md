# @opscogs/octools

[![npm](https://img.shields.io/npm/v/@opscogs/octools)](https://www.npmjs.com/package/@opscogs/octools)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/opscogs/octools/blob/main/LICENSE)

OpsCogs standard interface for AI agent tools, for TypeScript: the result
envelopes every tool returns, their tolerant reader, the closed vocabularies
and their fallbacks, and the cell check for tabular results. It implements
the same language-neutral contract as the Python package
[`octools`](https://pypi.org/project/octools/), and passes the same golden
cases.

## Install

Node 22.18 or newer, ESM only. zod 4 is a peer dependency and the only
runtime dependency.

```sh
npm install @opscogs/octools zod
```

## Quick start

```ts
import {
  TabularEnvelope,
  readEnvelope,
  validateTabular,
} from "@opscogs/octools";

// Producer: a strict parse returns the wire form, ready for JSON.stringify.
const result = TabularEnvelope.parse({
  columns: ["host", "hits"],
  column_kinds: ["fqdn", "integer"],
  rows: [["a.demo.example", 3]],
  row_count: 1,
  truncated: false,
});
console.log(validateTabular(result)); // []

// Reader: tolerates fields and vocabulary values a newer producer adds.
const read = readEnvelope(TabularEnvelope, JSON.stringify(result));
console.log(read);
```

Wire keys are spelled exactly as the spec spells them (`column_kinds`,
`next_cursor`); API names are camelCase.

## Links

- [Documentation](https://octools.docs.opscogs.com)
- [Source and issues](https://github.com/opscogs/octools)
- [Changelog](https://github.com/opscogs/octools/blob/main/CHANGELOG.md)

## Names

Each name maps one to one onto a name in the Python package's `__all__`.

| Python                                                                 | TypeScript                                                                            |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `RecordsEnvelope[T]`                                                   | `RecordsEnvelope(item)` (a zod schema), type `RecordsEnvelope<T>`                     |
| `TabularEnvelope`, `ArtifactEnvelope`, `ArtifactRef`                   | the same names: a zod schema and its output type                                      |
| `Model.model_validate(data)`                                           | `Model.parse(data)`                                                                   |
| `read_envelope`                                                        | `readEnvelope`                                                                        |
| `records_schema`, `tabular_schema`, `artifact_schema`                  | `recordsSchema`, `tabularSchema`, `artifactSchema`                                    |
| `validate_tabular`                                                     | `validateTabular`                                                                     |
| `strict_clean`, `strip_keys(schema, keys=..., prefixes=...)`           | `strictClean`, `stripKeys(schema, { keys, prefixes })`                                |
| `strip_titles`, `close_objects`                                        | `stripTitles`, `closeObjects`                                                         |
| `schema_for(Model, mode=...)`, `input_schema_for`, `output_schema_for` | `schemaFor(schema, { io })`, `inputSchemaFor`, `outputSchemaFor`, taking zod schemas  |
| `NoTitleGenerator`                                                     | none: `schemaFor` strips titles itself                                                |
| `OCTool(name=..., input_schema=..., ...)`                              | `new OCTool({ name, inputSchema, ... })`: every field in camelCase                    |
| `ToolProvider` (`all_tools()`)                                         | interface `ToolProvider` (`allTools()`)                                               |
| `merge_providers`, `check_tool_listing`                                | `mergeProviders`, `checkToolListing`                                                  |
| `validate_tool`, `validate_provider`, `count_sentences`                | `validateTool`, `validateProvider`, `countSentences`                                  |
| `to_mcp_tool(tool, name_prefix=...)`, `to_anthropic_tool`              | `toMcpTool(tool, { namePrefix })`, `toAnthropicTool`                                  |
| `summarize_tool`, `summarize_provider(provider, access=...)`           | `summarizeTool`, `summarizeProvider(provider, { access })`                            |
| `render_listing(provider, style=..., access=..., pretty=...)`          | `renderListing(provider, { style, access, pretty })`; a bad style throws `RangeError` |
| `render_markdown_table`, `ToolSummary.as_row()`, `InputSummary`        | `renderMarkdownTable`, `ToolSummary.asRow()`, `InputSummary`                          |
| `Cell`, `ColumnKind`, `ColumnScale`, `Sensitivity`                     | the same type names                                                                   |
| `Access`, `ResultKind`, `ListingStyle`                                 | the same type names                                                                   |
| `Finding`, `OCToolError`                                               | the same class names                                                                  |
| constants such as `SPEC_VERSION`, `COLUMN_KINDS`, `NAME_RE`            | the same names                                                                        |

The `*_RE` constants are `RegExp` objects, the `STRICT_*` sets are
`ReadonlySet<string>`, and the vocabulary values are readonly arrays.

The schema helpers read zod metadata where the Python ones read pydantic
field extras: `.meta({ "x-sensitivity": "identifier" })` on a result field,
`.meta({ format: "date-time" })` on a `z.string()`, and `.meta({ id })` on
a model that appears in `$defs` under that name when nested. A schema
emits the side a parse accepts: a `.default()` over a schema with a
transform states its default only as `.prefault()`, and a zod string
format such as `z.iso.datetime()` also carries a `pattern`, which
`strictClean` reports in an input schema.

## License

MIT. See [LICENSE](https://github.com/opscogs/octools/blob/main/LICENSE). The OpsCogs name and logos are
not covered by that license; see [NOTICE](https://github.com/opscogs/octools/blob/main/NOTICE).
