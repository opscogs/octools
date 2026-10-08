/**
 * JSON Schema 2020-12 helpers for `input_schema` and `output_schema`.
 *
 * Schemas are generated from zod schemas, never hand-written. This module
 * suppresses `title` noise, closes model objects for input schemas, passes
 * `x-` extension keys (such as `x-sensitivity`, set with `.meta()`) through
 * untouched, and checks a schema against the strict-mode keyword subset
 * that both Anthropic and OpenAI accept. The checker reports findings; it
 * never mutates the schema it is given.
 *
 * @module
 */
import type * as z from "zod";

import { Finding } from "./findings.js";
import { type JsonSchema, zodJsonSchema } from "./internal/jsonSchema.js";
import { STRICT_FORMATS, STRICT_KEYWORDS, STRICT_TYPES } from "./vocabulary.js";

/** Which side of a zod schema to describe: what a parse accepts or returns. */
export type SchemaIO = "input" | "output";

/** Options for {@link schemaFor}. */
export interface SchemaForOptions {
  /**
   * `input` (the default) describes what a parse accepts, `output` what it
   * returns. The input side is the wire shape: zod's output side marks
   * every defaulted field required, closes every object and cannot
   * represent a transform.
   */
  readonly io?: SchemaIO;
}

/** Options for {@link stripKeys}. */
export interface StripKeysOptions {
  /** Keywords removed exactly. */
  readonly keys?: Iterable<string>;
  /** Every keyword starting with one of these is removed. */
  readonly prefixes?: Iterable<string>;
}

const SCHEMA_MAPS: ReadonlySet<string> = new Set([
  "$defs",
  "dependentSchemas",
  "patternProperties",
  "properties",
]);
const SCHEMA_LISTS: ReadonlySet<string> = new Set([
  "allOf",
  "anyOf",
  "oneOf",
  "prefixItems",
]);
const DATA_KEYWORDS: ReadonlySet<string> = new Set([
  "const",
  "default",
  "enum",
  "examples",
]);
const DEFS_PREFIX = "#/$defs/";

type NodeFn = (node: JsonSchema) => JsonSchema;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Render `value` for a finding message, Python-style. */
function repr(value: unknown): string {
  if (typeof value === "string") return `'${value}'`;
  if (value === true) return "True";
  if (value === false) return "False";
  if (value === null) return "None";
  return JSON.stringify(value);
}

/**
 * Return a plain-data copy of `node` with `fn` applied to every subschema.
 *
 * Keys under `properties` / `$defs` are names, not keywords; values of
 * `default` / `const` / `enum` / `examples` and `x-` keys are data, so
 * neither is treated as a schema.
 */
function mapSchema(node: unknown, fn: NodeFn): unknown {
  if (!isObject(node)) {
    return structuredClone(node);
  }
  const out: JsonSchema = {};
  for (const [key, value] of Object.entries(node)) {
    if (SCHEMA_MAPS.has(key) && isObject(value)) {
      out[key] = Object.fromEntries(
        Object.entries(value).map(([name, sub]) => [name, mapSchema(sub, fn)]),
      );
    } else if (SCHEMA_LISTS.has(key) && Array.isArray(value)) {
      out[key] = value.map((sub: unknown) => mapSchema(sub, fn));
    } else if (DATA_KEYWORDS.has(key) || key.startsWith("x-")) {
      out[key] = structuredClone(value);
    } else if (isObject(value)) {
      out[key] = mapSchema(value, fn);
    } else {
      out[key] = structuredClone(value);
    }
  }
  return fn(out);
}

/**
 * Return a copy of `schema` without the named keywords at any schema level.
 *
 * `keys` are removed exactly; `prefixes` remove every keyword that starts
 * with one of them (`["x-"]` drops all extension keys). Property names are
 * never touched, even when they collide with a removed keyword.
 */
export function stripKeys(
  schema: JsonSchema,
  options: StripKeysOptions = {},
): JsonSchema {
  const drop: ReadonlySet<string> = new Set(options.keys ?? []);
  const starts = [...(options.prefixes ?? [])];
  const clean: NodeFn = (node) =>
    Object.fromEntries(
      Object.entries(node).filter(
        ([key]) =>
          !drop.has(key) && !starts.some((prefix) => key.startsWith(prefix)),
      ),
    );
  return mapSchema(schema, clean) as JsonSchema;
}

/** Return a copy of `schema` with every `title` keyword removed. */
export function stripTitles(schema: JsonSchema): JsonSchema {
  return stripKeys(schema, { keys: ["title"] });
}

