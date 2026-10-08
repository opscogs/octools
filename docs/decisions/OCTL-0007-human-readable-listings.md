---
status: accepted
version: 1.0.1
date: 2026-10-08
decision-makers: OpsCogs maintainers
---

# OCTL-0007 human-readable listings

## Context and Problem Statement

A provider's listing is a sequence of `OCTool` descriptors. The converters
turn it into the shapes a model or an MCP client reads, and
`validate_provider` checks it, but nothing turns it into something a person
reads: which tools a library ships, what each one does, whether it writes,
what inputs it takes. Every consumer that wants that view builds it from the
descriptor fields itself, and each one builds it slightly differently.

A client library can give the CLIs built on it a `tools list` command that
emits rows and a Markdown table, but a producer that is not built on such a
library has no listing at all, and a reviewer checking a library's tools has
no single command that works for every provider.

What does `octools` offer for reading a listing as a person, and how is a
provider named on a command line, without changing the descriptor or adding
a dependency?

## Decision Drivers

- `octools` depends on `pydantic` only; rendering uses the standard library.
- No descriptor field and no `SPEC_VERSION` change: the existing fields
  already carry everything a listing shows.
- One implementation of the row data and the table, so every consumer's
  listing agrees and a client library can delegate rather than duplicate.
- Any provider reachable by import can be listed, whether or not it is built
  on a client library.
- The addition fits the minor-release contract of
  [OCTL-0006](./OCTL-0006-tolerant-readers.md).

## Considered Options

- **A.** Data summaries, plain-text renderers and an `octools list` command
  in core.
- **B.** A rich, colored terminal renderer.
- **C.** Leave rendering to each consumer, for example a client library's
  own `tools list`.
- **D.** Display metadata fields on `OCTool`.

## Decision Outcome

Chosen option: **A, data summaries, plain-text renderers and an
`octools list` command in core**, because it gives every provider one
listing built from the fields the descriptor already has, with no new
dependency and no descriptor change.

### Summaries

```python
def summarize_tool(tool: OCTool) -> ToolSummary: ...
def summarize_provider(
    provider: ToolProvider, *, access: Access | None = None
) -> tuple[ToolSummary, ...]: ...
```

`ToolSummary` and `InputSummary` are frozen dataclasses derived from a
descriptor and nothing else:

- **`ToolSummary`** carries `name`, `title`, `summary`, `description`,
  `access`, `target`, `result_kind`, `read_only`, `destructive`,
  `idempotent`, `pages`, `deprecated`, `alias_of` and `inputs`. `pages` is
  true when the input schema's properties include `cursor`, the paging
  input convention of [OCTL-0002](./OCTL-0002-result-paging.md). `summary`
  is the
  description up to and including its first sentence end, by the same
  sentence rule the validator uses to count sentences, or the whole
  stripped description when it has no sentence end. `alias_of` is
  `meta[ALIAS_OF_KEY]` when it is a non-empty string.
- **`InputSummary`** carries `name`, `type`, `required` and `description`
  for each property of the input schema, in schema order. `type` is a short
  rendering of the property schema (`string`, `string|null`,
  `array[integer]`, a `$ref` target's last segment, `anyOf` and `oneOf`
  members joined with `|`, or `any`). A property with `enum` renders its
  values, `enum(a|b|c)`, whatever its `type`; when the joined values pass
  40 characters it shows the values that fit followed by `|...`. A
  property with `const` renders `const(<value>)`. A string value renders
  bare and any other value as JSON. Rendering never raises on an
  unexpected schema.
- **`ToolSummary.as_row()`** returns a flat, JSON-ready dict with the keys
  above in that order, `inputs` as a list of dicts. A consuming CLI that
  emits tool rows delegates its row building to it, so every listing shares
  one row shape.

`summarize_provider` keeps `all_tools()` order and, given `access`, keeps
only the tools with that access.

### Renderers

