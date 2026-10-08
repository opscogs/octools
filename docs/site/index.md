# octools

Version: **1.2.1** · Date: 2026-10-08

> `octools` is the OpsCogs standard interface for AI agent tools, in Python
> and TypeScript.

It holds the `OCTool` descriptor, the result envelopes every tool returns,
a conformance validator, and plain-data converters to the MCP and
Anthropic tool shapes. A library describes each capability once as an
`OCTool`; any agent runtime registers it without re-expressing it by hand.

Think of it as OpenAPI for agent tools: one vendor-neutral contract that
every OpsCogs library fills in, so the interface is defined once and each
adopter only supplies its tools. The contract ships as two packages with
the same API, one per language:

| Language   | Package                                                          | Runtime                   | Only dependency            |
| ---------- | ---------------------------------------------------------------- | ------------------------- | -------------------------- |
| Python     | [`octools` on PyPI](https://pypi.org/project/octools/)            | Python 3.12 or newer      | `pydantic >= 2.12, < 3`    |
| TypeScript | [`@opscogs/octools` on npm](https://www.npmjs.com/package/@opscogs/octools) | Node 22.18 or newer, ESM only | `zod` 4, a peer dependency |

Neither package depends on an OpsCogs package or an agent SDK, so the
dependency arrow always points toward `octools`, never back. The source
for both lives in one repository:
[github.com/opscogs/octools](https://github.com/opscogs/octools).

- [The OCTool descriptor](./octools_descriptor.md) - every field, the
  envelopes, the escape conditions, strict-clean rules, versioning.
- [Converters](./octools_converters.md) - the MCP and Anthropic mappings,
  what is lossless and what is dropped.
- [Listing tools for people](./octools_listing.md) - the `octools list`
  command and the listing API behind it.
- [The TypeScript package](./octools_typescript.md) - runtime floor, the
  Python to TypeScript name map, and where the two languages differ.
- [TypeScript API](./api/typescript/index.html) - the generated reference
  for every export of `@opscogs/octools`.

Code examples on these pages come in both languages. Pick a tab once and
every page follows it.

## Install

=== "Python"

    Python 3.12 or newer and `pydantic >= 2.12, < 3` (the only dependency).

    ```sh
    pip install octools
    ```

=== "TypeScript"

    Node 22.18 or newer; the package is ESM only and ships its type
    declarations. zod 4 is a peer dependency, so install it beside the
    package.

    ```sh
    npm install @opscogs/octools zod
    ```

## One contract, two languages

The wire format is defined once, outside either package, in the
repository's [`spec/`](https://github.com/opscogs/octools/tree/main/spec)
directory:

- `vocabulary.json` - `SPEC_VERSION`, every closed vocabulary with its
  declared fallback, and the shared constants (name patterns, sentence
  limits, the strict-mode keyword and format sets).
- `schema/*.schema.json` - the JSON Schemas of the descriptor and the
  envelopes.
- `fixtures/<operation>/<case>.json` - golden cases, one per file, each
  with an `input` and the `expected` result. An error or a validator
  finding is data in `expected`, never a language's exception type.

Both packages' test suites run every fixture and pass all of them; none
is skipped or filtered by language. Conforming to `octools` means passing
`spec/`, so the same envelope, the same findings and the same converter
output come back whichever package produced them. Wire keys are spelled
exactly as the spec spells them in both (`column_kinds`, `next_cursor`,
`inputSchema`); only the API names follow each language's idiom.

**Versions move in lockstep.** One release tag publishes both packages at
the same version, recorded in one changelog, and `SPEC_VERSION` is the
same in both. A pre-release is spelled `1.2.0rc1` on PyPI and `1.2.0-rc.1`
on npm, where it is published under the `next` tag and never installed by
default. The compatibility contract in
[Versioning and deprecation](./octools_descriptor.md#versioning-and-deprecation)
applies to both registries identically: a consuming library declares a
range from the oldest release carrying every name it uses up to the next
major.

## Quick start

Describe the arguments and result as models, wrap the function in an
`OCTool`, and list the tools from the provider function (`all_tools()` in
Python, `allTools()` in TypeScript):

=== "Python"

    ```python
    from pydantic import BaseModel, Field
    from octools import OCTool, RecordsEnvelope, input_schema_for, records_schema


    class EchoArgs(BaseModel):
        values: list[str] = Field(description="Strings to echo back, one record each.")


    class EchoRecord(BaseModel):
        value: str = Field(description="The echoed string.")
        position: int = Field(description="Zero-based position in the input.")


    def echo_records(_dependency, *, values: list[str]) -> dict:
        records = [EchoRecord(value=v, position=i) for i, v in enumerate(values)]
        return RecordsEnvelope[EchoRecord](
            records=records, count=len(records), truncated=False
        ).model_dump(mode="json")


    ECHO_RECORDS = OCTool(
        name="echo_records",
        description="Return each input string as one record with its position. Use it to check a tool round-trip. Returns a records envelope.",
        input_schema=input_schema_for(EchoArgs),
        output_schema=records_schema(EchoRecord),
        func=echo_records,
        access="local",
    )


    def all_tools() -> tuple[OCTool, ...]:
        return (ECHO_RECORDS,)
    ```

=== "TypeScript"

    ```ts
    // src/my_tools.ts
    import * as z from "zod";
    import {
      OCTool,
      RecordsEnvelope,
      inputSchemaFor,
      recordsSchema,
    } from "@opscogs/octools";

    const EchoArgs = z.object({
      values: z.array(z.string()).describe("Strings to echo back, one record each."),
    });

    const EchoRecord = z
      .object({
        value: z.string().describe("The echoed string."),
        position: z.int().describe("Zero-based position in the input."),
      })
      .meta({ id: "EchoRecord" });

    function echoRecords(_dependency: unknown, args: unknown): RecordsEnvelope {
      const { values } = EchoArgs.parse(args);
      const records = values.map((value, position) => ({ value, position }));
      return RecordsEnvelope(EchoRecord).parse({
        records,
        count: records.length,
        truncated: false,
      });
    }

    export const ECHO_RECORDS = new OCTool({
      name: "echo_records",
      description:
        "Return each input string as one record with its position. Use it to check a tool round-trip. Returns a records envelope.",
      inputSchema: inputSchemaFor(EchoArgs),
      outputSchema: recordsSchema(EchoRecord),
      func: echoRecords,
      access: "local",
    });

    export function allTools(): readonly OCTool[] {
      return [ECHO_RECORDS];
    }
    ```

    `.meta({ id })` puts the record model in `$defs`, as pydantic does for
    a nested model, so both packages emit the same output schema. A parse
    returns the envelope's wire form, ready for `JSON.stringify`.

Assert conformance in your own test suite, not at import time:

=== "Python"

    ```python
    # tests/test_conformance.py
    from octools import validate_provider
    import my_tools


    def test_conformance():
        assert validate_provider(my_tools) == []
    ```

=== "TypeScript"

    ```ts
    // test/conformance.test.ts
    import { expect, test } from "vitest";
    import { validateProvider } from "@opscogs/octools";
    import * as myTools from "../src/my_tools.js";

    test("conformance", () => {
      expect(validateProvider(myTools)).toEqual([]);
    });
    ```

The converters then give a runtime the registration objects it needs:
`to_mcp_tool(ECHO_RECORDS)` and `to_anthropic_tool(ECHO_RECORDS,
name_prefix="demo_")` in Python, `toMcpTool(ECHO_RECORDS)` and
`toAnthropicTool(ECHO_RECORDS, { namePrefix: "demo_" })` in TypeScript;
see [Converters](./octools_converters.md).