/**
 * Return a copy with `additionalProperties: false` on every model object.
 *
 * Only objects that declare `properties` are closed; a free-form record
 * (an object with no `properties`) is left alone so its meaning is not
 * silently changed, and {@link strictClean} reports it.
 */
export function closeObjects(schema: JsonSchema): JsonSchema {
  const close: NodeFn = (node) =>
    "properties" in node && !("additionalProperties" in node)
      ? { ...node, additionalProperties: false }
      : node;
  return mapSchema(schema, close) as JsonSchema;
}

/**
 * Return the 2020-12 JSON Schema of `schema` with no `title` keywords.
 *
 * The root carries no `$schema` (a tool's schema is embedded; the dialect
 * is `SCHEMA_DIALECT`). A schema given an `id` with `.meta()` lands in
 * `$defs` and is referenced by `$ref`; `.meta()` keys such as
 * `x-sensitivity` pass through unchanged.
 */
export function schemaFor(
  schema: z.ZodType,
  options: SchemaForOptions = {},
): JsonSchema {
  return stripTitles(zodJsonSchema(schema, options.io ?? "input"));
}

/**
 * Return `schema`'s JSON Schema shaped for `OCTool.input_schema`.
 *
 * The input side (what the model sends), no titles, and every model
 * object closed with `additionalProperties: false`.
 */
export function inputSchemaFor(schema: z.ZodType): JsonSchema {
  return closeObjects(schemaFor(schema));
}

/**
 * Return `schema`'s JSON Schema shaped for `OCTool.output_schema`.
 *
 * The wire shape a parse accepts, which is what the tool returns once its
 * result is parsed, and no titles. Output schemas are unconstrained
 * 2020-12: nothing sends them to a grammar compiler, so extension keys and
 * bounds are fine here. A `z.object` stays open and a `z.strictObject` is
 * closed, as in the schema given.
 */
export function outputSchemaFor(schema: z.ZodType): JsonSchema {
  return schemaFor(schema);
}

/** Return every internal `$defs` name referenced anywhere under `node`. */
function collectRefs(node: unknown, refs = new Set<string>()): Set<string> {
  if (Array.isArray(node)) {
    for (const item of node) collectRefs(item, refs);
  } else if (isObject(node)) {
    for (const [key, value] of Object.entries(node)) {
      if (
        key === "$ref" &&
        typeof value === "string" &&
        value.startsWith(DEFS_PREFIX)
      ) {
        refs.add(value.slice(DEFS_PREFIX.length));
      } else if (!DATA_KEYWORDS.has(key)) {
        collectRefs(value, refs);
      }
    }
  }
  return refs;
}

/** Return the `$defs` names that can reach themselves through `$ref`. */
function recursiveDefs(defs: JsonSchema): string[] {
  const neighbors = (name: string): string[] =>
    [...collectRefs(defs[name])].filter((ref) => Object.hasOwn(defs, ref));
  const recursive: string[] = [];
  for (const start of Object.keys(defs)) {
    const seen = new Set<string>();
    const stack = neighbors(start);
    for (
      let current = stack.pop();
      current !== undefined;
      current = stack.pop()
    ) {
      if (current === start) {
        recursive.push(start);
        break;
      }
      if (!seen.has(current)) {
        seen.add(current);
        stack.push(...neighbors(current));
      }
    }
  }
  return recursive;
}

function isPrimitive(value: unknown): boolean {
  return (
    value === null ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  );
}

/** Walk one schema and collect strict-mode findings. */
class StrictChecker {
  readonly findings: Finding[] = [];

  constructor(private readonly defs: JsonSchema) {}

  add(rule: string, message: string, path: string): void {
    this.findings.push(new Finding({ rule, message, path }));
  }

  check(node: unknown, path: string, root = false): void {
    if (!isObject(node)) {
      this.add(
        "boolean_schema",
        `boolean schema ${repr(node)} is not allowed`,
        path,
      );
      return;
    }
    for (const [key, value] of Object.entries(node)) {
      this.checkKeyword(key, value, path);
    }
    if ("$defs" in node && !root) {
      this.add("defs_not_at_root", "$defs must live at the schema root", path);
    }
    this.checkObject(node, path);
    this.checkRefs(node, path);
    this.recurse(node, path);
  }