```python
ListingStyle = Literal["table", "md", "txt", "json"]


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

`LISTING_STYLES` holds the four styles in that order; an unknown style,
including the CLI alias `markdown`, raises `ValueError` naming them. The
style ids double as the command's output format ids: `table` for aligned
terminal columns, `md` for Markdown (the id matching the `.md` extension),
`txt` for plain text and `json`.
`pretty` applies to `json` only: indented when true, which is the
library default, and on one line with `(",", ":")` separators when false.
A rendering ends with a newline, except that an empty listing renders
`""` for `table` and `txt`; `md` then renders the header and divider,
and `json` renders `[]`.

- **`table`**: one padded line per tool, `name  access  mode  summary`,
  with no header. `mode` is `destructive`, `write` or `read` from the
  hints, and a deprecated tool is marked `[deprecated; use <alias_of>]`.
- **`md`**: a padded Markdown table of `name`, `access`, `mode`,
  `result_kind`, `pages`, `deprecated` and `summary`.
- **`txt`**: one block per tool with its title, the full wrapped
  description, access, target, result kind, hints (with `pages` when the
  tool pages), the deprecation note and the inputs as plain aligned
  columns, so a type such as `string|null` prints unescaped in a terminal.
- **`json`**: the `as_row()` list, indented or compact. This is the
  machine form.

`render_markdown_table` is the table every style and every consuming CLI
share: it renders booleans as `yes` / `no`, `None` or a missing key as an
empty cell, escapes `|` and flattens newlines inside a cell, and renders an
empty row list as the header and divider alone.

The `table`, `md` and `txt` styles are for people. Their layout,
column choice and wording may change in any release and are not a parse
target; a program reads the `json` style or calls `summarize_provider`
directly. The `json` keys follow the compatibility contract of every other
public name: keys may be added in a minor, and none is removed or changes
meaning within a major.

### The `octools list` command

```sh
octools list SPEC [--access ACCESS] [-o PATH|-] [--output-format FORMAT] [--pretty | --no-pretty]
python -m octools list SPEC
octools --version
```

The `octools` console script and `python -m octools` run the same command.
It renders `render_listing` for the provider named by `SPEC` and exits 0.

The command's option names, formats, exit codes and error output follow
these rules, implemented with the standard library only; a consuming CLI
that follows the same rules behaves the same way:

- **Options.** `--access ACCESS` (`local` or `remote`) filters the
  listing. `-o` / `--output-file PATH|-` writes the rendering to a file,
  as UTF-8 through a temporary file in the same directory and an atomic
  replace; `-` or no `-o` means stdout. A path whose directory is missing
  or not writable, or that names a directory, is a usage error from the
  option's own validator. `--output-format FORMAT` takes the four style
  ids, with `markdown` accepted as an alias for `md`; when it is omitted,
  an `-o` extension of `.md` or `.markdown`, `.json` or `.txt` picks the
  format, and anything else is `table`. An explicit value wins.
  `--pretty` / `--no-pretty` sets `json` indentation, defaulting to pretty
  only when stdout is a terminal, so a file or a pipe gets one line.
  `-v`, `-V` and `--version` print `octools <version>`.
- **Parser.** Neither parser accepts abbreviated option names, every value
  option shows a placeholder, and every help string is one sentence ending
  in a period.
- **Exit codes.** `0` success; `1` the listing could not be read or
  written; `2` a usage error; `130` interrupted.
- **Errors.** stdout is empty on failure. A usage error prints the
  command's usage and an `octools list: error: <message>` line; any other
  failure prints one `error: <message>` line to stderr. When the effective
  format is `json`, stderr instead ends with exactly one JSON object:
  `{"error": {"type", "exit_code", "message", "reason", "status_code", "details", "hint"}}`.
  `type` is `usage` (exit 2) or `api_failure` (exit 1); `reason`,
  `status_code` and `details` are `null`, and `hint` carries the fix when
  there is one.

The command registers no environment-file, extended-help, logging,
transport or paging options: `octools` reads no environment, makes no
network call, and depends on no client library.

`SPEC` is `package.module` or `package.module:attr`, where `attr` may be
dotted. The working directory is importable, as it is under
`python -m`. The command resolves it in this order:

1. Import the module. With no `attr`, the module itself is the target;
   otherwise the attribute path is looked up on it.
2. A target that satisfies `ToolProvider` is used as it is. This covers a
   module with a module-level `all_tools()` and a provider object.
3. Otherwise a callable target is called with no arguments, and its result
   must satisfy `ToolProvider`.
4. Anything else is an error.
5. The provider's `all_tools()` is called once, and every item must be an
   `OCTool`.

A module that does not import, a missing attribute, or a target that is
neither a provider nor callable is a usage error, exit 2: the SPEC is
wrong. A factory that raises or returns a non-provider, or an
`all_tools()` that raises or returns an item that is not an `OCTool`,
exits 1: the SPEC names code that failed. An `all_tools()` that raises
reads `'<SPEC>': all_tools raised <Type>: <message>`. A factory that
returns a sequence, as a SPEC naming a module-level `all_tools` function
does, is not a provider; its hint is
`name the module '<module>' to use its all_tools`, appended after a
semicolon on the text line. The module is the provider, so the command
accepts no second provider shape.

The command never constructs a client, reads configuration or passes
arguments. A provider that needs a live client or configuration to build its
listing is listed this way only through a zero-argument factory that builds
the listing without one.

### Consequences

- Good: any provider reachable by import is listable with one command,
  whether or not it is built on a client library.
- Good: a consuming CLI's own `tools list` shares one row shape and one
  table with `octools list`, and gains the `table` and `txt` styles by
  delegating.
- Good: no descriptor field, no `SPEC_VERSION` change and no new
  dependency.
- Bad: a provider that needs a client to build its listing needs a
  client-less zero-argument factory before `octools list` can show it.
- Bad: the human styles are deliberately unstable; a script that parses
  them breaks, and has to use the `json` style instead.
- Neutral: the listing shows only what the descriptor states, so a tool
  with a thin description reads as thinly as it is written.

### Confirmation

- The end-to-end example provider renders in every style, and its `json`
  rendering equals the `as_row()` list of `summarize_provider`.
- Tests pin the summary sentence rule, `pages`, each input type rendering
  including `enum` values and their 40-character cut, cell
  escaping in `render_markdown_table`, the `access` filter, and the
  `ValueError` for an unknown style.
- Tests drive the command through a module provider, a provider object, a
  zero-argument factory, and each error path, including an `all_tools()`
  that raises or returns a non-`OCTool`, asserting the exit code, the
  stderr line and the JSON error object.
- Tests pin format inference from the `-o` extension, the atomic file
  write, the TTY-dependent `--pretty` default, `--version`, exit 130, and
  a parser check that abbreviations are off and every option has a
  placeholder and a one-sentence help string.

## Pros and Cons of the Options

### A. Data summaries, plain-text renderers and `octools list` in core (chosen)

- Good: one row shape and one table for every consumer.
- Good: works for any provider reachable by import.
- Good: standard library only; the additions are functions and exports.
- Bad: plain text only, with no color or terminal width detection.

### B. A rich, colored terminal renderer

- Good: easier to scan in a terminal.
- Bad: it needs a rendering library, which breaks the rule that
  `octools` depends on `pydantic` only and would reach every library that
  depends on `octools`.

### C. Leave rendering to each consumer

- Good: nothing to add to `octools`.
- Bad: every consumer rebuilds the same rows and table, and the listings
  drift apart.
- Bad: a producer not built on a client library gets no listing at all.

### D. Display metadata fields on `OCTool`

- Good: a producer could tune how its tools are listed.
- Bad: it changes the descriptor for a presentation concern, which is
  scope the descriptor does not carry.
- Bad: the existing fields (title, description, access, hints, result
  kind, input schema, `ALIAS_OF_KEY` meta) already hold everything a listing
  shows.

## More Information

Additive under [OCTL-0006](./OCTL-0006-tolerant-readers.md): new functions,
dataclasses, a style literal and constant, and a command, with no descriptor
or envelope field, no vocabulary value, no validator rule and no converter
key, so listings need no `SPEC_VERSION` change of their own; octools
1.1.0 raises `SPEC_VERSION` to `"1.1"` for the paging fields in
[OCTL-0002](./OCTL-0002-result-paging.md). The package root's `__all__` gains
`InputSummary`, `LISTING_STYLES`, `ListingStyle`, `ToolSummary`,
`render_listing`, `render_markdown_table`, `summarize_provider` and
`summarize_tool`; the command's entry point is not a public name.

Ships in octools 1.1.0. A consumer that calls these names raises its floor
to `octools >= 1.1`.
