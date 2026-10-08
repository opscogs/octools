/**
 * The `OCTool` agent-tool descriptor and the `ToolProvider` interface.
 *
 * An `OCTool` is a frozen, vendor-neutral description of one capability a
 * library offers to an agent runtime: a name, a model-facing description,
 * JSON Schema 2020-12 for its arguments and result, MCP-vocabulary safety
 * hints, an OpsCogs access classification, and the function that does the
 * work. Construction fails fast on structural errors; policy conformance
 * (sentence counts, strict-clean schemas, escape reasons) is reported by
 * `validateTool` and `validateProvider` instead, so a library can assert on
 * findings.
 *
 * @module
 */
import { OCToolError } from "./errors.js";
import { Finding } from "./findings.js";
import type { JsonSchema } from "./internal/jsonSchema.js";
import { strip } from "./internal/pytext.js";
import {
  ACCESS_KINDS,
  type Access,
  NAME_RE,
  RESULT_KINDS,
  type ResultKind,
} from "./vocabulary.js";

/**
 * The function a tool runs. Any synchronous function fits; its arguments
 * are the runtime's business, not the descriptor's.
 */
export type ToolFunc = (...args: never[]) => unknown;

/**
 * The fields an {@link OCTool} is constructed from.
 *
 * Required: `name`, `description`, `inputSchema`, `func` and `access`.
 * Every other field has a default, so a field a later minor spec version
 * adds never breaks construction.
 */
export interface OCToolInit {
  /** Lowercase snake_case, at most 48 characters ({@link NAME_RE}). */
  readonly name: string;
  /** The model-facing description: two to four sentences. */
  readonly description: string;
  /** JSON Schema of the arguments; the root has `type: "object"`. */
  readonly inputSchema: JsonSchema;
  /** The synchronous function that does the work. */
  readonly func: ToolFunc;
  /** Whether the tool reaches only local state or a remote system. */
  readonly access: Access;
  /** The remote system the tool reaches, when it names one. */
  readonly target?: string | null | undefined;
  /** JSON Schema of the result; the root has `type: "object"`. */
  readonly outputSchema?: JsonSchema | null | undefined;
  /** The envelope the tool returns. Defaults to `records`. */
  readonly resultKind?: ResultKind | undefined;
  /** A display name for a person. */
  readonly title?: string | null | undefined;
  /** The tool changes nothing. Defaults to `true`. */
  readonly readOnlyHint?: boolean | undefined;
  /** A change the tool makes may destroy data. Defaults to `false`. */
  readonly destructiveHint?: boolean | undefined;
  /** Repeating a call has no further effect. Defaults to `true`. */
  readonly idempotentHint?: boolean | undefined;
  /** The tool is kept only as an alias. Defaults to `false`. */
  readonly deprecated?: boolean | undefined;
  /** Free-form JSON data for the runtime. Defaults to `{}`. */
  readonly meta?: Readonly<Record<string, unknown>> | undefined;
}

const FIELDS: ReadonlySet<string> = new Set([
  "name",
  "description",
  "inputSchema",
  "func",
  "access",
  "target",
  "outputSchema",
  "resultKind",
  "title",
  "readOnlyHint",
  "destructiveHint",
  "idempotentHint",
  "deprecated",
  "meta",
]);
const HINTS = ["readOnlyHint", "destructiveHint", "idempotentHint"] as const;
const ASYNC_TAGS: ReadonlySet<string> = new Set([
  "[object AsyncFunction]",
  "[object AsyncGeneratorFunction]",
]);

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Return `value` as it reads in a message: JSON where it has one. */
function show(value: unknown): string {
  return value === undefined ? "undefined" : JSON.stringify(value);
}

/** Return `value`, or `fallback` when it is left out; `null` is kept. */
function given<T>(value: T | undefined, fallback: T): T {
  return typeof value === "undefined" ? fallback : value;
}

function ensure(condition: boolean, message: string): void {
  if (!condition) {
    throw new OCToolError(message);
  }
}

function isBlankFree(value: unknown): boolean {
  return typeof value === "string" && strip(value) !== "";
}

function checkObjectSchema(schema: unknown, label: string): void {
  if (!isObject(schema)) {
    throw new OCToolError(`${label} must be a JSON object`);
  }
  ensure(
    schema["type"] === "object",
    `${label} root must have type 'object', got ${show(schema["type"])}`,
  );
}

/**
 * One agent tool, described once, convertible to any vendor's shape.
 *
 * The fields mirror the descriptor's wire keys in camelCase
 * (`input_schema` is `inputSchema`). The constructor checks the structural
 * invariants and throws {@link OCToolError} on the first one that fails,
 * including a field the descriptor does not have. Instances are frozen.
 */
export class OCTool {
  /** Lowercase snake_case, at most 48 characters. */
  readonly name: string;
  /** The model-facing description. */
  readonly description: string;
  /** JSON Schema of the arguments. */
  readonly inputSchema: JsonSchema;
  /** The function that does the work. */
  readonly func: ToolFunc;
  /** `local` or `remote`. */
  readonly access: Access;
  /** The remote system the tool reaches, or `null`. */
  readonly target: string | null;
  /** JSON Schema of the result, or `null`. */
  readonly outputSchema: JsonSchema | null;
  /** `records` or `artifact`. */
  readonly resultKind: ResultKind;
  /** A display name for a person, or `null`. */
  readonly title: string | null;
  /** The tool changes nothing. */
  readonly readOnlyHint: boolean;
  /** A change the tool makes may destroy data. */
  readonly destructiveHint: boolean;
  /** Repeating a call has no further effect. */
  readonly idempotentHint: boolean;
  /** The tool is kept only as an alias. */
  readonly deprecated: boolean;
  /** Free-form JSON data for the runtime. */
  readonly meta: Readonly<Record<string, unknown>>;

