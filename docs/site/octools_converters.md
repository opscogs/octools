# Converters

Version: **1.4.0** · Date: 2026-11-09

The converters turn an `OCTool` into the registration object a target
expects, as plain data: dicts in Python, plain objects in TypeScript. No
SDK is imported, so a library can test its descriptors without depending
on `mcp` or `anthropic` (or `@modelcontextprotocol/sdk` and
`@anthropic-ai/sdk`). Lossless round-trip is the design goal; where a
target has no slot for a field the mapping says so here. Both packages
produce the same output for the same descriptor, key for key.

=== "Python"

    ```python
    from octools import to_anthropic_tool, to_mcp_tool
    from my_tools import ECHO_RECORDS

    mcp_tool = to_mcp_tool(ECHO_RECORDS, name_prefix="site_a_")
    anthropic_tool = to_anthropic_tool(ECHO_RECORDS, name_prefix="demo_")
    ```

=== "TypeScript"

    ```ts
    import { toAnthropicTool, toMcpTool } from "@opscogs/octools";
    import { ECHO_RECORDS } from "./my_tools.js";

    const mcpTool = toMcpTool(ECHO_RECORDS, { namePrefix: "site_a_" });
    const anthropicTool = toAnthropicTool(ECHO_RECORDS, { namePrefix: "demo_" });
    ```

The tables below name the Python descriptor fields; the TypeScript
`OCTool` has the same fields in camelCase (`input_schema` is
`inputSchema`, `read_only_hint` is `readOnlyHint`). The output keys are
identical in both. A prefixed name that breaks the target's pattern raises
`OCToolError` in both packages.

## Publishing behind a prefix: `prefix_tools(tools, name_prefix)`

TypeScript: `prefixTools(tools, namePrefix)`.

A provider publishes its tools under its namespace (`demo_get_rows`), and a
host that adds a prefix of its own does it once, before converting, with
`prefix_tools`. It returns renamed copies, each keeping its own `func`, so the
host registers and dispatches by the names the agent sees.

=== "Python"

    ```python
    from octools import prefix_tools, to_anthropic_tool, to_mcp_tool

    published = prefix_tools(merged.all_tools(), "acme_")
    mcp_tools = [to_mcp_tool(tool) for tool in published]
    anthropic_tools = [to_anthropic_tool(tool) for tool in published]
    handlers = {tool.name: tool.func for tool in published}
    ```

=== "TypeScript"

    ```ts
    import { prefixTools, toAnthropicTool, toMcpTool } from "@opscogs/octools";

    const published = prefixTools(merged.allTools(), "acme_");
    const mcpTools = published.map((tool) => toMcpTool(tool));
    const anthropicTools = published.map((tool) => toAnthropicTool(tool));
    ```

- The prefix is lowercased, and one without a trailing underscore gets one,
  so `"Acme"`, `"acme"` and `"acme_"` give the same names.
- A name that already starts with the prefix counts as published and is
  kept, so applying it twice changes nothing, and a host prefix equal to the
  provider's namespace is a no-op. Keep bare names free of your own
  namespace: `demo_mode_status` under `demo_` would be taken as published.
- An empty prefix renames nothing.
- `meta["alias_of"]` is prefixed the same way, so a deprecated alias still
  names its target.
- Each whole-word reference to a sibling in `description`, and in any
  `description` inside `input_schema` or `output_schema`, becomes the
  sibling's published name: "use `describe_table` for one table's columns"
  becomes "use `acme_describe_table` ...". For a sibling already published,
  its bare form counts as a reference too, so `get_rows` becomes
  `acme_get_rows` when the listing holds `acme_get_rows`. A word is a run of
  letters, digits and underscores, so an occurrence already prefixed, or part
  of a longer name, is left alone, as are words that name no sibling.
- A name with an underscore (`get_rows`) is rewritten wherever it stands as a
  word. A one-word name (`ping`, `status`) is rewritten only inside a code
  span, between single backticks, so "ping the server" stays as written and
  `` `ping` `` becomes `` `acme_ping` ``. Write a one-word sibling name in
  backticks.
- Only descriptions are rewritten: the tool's `description` and every
  `description` in its input and output schemas. Titles, schema `title`
  keywords, instance data (`const`, `default`, `enum`, `examples`), property
  names and `meta` values other than `alias_of` are not; rename a sibling
  named there yourself.
- A published name that breaks `NAME_RE` raises `OCToolError`, and so do two
  tools that would publish under one name (`get_rows` and `acme_get_rows`).

The published names are unique, and every whole-word sibling reference, bare
or prefixed, names a published tool.

Call it on the whole listing a host publishes, merged providers included, so
references between them are rewritten too. The converters' `name_prefix`
stays plain concatenation, for a wire name only.

## MCP: `to_mcp_tool(tool, *, name_prefix="")`

TypeScript: `toMcpTool(tool, { namePrefix })`.

Produces an MCP `Tool` object (specification 2025-11-25 and 2026-07-28;
the `Tool` object and its name rule are unchanged between them for the
fields this mapping uses). Everything but `func` survives, because
`func` is the server's handler rather than protocol data.