  checkKeyword(key: string, value: unknown, path: string): void {
    if (key === "title") {
      this.add("title_present", "title is schema noise; strip it", path);
    } else if (key.startsWith("x-")) {
      this.add(
        "extension_key",
        `extension key ${repr(key)} belongs on output schemas only`,
        path,
      );
    } else if (!STRICT_KEYWORDS.has(key)) {
      this.add(
        "unsupported_keyword",
        `${repr(key)} is outside the strict subset`,
        path,
      );
    } else if (key === "type") {
      for (const name of Array.isArray(value) ? value : [value]) {
        if (typeof name !== "string" || !STRICT_TYPES.has(name)) {
          this.add(
            "unsupported_type",
            `type ${repr(name)} is not allowed`,
            path,
          );
        }
      }
    } else if (
      key === "format" &&
      (typeof value !== "string" || !STRICT_FORMATS.has(value))
    ) {
      this.add(
        "unsupported_format",
        `format ${repr(value)} is not shared`,
        path,
      );
    } else if (key === "minItems" && value !== 0 && value !== 1) {
      this.add(
        "min_items",
        `minItems must be 0 or 1, got ${repr(value)}`,
        path,
      );
    } else if (
      key === "enum" &&
      (!Array.isArray(value) || !value.every(isPrimitive))
    ) {
      this.add("enum_not_primitive", "enum values must be primitives", path);
    }
  }

  checkObject(node: JsonSchema, path: string): void {
    if (node["type"] === "object" || "properties" in node) {
      const extra =
        "additionalProperties" in node
          ? node["additionalProperties"]
          : "missing";
      if (extra !== false) {
        this.add(
          "open_object",
          `object schema needs additionalProperties: false (found ${repr(extra)})`,
          path,
        );
      }
    }
  }

  checkRefs(node: JsonSchema, path: string): void {
    const ref = node["$ref"];
    if (
      typeof ref === "string" &&
      (!ref.startsWith(DEFS_PREFIX) ||
        !Object.hasOwn(this.defs, ref.slice(DEFS_PREFIX.length)))
    ) {
      this.add(
        "unknown_ref",
        `$ref ${repr(ref)} must point at a root $defs entry`,
        path,
      );
    }
    const members = node["allOf"];
    if (
      Array.isArray(members) &&
      members.some((member) => isObject(member) && "$ref" in member)
    ) {
      this.add(
        "allof_ref",
        "allOf must not contain a $ref member",
        `${path}/allOf`,
      );
    }
  }

  recurse(node: JsonSchema, path: string): void {
    const properties = node["properties"];
    if (isObject(properties)) {
      for (const [name, sub] of Object.entries(properties)) {
        this.check(sub, `${path}/properties/${name}`);
      }
    }
    if ("items" in node) {
      this.check(node["items"], `${path}/items`);
    }
    for (const keyword of ["anyOf", "allOf"]) {
      const members = node[keyword];
      if (Array.isArray(members)) {
        members.forEach((sub: unknown, index) => {
          this.check(sub, `${path}/${keyword}/${String(index)}`);
        });
      }
    }
    const extra = node["additionalProperties"];
    if (isObject(extra)) {
      this.check(extra, `${path}/additionalProperties`);
    }
  }
}

/**
 * Report every way `schema` leaves the Anthropic/OpenAI strict subset.
 *
 * Rules: object root; only `STRICT_KEYWORDS` (no `title`, no `x-` keys, no
 * numeric or string bounds); `STRICT_TYPES` and `STRICT_FORMATS` only;
 * `minItems` 0 or 1; primitive `enum` values; `additionalProperties: false`
 * on every object; `$ref` only to a root `$defs` entry, never inside
 * `allOf`, never recursive. Returns an empty array for a clean schema; the
 * schema itself is never modified.
 */
export function strictClean(schema: unknown): Finding[] {
  if (!isObject(schema) || schema["type"] !== "object") {
    return [
      new Finding({
        rule: "root_not_object",
        message: "input schemas must be a mapping with root type 'object'",
        path: "",
      }),
    ];
  }
  const defs = "$defs" in schema ? schema["$defs"] : {};
  if (!isObject(defs)) {
    return [
      new Finding({
        rule: "bad_defs",
        message: "$defs must be a mapping",
        path: "/$defs",
      }),
    ];
  }
  const checker = new StrictChecker(defs);
  checker.check(schema, "", true);
  for (const [name, sub] of Object.entries(defs)) {
    checker.check(sub, `/$defs/${name}`);
  }
  for (const name of recursiveDefs(defs)) {
    checker.add(
      "recursive_ref",
      `$defs entry ${repr(name)} refers to itself`,
      `/$defs/${name}`,
    );
  }
  return checker.findings;
}
