/**
 * JSON Schema emission from zod schemas, shaped like the spec's schemas.
 *
 * `z.toJSONSchema` emits 2020-12. The walk below removes what it adds that
 * the wire format does not state: the root `$schema` (a tool's schema is
 * embedded, not a document), each safe-integer bound `z.int()` carries, and
 * the `propertyNames: {type: "string"}` a record carries (JSON keys are
 * always strings). An unconstrained `additionalProperties: {}` becomes
 * `true`, and a list-valued `type` (`["string", "null"]`) becomes an
 * `anyOf` of one type each, the form strict tool modes accept. Keywords
 * left beside that `anyOf` apply only to the types they constrain, so the
 * schema accepts the same values. A root that is only a `$ref` to a
 * `$defs` entry nothing else refers to (a schema given an `id` with
 * `.meta()`) is inlined, so a model's own schema has an object root while
 * the same model nested elsewhere is a `$ref`.
 *
 * @module
 */
import * as z from "zod";

/** A JSON Schema document or subschema, as plain data. */
export type JsonSchema = Record<string, unknown>;

const DATA_KEYWORDS: ReadonlySet<string> = new Set([
  "const",
  "default",
  "enum",
  "examples",
]);

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isEmptyObject(value: unknown): boolean {
  return isObject(value) && Object.keys(value).length === 0;
}

function tidy(node: unknown): unknown {
  if (Array.isArray(node)) {
    return node.map(tidy);
  }
  if (!isObject(node)) {
    return node;
  }
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(node)) {
    out[key] = DATA_KEYWORDS.has(key) ? value : tidy(value);
  }
  if (out["type"] === "integer") {
    if (out["minimum"] === Number.MIN_SAFE_INTEGER) delete out["minimum"];
    if (out["maximum"] === Number.MAX_SAFE_INTEGER) delete out["maximum"];
  }
  const type = out["type"];
  if (Array.isArray(type)) {
    delete out["type"];
    out["anyOf"] = type.map((name: unknown) => ({ type: name }));
  }
  const names = out["propertyNames"];
  if (
    isObject(names) &&
    names["type"] === "string" &&
    Object.keys(names).length === 1
  ) {
    delete out["propertyNames"];
  }
  if (isEmptyObject(out["additionalProperties"])) {
    out["additionalProperties"] = true;
  }
  return out;
}

/** True when `ref` is a `$ref` value anywhere under `node`. */
function refersTo(node: unknown, ref: string): boolean {
  if (Array.isArray(node)) {
    return node.some((item) => refersTo(item, ref));
  }
  if (!isObject(node)) {
    return false;
  }
  return Object.entries(node).some(([key, value]) =>
    key === "$ref"
      ? value === ref
      : !DATA_KEYWORDS.has(key) && refersTo(value, ref),
  );
}

/** Inline a root that only refers to a `$defs` entry used nowhere else. */
function inlineRoot(schema: JsonSchema): JsonSchema {
  const ref = schema["$ref"];
  const defs = schema["$defs"];
  if (
    typeof ref !== "string" ||
    !ref.startsWith("#/$defs/") ||
    !isObject(defs) ||
    Object.keys(schema).length !== 2
  ) {
    return schema;
  }
  const { [ref.slice("#/$defs/".length)]: root, ...rest } = defs;
  if (!isObject(root) || refersTo(root, ref) || refersTo(rest, ref)) {
    return schema;
  }
  return Object.keys(rest).length === 0 ? root : { ...root, $defs: rest };
}

/**
 * Return the 2020-12 JSON Schema of `schema` without a root `$schema`.
 *
 * `io` picks the side of a transform the schema describes: `input` for
 * what a parser accepts, `output` for what it returns.
 */
export function zodJsonSchema(
  schema: z.ZodType,
  io: "input" | "output",
): JsonSchema {
  const emitted = tidy(z.toJSONSchema(schema, { io })) as JsonSchema;
  delete emitted["$schema"];
  return inlineRoot(emitted);
}
