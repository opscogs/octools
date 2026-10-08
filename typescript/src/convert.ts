/**
 * Plain-object converters from `OCTool` to vendor tool shapes.
 *
 * No SDK is imported: each converter returns the JSON object the target
 * expects, built from plain objects, so a library can test its descriptors
 * without depending on an SDK. The MCP mapping is lossless (everything but
 * `func` survives, OpsCogs fields under a namespaced `_meta`); the
 * Anthropic mapping is lossy by necessity and documents what it drops.
 *
 * @module
 */
import type { OCTool } from "./descriptor.js";
import { OCToolError } from "./errors.js";
import type { JsonSchema } from "./internal/jsonSchema.js";
import { stripKeys } from "./schema.js";
import {
  ANTHROPIC_NAME_RE,
  MCP_META_NAMESPACE,
  MCP_NAME_RE,
  SPEC_VERSION,
} from "./vocabulary.js";

/** Options both converters take. */
export interface ConvertOptions {
  /** Prepended to the tool's name; the result must fit the target's rule. */
  readonly namePrefix?: string | undefined;
}

/** Return `value` as plain JSON-compatible objects and arrays (a deep copy). */
function plainCopy(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(plainCopy);
  }
  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(
      Object.entries(value).map(([key, sub]) => [key, plainCopy(sub)]),
    );
  }
  return value;
}

function plainObject(value: Readonly<Record<string, unknown>>): JsonSchema {
  return plainCopy(value) as JsonSchema;
}

/** Return `namePrefix` plus the tool's name, or throw if it breaks `rule`. */
function prefixedName(
  tool: OCTool,
  options: ConvertOptions,
  rule: RegExp,
): string {
  const name = `${options.namePrefix ?? ""}${tool.name}`;
  if (!rule.test(name)) {
    throw new OCToolError(
      `tool name ${JSON.stringify(name)} does not match ${rule.source}`,
    );
  }
  return name;
}

/**
 * Return `tool` as an MCP `Tool` object (specs 2025-11-25 and 2026-07-28).
 *
 * `name` has `namePrefix` prepended, checked against {@link MCP_NAME_RE},
 * so one provider can reach two targets on one server. `inputSchema` and
 * `outputSchema` are the descriptor's schemas verbatim; the three hints
 * become `annotations`; `access`, `target`, `result_kind`, `deprecated` and
 * the `meta` bag go under `_meta` with the `com.opscogs.octools/` prefix,
 * beside the spec version. Only `func` is not represented (it is the
 * server's handler). `title`, `outputSchema` and `target` are present only
 * when set. Throws {@link OCToolError} when the prefixed name breaks the
 * rule.
 */
export function toMcpTool(
  tool: OCTool,
  options: ConvertOptions = {},
): Record<string, unknown> {
  const out: Record<string, unknown> = {
    name: prefixedName(tool, options, MCP_NAME_RE),
  };
  if (tool.title !== null) {
    out["title"] = tool.title;
  }
  out["description"] = tool.description;
  out["inputSchema"] = plainObject(tool.inputSchema);
  if (tool.outputSchema !== null) {
    out["outputSchema"] = plainObject(tool.outputSchema);
  }
  out["annotations"] = {
    readOnlyHint: tool.readOnlyHint,
    destructiveHint: tool.destructiveHint,
    idempotentHint: tool.idempotentHint,
  };
  const meta: Record<string, unknown> = {
    [`${MCP_META_NAMESPACE}spec_version`]: SPEC_VERSION,
    [`${MCP_META_NAMESPACE}access`]: tool.access,
    [`${MCP_META_NAMESPACE}result_kind`]: tool.resultKind,
    [`${MCP_META_NAMESPACE}deprecated`]: tool.deprecated,
    [`${MCP_META_NAMESPACE}meta`]: plainObject(tool.meta),
  };
  if (tool.target !== null) {
    meta[`${MCP_META_NAMESPACE}target`] = tool.target;
  }
  out["_meta"] = meta;
  return out;
}

/**
 * Return `tool` as an Anthropic Messages API `tools[]` entry.
 *
 * The entry carries `name` (with `namePrefix` prepended, checked against
 * {@link ANTHROPIC_NAME_RE}), `description` and `input_schema`. The schema
 * is the descriptor's with every `title` and `x-` key stripped and
 * `additionalProperties: false` on the root unless it sets its own, so the
 * runtime can set `strict: true` itself. Dropped, because the API has no
 * slot for them: `title`, `outputSchema`, the hints, `access` / `target`,
 * `resultKind`, `deprecated` and `meta` (the runtime's registry keeps
 * those). `strict` is not emitted; it is a runtime choice. Throws
 * {@link OCToolError} when the prefixed name breaks the rule.
 */
export function toAnthropicTool(
  tool: OCTool,
  options: ConvertOptions = {},
): Record<string, unknown> {
  const name = prefixedName(tool, options, ANTHROPIC_NAME_RE);
  const schema = stripKeys(tool.inputSchema, {
    keys: ["title"],
    prefixes: ["x-"],
  });
  if (!Object.hasOwn(schema, "additionalProperties")) {
    schema["additionalProperties"] = false;
  }
  return { name, description: tool.description, input_schema: schema };
}
