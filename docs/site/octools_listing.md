# Listing tools for people

Version: **1.2.0** · Date: 2026-10-08

The listing helpers turn a provider's tools into a listing a person can
read: a terminal command (`octools list`) for anyone with the Python
package installed, and a small library API (`summarize_provider` and
`render_listing` in Python, `summarizeProvider` and `renderListing` in
TypeScript) for a library that wants the same listing inside its own CLI.
Both packages render the same text, byte for byte. Nothing here changes
the descriptor or the envelopes; it only reads them.

The Python package ships a demo provider, `octools.example`, so
`octools list octools.example` works wherever the package is installed: a
smoke test that the command runs, and a small conformant provider to read.
Its tools may change in any release, and it is not part of the public API.

## The `octools list` command

The command ships with the Python package. The TypeScript package has no
command of its own; a TypeScript CLI renders the same listing through
`renderListing` (see
[Wiring `render_listing` into your own CLI](#wiring-render_listing-into-your-own-cli)).

```sh
octools list SPEC [--access ACCESS] [-o PATH|-] [--output-format FORMAT] [--pretty | --no-pretty]
python -m octools list SPEC [...]
octools --version
```

| Option                     | Meaning                                                                                                                                      |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `SPEC`                     | The provider to list: a module, a `module:attr` object or a zero-argument factory.                                                           |
| `--access ACCESS`          | Only list tools with this access, `local` or `remote`; omitted lists every tool.                                                             |
| `-o`, `--output-file PATH\|-` | Write the listing to `PATH` instead of stdout; `-` or omitted means stdout. The file is written as UTF-8 and replaced atomically.            |
| `--output-format FORMAT`   | `table`, `md` (`markdown` is accepted as an alias), `txt` or `json`. Omitted, it follows the `-o` extension, else `table`.                   |
| `--pretty`, `--no-pretty`  | Indent `json` output or print it on one line. The default is indented when stdout is a terminal and compact when it is piped or `-o` is set. |
| `-v`, `-V`, `--version`    | Print `octools <version>` and exit `0`.                                                                                                      |

With `-o` and no `--output-format`, the extension picks the format:
`.md` and `.markdown` write `md`, `.json` writes `json`, `.txt` writes
`txt`, and any other extension writes `table`. An explicit
`--output-format` always wins. An `-o` whose directory does not exist or
is not writable, or that names a directory, is a usage error before
anything is listed. Option names are never abbreviated: `--output` is an
unknown option, not a short form of `--output-file`.

`SPEC` names the provider to list, as `package.module` or
`package.module:attr` (`attr` may itself be dotted, `a.b`). The working
directory is importable, as it is under `python -m`, so a local module
lists without installing it. Resolution:

1. Import the module.
2. With no `:attr`, the module itself is the candidate target; with
   `:attr`, resolve that attribute on it.
3. A target that already satisfies `ToolProvider` (it has an `all_tools`
   method) is used as-is.
4. Otherwise, a callable target is called with no arguments, and its
   return value must satisfy `ToolProvider`.
5. Anything else is an error.
6. The provider's `all_tools()` is called once, and every item it returns
   must be an `OCTool`.

### Exit codes and errors

| Code  | Meaning                                                                                                                                   |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `0`   | The listing was printed or written.                                                                                                       |
| `1`   | The listing could not be read or written: a factory raised or returned a non-provider, `all_tools()` raised or returned a non-`OCTool`, or the output file could not be written. |
| `2`   | Usage error: an unknown option or value, an unusable `-o` path, or a `SPEC` whose module does not import, whose attribute is missing, or that names neither a provider nor a callable. |
| `130` | Interrupted.                                                                                                                              |

stdout carries the listing or nothing: on any failure it is empty. A
usage error prints the command's usage and one
`octools list: error: <message>` line to stderr; any other failure prints
one `error: <message>` line:

```text
$ octools list no_such_tools
usage: octools list [-h] [--access ACCESS] [-o PATH|-]
                    [--output-format FORMAT] [--pretty | --no-pretty]
                    SPEC
octools list: error: cannot import 'no_such_tools': No module named 'no_such_tools'
```

An `all_tools()` that raises reads
`'<SPEC>': all_tools raised <Type>: <message>`. A SPEC that names a
module-level `all_tools` function is called as a factory, and the tuple it
returns is not a provider; the error names the fix:

```text
$ octools list octools.example:all_tools
error: 'octools.example:all_tools': factory returned tuple, not a tool provider; name the module 'octools.example' to use its all_tools
```

When the output format is `json`, given or inferred from `-o`, stderr
instead ends with exactly one JSON object on one line. `type` is `usage`
for exit `2` and `api_failure` for exit `1`; `reason`, `status_code` and
`details` are always `null`, and `hint` carries the fix when there is one:

```text
$ octools list octools.example:all_tools --output-format json
{"error": {"type": "api_failure", "exit_code": 1, "message": "'octools.example:all_tools': factory returned tuple, not a tool provider", "reason": null, "status_code": null, "details": null, "hint": "name the module 'octools.example' to use its all_tools"}}
```

The machine contract is `--output-format json`: the listing on stdout,
and nothing else there. Pipe it straight into `jq`:

```sh
octools list SPEC --output-format json | jq '.[].name'
```

### Providers that need a client

A provider reachable as a module with a module-level `all_tools()`
works directly. A provider whose tools need a live client or
configuration to construct needs a client-less, zero-argument factory
function to be listed this way - one that builds the tools without
reaching a real system, for example by passing `None` as the injected
dependency.

## Formats

`table`, `md` and `txt` are for a person reading a terminal or a chat
reply. `json` is the machine-readable form, for a script or another tool
to parse: a plain list of dicts, one per tool, in the same key order every
time.

The examples below list the demo provider, `octools.example`, with four
tools: `echo_records` (reads input back as records, one page at a
time), `echo` (its deprecated alias), `block_sizes` (address block sizes)
and `render_badge` (writes a badge image through an injected sink).

### `table`

One line per tool, columns padded to width with a two-space gutter, no
header. `mode` is `destructive` when the tool's destructive hint is set,
`write` when it is not read-only, otherwise `read`. A deprecated tool
appends `[deprecated; use <alias_of>]`, or `[deprecated]` when it names no
replacement.

```text
$ octools list octools.example
echo_records  local  read  Return each input string as one record with its position.
echo          local  read  Deprecated alias of echo_records kept for one major version. [deprecated; use echo_records]
block_sizes   local  read  Return each CIDR prefix normalized, with its length and address count.
render_badge  local  read  Render a two-part SVG badge and write it through the injected sink.
```

### `md`

A GitHub-flavored Markdown table over the same rows, with columns `name`,
`access`, `mode`, `result_kind`, `pages`, `deprecated`, `summary`. `pages`
is `yes` when the tool takes a `cursor` input, the paging convention in
[Descriptor and envelopes](./octools_descriptor.md).

```text
$ octools list octools.example --output-format md
| name         | access | mode | result_kind | pages | deprecated | summary                                                                |
| ------------ | ------ | ---- | ----------- | ----- | ---------- | ---------------------------------------------------------------------- |
| echo_records | local  | read | records     | yes   | no         | Return each input string as one record with its position.              |
| echo         | local  | read | records     | yes   | yes        | Deprecated alias of echo_records kept for one major version.           |
| block_sizes  | local  | read | records     | no    | no         | Return each CIDR prefix normalized, with its length and address count. |
| render_badge | local  | read | artifact    | no    | no         | Render a two-part SVG badge and write it through the injected sink.    |
```

`-o tools.md` writes the same table to `tools.md`.

### `txt`

One block per tool, blocks separated by a blank line: the name (and
`- <title>` when the tool has one), the full description wrapped at 88
columns, an `access` / `target` / `result` line, a `hints` line (ending
in `pages` when the tool takes a `cursor` input), a `deprecated` line
when the tool is deprecated, and the tool's inputs as plain aligned
columns of `name`, `type`, `required` and `description` (or
`inputs: none`). The columns are text for a terminal, not Markdown, so a
type such as `string|null` prints as is. The first two blocks:

```text
$ octools list octools.example --output-format txt --access local
echo_records - Echo strings as records
  Return each input string as one record with its position. Use it to check that a tool
  round-trip works before calling anything real. Returns a records envelope; when limit
  cut the list, truncated is true and next_cursor fetches the next page.
  access: local  target: -  result: records
  hints: read-only, idempotent, pages
  inputs:
    name    type           required  description
    values  array[string]  yes       Strings to echo back, one record each.
    limit   integer        no        Maximum records to return, 1 to 100; the tool enforces it.
    cursor  string|null    no        next_cursor from a previous page; omit for the first page.

echo
  Deprecated alias of echo_records kept for one major version. Call echo_records
  instead.
  access: local  target: -  result: records
  hints: read-only, idempotent, pages
  deprecated: use echo_records
  inputs:
    name    type           required  description
    values  array[string]  yes       Strings to echo back, one record each.
    limit   integer        no        Maximum records to return, 1 to 100; the tool enforces it.
    cursor  string|null    no        next_cursor from a previous page; omit for the first page.
...
```

### `json`

`json.dumps([summary.as_row() for summary in summaries], indent=2)` with
`--pretty` (the default on a terminal), or on one line with
`separators=(",", ":")` otherwise; one flat dict per tool (the first shown
here):

```text
$ octools list octools.example --output-format json --pretty
[
  {
    "name": "echo_records",
    "title": "Echo strings as records",
    "summary": "Return each input string as one record with its position.",
    "description": "Return each input string as one record with its position. Use it to check that a tool round-trip works before calling anything real. Returns a records envelope; when limit cut the list, truncated is true and next_cursor fetches the next page.",
    "access": "local",
    "target": null,
    "result_kind": "records",
    "read_only": true,
    "destructive": false,
    "idempotent": true,
    "pages": true,
    "deprecated": false,
    "alias_of": null,
    "inputs": [
      {
        "name": "values",
        "type": "array[string]",
        "required": true,
        "description": "Strings to echo back, one record each."
      },
      {
        "name": "limit",
        "type": "integer",
        "required": false,
        "description": "Maximum records to return, 1 to 100; the tool enforces it."
      },
      {
        "name": "cursor",
        "type": "string|null",
        "required": false,
        "description": "next_cursor from a previous page; omit for the first page."
      }
    ]
  },
  ...
]
```

## Library API

Both packages export the pieces above so a producer's own CLI can render
the same listing without shelling out to `octools list`. The TypeScript
names are camelCase: `summarizeTool`, `summarizeProvider`,
`renderMarkdownTable`, `renderListing`.

### `ToolSummary` and `InputSummary`

`summarize_tool(tool)` returns a `ToolSummary`: `name`, `title`,
`summary` (the first sentence of `description`, or the whole description
when no sentence boundary is found), `description`, `access`, `target`,
`result_kind`, `read_only`, `destructive`, `idempotent`, `pages` (true
when the input schema's properties include `cursor`), `deprecated`,
`alias_of` (the tool's `meta["alias_of"]` when it is a non-empty string,
else `None`), and `inputs`, a tuple of `InputSummary`. In TypeScript the
`ToolSummary` properties are camelCase (`resultKind`, `readOnly`,
`aliasOf`) and `inputs` is a readonly array.

Each `InputSummary` describes one property of the tool's input schema:
`name`, `type` (rendered from the property's JSON Schema, see below),
`required`, and `description` (the property's own `description` when it
is a string, else `None`). Inputs are read in the schema's own property
order.

`ToolSummary.as_row()` (`asRow()`) returns a flat, JSON-ready dict in a
fixed key
order - `name`, `title`, `summary`, `description`, `access`, `target`,
`result_kind`, `read_only`, `destructive`, `idempotent`, `pages`,
`deprecated`, `alias_of`, `inputs` (each input as a dict of `name`,
`type`, `required`, `description`) - the shape the `json` format
serializes. The row keys are the same snake_case keys in both packages.

Type rendering never raises, for any input mapping:

| Property shape                          | Rendered type                        |
| ---------------------------------------- | ------------------------------------- |
| `"type": "string"`                       | `string`                              |
| `"type"` is a list                       | member types joined with `\|` (`string\|null`) |
| `"type": "array"` with `"items"`         | `array[<items type>]`                 |
| `"enum"` present, with or without `"type"` | `enum(a\|b\|c)`; past 40 characters, the values that fit then `\|...` |
| `"const"`                                | `const(<value>)`                      |
| `"$ref"`                                 | the last path segment (`#/$defs/Mode` -> `Mode`) |
| `"anyOf"` or `"oneOf"`                   | member types joined with `\|` (`enum(a\|b)\|null`) |
| anything else                            | `any`                                 |

`enum` and `const` take precedence over the other keys, since their values
are what a reader needs. A string value renders bare and any other value
as JSON (`enum(null|true|1.5)`).

### `summarize_provider`

=== "Python"

    ```python
    def summarize_provider(
        provider: ToolProvider, *, access: Access | None = None
    ) -> tuple[ToolSummary, ...]: ...
    ```

=== "TypeScript"

    ```ts
    function summarizeProvider(
      provider: ListedToolProvider,
      options?: SummarizeOptions, // { access? }
    ): ToolSummary[];
    ```

Summarizes every tool `provider.all_tools()` returns, in that order,
filtered to `access` ("local" or "remote") when given.

### `render_markdown_table` and `render_listing`

=== "Python"

    ```python
    def render_markdown_table(
        rows: Sequence[Mapping[str, object]], columns: Sequence[str]
    ) -> str: ...
    def render_listing(
        provider: ToolProvider,
        *,
        style: ListingStyle = "table",
        access: Access | None = None,
        pretty: bool = True,
    ) -> str: ...
    ```

=== "TypeScript"

    ```ts
    function renderMarkdownTable(
      rows: readonly Readonly<Record<string, unknown>>[],
      columns: readonly string[],
    ): string;
    function renderListing(
      provider: ListedToolProvider,
      options?: RenderListingOptions, // { style?, access?, pretty? }
    ): string;
    ```

    `ListedToolProvider` is any object whose `allTools()` lists tools;
    every `ToolProvider` is one.

`render_markdown_table` pads a GitHub-flavored table over any rows and
column names: a `bool` cell renders as `yes` / `no`, `None` or a missing
key as an empty cell, anything else via `str()`; a literal `|` in a cell
is escaped as `\|` and a newline becomes a space. With no rows it renders
the header and divider only. The result always ends with a newline.

`render_listing` is the one call behind the `octools list` command:
given a provider and a style (one of the formats above), it summarizes
and renders in one step. An unknown style raises `ValueError` (a
`RangeError` in TypeScript) naming the valid ones, `LISTING_STYLES` (`"table"`, `"md"`, `"txt"`, `"json"`, also
exported as the `ListingStyle` literal); `markdown` is a CLI alias only.
`pretty` applies to `json` alone: indented when true (the default),
compact on one line when false. The result ends with a newline, except
that an empty listing renders as an empty string for `table` and `txt`;
`md` then renders the header and divider only, and `json` renders
`[]\n`.

## Wiring `render_listing` into your own CLI

A library that already ships a CLI can add its own `tools list` command
by delegating straight to `render_listing` (`renderListing`), instead of
building rows by hand:

=== "Python"

    ```python
    import argparse

    from octools import LISTING_STYLES, render_listing
    from octools import example as my_tools


    def cmd_tools_list(args: argparse.Namespace) -> None:
        text = render_listing(my_tools, style=args.output_format, access=args.access)
        print(text, end="")


    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command")
    tools_list = subcommands.add_parser("tools-list")
    tools_list.add_argument(
        "--output-format",
        metavar="FORMAT",
        choices=LISTING_STYLES,
        default="table",
        help="Render the listing in this format.",
    )
    tools_list.add_argument(
        "--access",
        metavar="ACCESS",
        choices=["local", "remote"],
        help="Only list tools with this access.",
    )
    tools_list.set_defaults(func=cmd_tools_list)
    ```

=== "TypeScript"

    ```ts
    import { parseArgs } from "node:util";

    import {
      ACCESS_KINDS,
      LISTING_STYLES,
      type Access,
      type ListingStyle,
      renderListing,
    } from "@opscogs/octools";
    import * as myTools from "./my_tools.js";

    function oneOf<T extends string>(
      value: string | undefined,
      allowed: readonly T[],
      option: string,
    ): T | undefined {
      if (value !== undefined && !(allowed as readonly string[]).includes(value)) {
        throw new RangeError(`${option} must be one of ${allowed.join(", ")}`);
      }
      return value as T | undefined;
    }

    export function cmdToolsList(args: string[]): void {
      const { values } = parseArgs({
        args,
        options: {
          "output-format": { type: "string", default: "table" },
          access: { type: "string" },
        },
      });
      const style: ListingStyle | undefined = oneOf(
        values["output-format"],
        LISTING_STYLES,
        "--output-format",
      );
      const access: Access | undefined = oneOf(
        values.access,
        ACCESS_KINDS,
        "--access",
      );
      process.stdout.write(renderListing(myTools, { style, access }));
    }
    ```

Every producer's `tools list` command then supports the same four formats
with no per-library formatting code, and stays in sync with the
descriptor whenever a tool's description, hints or inputs change.