| `OCTool` field                              | MCP field                                              |
| ------------------------------------------- | ------------------------------------------------------ |
| `name`                                      | `name`, with `name_prefix` prepended; the result must match `MCP_NAME_RE` (`^[A-Za-z0-9_.-]{1,128}$`) or `OCToolError` is raised |
| `title`                                     | `title` (only when set)                                |
| `description`                               | `description`                                          |
| `input_schema`                              | `inputSchema` (verbatim copy)                          |
| `output_schema`                             | `outputSchema` (verbatim copy, only when set)          |
| `read_only_hint`                            | `annotations.readOnlyHint`                             |
| `destructive_hint`                          | `annotations.destructiveHint`                          |
| `idempotent_hint`                           | `annotations.idempotentHint`                           |
| `access`                                    | `_meta["com.opscogs.octools/access"]`                          |
| `target`                                    | `_meta["com.opscogs.octools/target"]` (only when set)          |
| `result_kind`                               | `_meta["com.opscogs.octools/result_kind"]`                     |
| `tags`                                      | `_meta["com.opscogs.octools/tags"]` (only when set)            |
| `deprecated`                                | `_meta["com.opscogs.octools/deprecated"]`                      |
| `meta`                                      | `_meta["com.opscogs.octools/meta"]` (copy)                     |
| `SPEC_VERSION`                              | `_meta["com.opscogs.octools/spec_version"]`                    |

`_meta` keys use the reverse-DNS prefix `com.opscogs.octools/` per the MCP
`_meta` convention, so they never collide with another vendor's keys. The
package label sits in the prefix because MCP allows only a single slash
per key, and other OpsCogs packages use their own `com.opscogs.<package>/`
prefix.
`openWorldHint` is not emitted: it has no clean OpsCogs meaning yet.
Schemas are deep copies, so a consumer can decorate the result without
touching the descriptor.

Example:

```json
{
  "name": "cluster_info",
  "title": "Cluster identity and versions",
  "description": "...",
  "inputSchema": { "type": "object", "properties": {}, "additionalProperties": false },
  "outputSchema": { "type": "object", "properties": {} },
  "annotations": { "readOnlyHint": true, "destructiveHint": false, "idempotentHint": true },
  "_meta": {
    "com.opscogs.octools/spec_version": "1.3",
    "com.opscogs.octools/access": "remote",
    "com.opscogs.octools/result_kind": "records",
    "com.opscogs.octools/deprecated": false,
    "com.opscogs.octools/meta": { "min_api_version": "2.10" },
    "com.opscogs.octools/target": "cluster"
  }
}
```

`name_prefix` (`namePrefix`) has the same meaning as on `to_anthropic_tool`: a server
that publishes one provider against two targets passes a different
prefix per target (`site_a_`, `site_b_`) so the names do not collide.
The prefix is not recorded in `_meta`, and descriptions are left as they
are. To keep sibling references and dispatch names in step with the
published names, call `prefix_tools` instead and convert its result with no
`name_prefix`.

The reverse mapping is mechanical, and the test suite proves it: an
`OCTool` rebuilt from `to_mcp_tool(tool)` plus the original `func`
compares equal to `tool`.

## Choosing a converter by id: `convert_tool(tool, format, *, name_prefix="")`

TypeScript: `convertTool(tool, format, { namePrefix })`.

`TOOL_FORMATS` lists the converter ids, `"mcp"` and `"anthropic"`. A
consumer that offers an export format takes its choices from `TOOL_FORMATS`
and calls `convert_tool`, so a new converter reaches it with no code change.
An unknown id raises `OCToolError`. These ids are separate from the listing
styles in `LISTING_STYLES`.

## Anthropic: `to_anthropic_tool(tool, *, name_prefix="")`

TypeScript: `toAnthropicTool(tool, { namePrefix })`.

Produces a Messages API `tools[]` entry with exactly three keys.

| `OCTool` field | Anthropic field                                                                                                                   |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `name`         | `name`, with `name_prefix` prepended; the result must match `ANTHROPIC_NAME_RE` (`^[a-zA-Z0-9_-]{1,128}$`) or `OCToolError` is raised |
| `description`  | `description`                                                                                                                     |
| `input_schema` | `input_schema`, with every `title` and `x-` key stripped at schema level and `additionalProperties: false` added to the root if missing |

A descriptor name, provider namespace included, stops at 48 characters, so
an agent host's own routing prefix still fits under the tightest common
limit, 64. Property names are never altered, even one literally called
`title`.

Dropped, because the API has no slot for them: `title`, `output_schema`,
the three hints, `access` and `target`, `result_kind`, `deprecated`,
`meta`, `tags`, and `func`. A host filters with `select_tools` before
converting, and a runtime keeps those in its own registry, which is
where approval policy, result rendering and deprecation warnings already
read them. `strict` is not emitted either: turning strict mode on is a
runtime decision, and a strict-clean input schema is what makes it
possible.

```json
{
  "name": "demo_cluster_info",
  "description": "...",
  "input_schema": { "type": "object", "properties": {}, "additionalProperties": false }
}
```

## Other targets

OpenAI function tools want every property in `required` and optionals
as `type: ["string", "null"]`; pydantic-ai and LangChain accept the
2020-12 schema as is. Those transforms are consumer-side, not this
package's; `input_schema` is the stable input to all of them.
