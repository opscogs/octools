# Converters

Version: **1.2.0** · Date: 2026-10-08

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
    "com.opscogs.octools/spec_version": "1.1",
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
The prefix is not recorded in `_meta`; the server that added it strips
it before dispatching to `func`.

The reverse mapping is mechanical, and the test suite proves it: an
`OCTool` rebuilt from `to_mcp_tool(tool)` plus the original `func`
compares equal to `tool`.

## Anthropic: `to_anthropic_tool(tool, *, name_prefix="")`

TypeScript: `toAnthropicTool(tool, { namePrefix })`.

Produces a Messages API `tools[]` entry with exactly three keys.

| `OCTool` field | Anthropic field                                                                                                                   |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `name`         | `name`, with `name_prefix` prepended; the result must match `ANTHROPIC_NAME_RE` (`^[a-zA-Z0-9_-]{1,128}$`) or `OCToolError` is raised |
| `description`  | `description`                                                                                                                     |
| `input_schema` | `input_schema`, with every `title` and `x-` key stripped at schema level and `additionalProperties: false` added to the root if missing |

The runtime supplies the namespace prefix (`demo_`, for example), which
is why descriptor names stop at 48 characters. Property names are never
altered, even one literally called `title`.

Dropped, because the API has no slot for them: `title`, `output_schema`,
the three hints, `access` and `target`, `result_kind`, `deprecated`,
`meta`, and `func`. A runtime keeps those in its own registry, which is
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