  /** Build a frozen descriptor; throw {@link OCToolError} on invalid data. */
  constructor(init: OCToolInit) {
    const unknown = Object.keys(init).filter((key) => !FIELDS.has(key));
    ensure(
      unknown.length === 0,
      `tool ${show(init.name)}: unknown fields ${show(unknown)}`,
    );
    this.name = init.name;
    this.description = init.description;
    this.inputSchema = init.inputSchema;
    this.func = init.func;
    this.access = init.access;
    this.target = init.target ?? null;
    this.outputSchema = init.outputSchema ?? null;
    this.resultKind = given(init.resultKind, "records");
    this.title = init.title ?? null;
    this.readOnlyHint = given(init.readOnlyHint, true);
    this.destructiveHint = given(init.destructiveHint, false);
    this.idempotentHint = given(init.idempotentHint, true);
    this.deprecated = given(init.deprecated, false);
    this.meta = given(init.meta, {});
    this.check();
    Object.freeze(this);
  }

  private check(): void {
    const label = `tool ${show(this.name)}`;
    ensure(
      typeof this.name === "string" && NAME_RE.test(this.name),
      `name ${show(this.name)} must match ${NAME_RE.source}`,
    );
    ensure(
      isBlankFree(this.description),
      `${label}: description must be a non-empty string`,
    );
    checkObjectSchema(this.inputSchema, `${label}: inputSchema`);
    if (this.outputSchema !== null) {
      checkObjectSchema(this.outputSchema, `${label}: outputSchema`);
    }
    ensure(
      typeof this.func === "function",
      `${label}: func must be a function`,
    );
    ensure(
      !ASYNC_TAGS.has(Object.prototype.toString.call(this.func)),
      `${label}: func must be synchronous, not async`,
    );
    ensure(
      (ACCESS_KINDS as readonly unknown[]).includes(this.access),
      `${label}: access must be one of ${show(ACCESS_KINDS)}, got ${show(this.access)}`,
    );
    ensure(
      this.target === null || isBlankFree(this.target),
      `${label}: target must be null or a non-empty string`,
    );
    ensure(
      (RESULT_KINDS as readonly unknown[]).includes(this.resultKind),
      `${label}: resultKind must be one of ${show(RESULT_KINDS)}, got ${show(this.resultKind)}`,
    );
    ensure(
      this.title === null || isBlankFree(this.title),
      `${label}: title must be null or a non-empty string`,
    );
    for (const hint of HINTS) {
      ensure(
        typeof this[hint] === "boolean",
        `${label}: ${hint} must be a boolean`,
      );
    }
    ensure(
      typeof this.deprecated === "boolean",
      `${label}: deprecated must be a boolean`,
    );
    ensure(isObject(this.meta), `${label}: meta must be a JSON object`);
  }
}

/**
 * Anything that lists its tools.
 *
 * `allTools()` returns the descriptors in a fixed order (MCP asks for
 * deterministic listings so prompt caches stay warm) with unique names.
 */
export interface ToolProvider {
  /** Return every tool this provider offers, in deterministic order. */
  allTools(): readonly OCTool[];
}

/**
 * Combine providers into one whose listing concatenates theirs, in order.
 *
 * A consumer registering its own tools beside another package's validates
 * the union, not each half. Nothing is deduplicated: a name two providers
 * share stays listed twice so `validateProvider` reports it as
 * `duplicate_name` instead of silently dropping one of them.
 */
export function mergeProviders(...providers: ToolProvider[]): ToolProvider {
  const parts = Object.freeze([...providers]);
  return Object.freeze({
    allTools: (): readonly OCTool[] =>
      Object.freeze(parts.flatMap((provider) => [...provider.allTools()])),
  });
}

/** Return the type of a listed item that is not an `OCTool`, for a message. */
export function typeName(item: unknown): string {
  if (item === null) {
    return "null";
  }
  if (Array.isArray(item)) {
    return "array";
  }
  if (typeof item === "object") {
    const ctor = (item as { constructor?: unknown }).constructor;
    return typeof ctor === "function" && ctor.name !== ""
      ? ctor.name
      : "object";
  }
  return typeof item;
}

/** Return the names `allTools()` lists; foreign items show as their type. */
function listedNames(provider: ToolProvider): string[] {
  const items: readonly unknown[] = provider.allTools();
  return items.map((item) =>
    item instanceof OCTool ? item.name : `<${typeName(item)}>`,
  );
}

/**
 * Report duplicate names and unstable ordering in a provider's listing.
 *
 * Calls `allTools()` twice: the two name sequences must be identical
 * (`unstable_order`) and each name must appear once (`duplicate_name`).
 */
export function checkToolListing(provider: ToolProvider): Finding[] {
  const first = listedNames(provider);
  const second = listedNames(provider);
  const findings: Finding[] = [];
  if (show(first) !== show(second)) {
    findings.push(
      new Finding({
        rule: "unstable_order",
        message: `allTools() order changed between calls: ${show(first)} then ${show(second)}`,
      }),
    );
  }
  const seen = new Set<string>();
  for (const name of first) {
    if (seen.has(name)) {
      findings.push(
        new Finding({
          rule: "duplicate_name",
          message: `tool name ${show(name)} is listed more than once`,
          tool: name,
        }),
      );
    }
    seen.add(name);
  }
  return findings;
}
