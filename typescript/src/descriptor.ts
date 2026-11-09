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
  ALIAS_OF_KEY,
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
  /** What the tool is, for a host to select by. Defaults to none. */
  readonly tags?: readonly string[] | undefined;
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
  "tags",
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
  /** What the tool is, for a host to select by; `recommended` or `advanced`. */
  readonly tags: readonly string[];

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
    this.tags = given(init.tags, []);
    this.check();
    this.tags = Object.freeze([...this.tags]);
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
    ensure(
      Array.isArray(this.tags) && this.tags.every(isBlankFree),
      `${label}: tags must be an array of non-empty strings`,
    );
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

/**
 * Return a provider listing only the tools carrying any of `options.tags`.
 *
 * A host calls this before converting, so it needs no consumer's `meta` key:
 * `selectTools(merged, { tags: ["recommended"] })`. Order is kept, and the
 * result reads the underlying provider on every `allTools()` call. A
 * deprecated alias whose `meta["alias_of"]` target is not selected is dropped,
 * and so is an alias of a dropped alias, until every kept alias names a kept
 * tool, so the result passes `validateProvider`. A target is never pulled in. A bare string throws
 * {@link OCToolError}, since it would match by character.
 */
export function selectTools(
  provider: ToolProvider,
  options: { readonly tags: Iterable<string> },
): ToolProvider {
  ensure(
    typeof options.tags !== "string",
    "tags must be an iterable of strings",
  );
  const tags = new Set(options.tags);
  return Object.freeze({
    allTools: (): readonly OCTool[] => {
      let matched = provider
        .allTools()
        .filter(
          (tool): tool is OCTool =>
            tool instanceof OCTool && tool.tags.some((tag) => tags.has(tag)),
        );
      let kept = matched;
      do {
        matched = kept;
        const names = new Set(matched.map((tool) => tool.name));
        kept = matched.filter((tool) => !stranded(tool, names));
      } while (kept.length !== matched.length);
      return Object.freeze(kept);
    },
  });
}

/** True when `tool` is a deprecated alias whose target is not in `names`. */
function stranded(tool: OCTool, names: ReadonlySet<string>): boolean {
  const alias = tool.meta[ALIAS_OF_KEY];
  return tool.deprecated && typeof alias === "string" && !names.has(alias);
}

/** Schema keywords whose values are instance data, never rewritten. */
const DATA_KEYWORDS: ReadonlySet<string> = new Set([
  "const",
  "default",
  "enum",
  "examples",
]);
/** Schema keywords whose keys are names and whose values are schemas. */
const NAME_MAPS: ReadonlySet<string> = new Set([
  "$defs",
  "definitions",
  "dependentSchemas",
  "patternProperties",
  "properties",
]);

/** Return a copy of schema `node` with every `description` rewritten. */
function rewriteSchema(
  node: unknown,
  rewrite: (text: string) => string,
): unknown {
  if (Array.isArray(node)) {
    return node.map((sub) => rewriteSchema(sub, rewrite));
  }
  if (!isObject(node)) {
    return node;
  }
  return Object.fromEntries(
    Object.entries(node).map(([key, value]) => {
      if (key === "description" && typeof value === "string") {
        return [key, rewrite(value)];
      }
      if (NAME_MAPS.has(key) && isObject(value)) {
        return [
          key,
          Object.fromEntries(
            Object.entries(value).map(([name, sub]) => [
              name,
              rewriteSchema(sub, rewrite),
            ]),
          ),
        ];
      }
      return [
        key,
        DATA_KEYWORDS.has(key) ? value : rewriteSchema(value, rewrite),
      ];
    }),
  );
}

/**
 * Return a function replacing each whole-word key of `renames` in text.
 *
 * A word is a run of ASCII letters, digits and underscores, so an occurrence
 * inside a longer name (`demo_get_rows`, `get_rows_all`) is left alone.
 */
function renamer(
  renames: ReadonlyMap<string, string>,
): (text: string) => string {
  const changed = [...renames]
    .filter(([from, to]) => from !== to)
    .map(([from]) => from)
    .sort((a, b) => b.length - a.length);
  if (changed.length === 0) {
    return (text) => text;
  }
  // Tool names match NAME_RE, so they hold no RegExp metacharacter.
  const pattern = new RegExp(
    `(?<![A-Za-z0-9_])(?:${changed.join("|")})(?![A-Za-z0-9_])`,
    "g",
  );
  return (text) => text.replace(pattern, (word) => String(renames.get(word)));
}

/** Return `name` with `namePrefix` prepended unless it already starts so. */
function withPrefix(name: string, namePrefix: string): string {
  return name.startsWith(namePrefix) ? name : `${namePrefix}${name}`;
}

/**
 * Return copies of `tools` published under `namePrefix`.
 *
 * A prefix without a trailing underscore gets one, so `"demo"` and `"demo_"`
 * are the same prefix. Each copy keeps its own `func`; a name already
 * starting with the prefix is kept, so applying it twice changes nothing.
 * `meta["alias_of"]` is prefixed the same way. Every whole-word occurrence
 * of a sibling's name, in `description` and in any `description` of
 * `inputSchema` or `outputSchema` (instance data such as `enum` and
 * `default` excepted),
 * becomes the sibling's published name; an occurrence already prefixed and
 * words that name no sibling stay as they are. A prefixed name that breaks
 * {@link NAME_RE}, or an item that is not an `OCTool`, throws
 * {@link OCToolError}. A host dispatches by the returned descriptors' names.
 */
export function prefixTools(
  tools: Iterable<OCTool>,
  namePrefix: string,
): readonly OCTool[] {
  const prefix =
    namePrefix === "" || namePrefix.endsWith("_")
      ? namePrefix
      : `${namePrefix}_`;
  const listed: readonly unknown[] = [...tools];
  for (const item of listed) {
    ensure(item instanceof OCTool, `${typeName(item)} is not an OCTool`);
  }
  const octools = listed as readonly OCTool[];
  const names = octools.map((tool) => withPrefix(tool.name, prefix));
  const renames = new Map(
    octools.map((tool, index) => [tool.name, String(names[index])]),
  );
  for (const name of names) {
    ensure(
      NAME_RE.test(name),
      `tool name ${show(name)} does not match ${NAME_RE.source}`,
    );
  }
  const rename = renamer(renames);
  return Object.freeze(
    octools.map((tool, index) => {
      const alias = tool.meta[ALIAS_OF_KEY];
      return new OCTool({
        name: String(names[index]),
        func: tool.func,
        access: tool.access,
        target: tool.target,
        outputSchema:
          tool.outputSchema === null
            ? null
            : (rewriteSchema(tool.outputSchema, rename) as JsonSchema),
        resultKind: tool.resultKind,
        title: tool.title,
        readOnlyHint: tool.readOnlyHint,
        destructiveHint: tool.destructiveHint,
        idempotentHint: tool.idempotentHint,
        deprecated: tool.deprecated,
        tags: tool.tags,
        description: rename(tool.description),
        inputSchema: rewriteSchema(tool.inputSchema, rename) as JsonSchema,
        meta:
          typeof alias === "string"
            ? { ...tool.meta, [ALIAS_OF_KEY]: withPrefix(alias, prefix) }
            : tool.meta,
      });
    }),
  );
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
