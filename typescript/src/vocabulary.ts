/**
 * The format version, every closed vocabulary with its fallback, and the
 * shared constants of the wire format.
 *
 * Every value here equals the one in `spec/vocabulary.json`; the test suite
 * checks that. A fallback is the value a tolerant reader reads in place of
 * a vocabulary value it does not know, and is always the most conservative
 * reading of its vocabulary.
 *
 * @module
 */

/**
 * Format version of the `OCTool` descriptor and the result envelopes.
 *
 * Readers check the major only. A minor adds only what a reader may drop or
 * read as a fallback: an optional field whose absence keeps its meaning, or
 * a value in a vocabulary that has a fallback.
 */
export const SPEC_VERSION = "1.1";

/** Every `result_kind` value, in documentation order. */
export const RESULT_KINDS = ["records", "artifact"] as const;
/** The closed `result_kind` vocabulary. */
export type ResultKind = (typeof RESULT_KINDS)[number];
/** How a reader of a tool listing reads a `result_kind` it does not know. */
export const RESULT_KIND_FALLBACK: ResultKind = "records";

/** Every `access` value, in documentation order. */
export const ACCESS_KINDS = ["local", "remote"] as const;
/** The closed `access` vocabulary. */
export type Access = (typeof ACCESS_KINDS)[number];
/**
 * How a reader of a tool listing reads an `access` it does not know:
 * `remote` is the safer policy assumption.
 */
export const ACCESS_FALLBACK: Access = "remote";

/** Every `column_kinds` value, in documentation order. */
export const COLUMN_KINDS = [
  "text",
  "number",
  "integer",
  "boolean",
  "timestamp",
  "ip",
  "fqdn",
  "mac",
  "ip_block",
  "big_integer",
] as const;
/** The closed `column_kinds` vocabulary. */
export type ColumnKind = (typeof COLUMN_KINDS)[number];
/** How `readEnvelope` reads a kind it does not know: every cell is text. */
export const COLUMN_KIND_FALLBACK: ColumnKind = "text";

/** Every `column_scales` value, in documentation order. */
export const COLUMN_SCALES = ["linear", "log10", "log2"] as const;
/** The closed `column_scales` vocabulary. */
export type ColumnScale = (typeof COLUMN_SCALES)[number];
/** How `readEnvelope` reads a scale it does not know: no hint. */
export const COLUMN_SCALE_FALLBACK: ColumnScale | null = null;

/** The closed `ArtifactEnvelope.sensitivity` vocabulary. */
export type Sensitivity = "inherits_input";
/**
 * The `sensitivity` values, for this package's own checks. The spec names no
 * constant for this vocabulary, so the package root does not export it.
 */
export const SENSITIVITIES: readonly Sensitivity[] = ["inherits_input"];
/**
 * How `readEnvelope` reads a sensitivity it does not know.
 *
 * `inherits_input` is the most conservative reading, and only values less
 * restrictive than it may be added, so degrading to it is always fail-safe.
 */
export const SENSITIVITY_FALLBACK: Sensitivity = "inherits_input";

/** Every closed envelope vocabulary, by field name, with its fallback. */
export const VOCABULARY_FALLBACKS: Readonly<Record<string, string | null>> =
  Object.freeze({
    column_kinds: COLUMN_KIND_FALLBACK,
    column_scales: COLUMN_SCALE_FALLBACK,
    sensitivity: SENSITIVITY_FALLBACK,
  });

/**
 * Tool names: lowercase snake_case, at most 48 characters.
 *
 * The tightest common tool-name limit is 64 characters; the 16 spare leave
 * room for the runtime's namespace prefix (for example `demo_`).
 *
 * In Python, `$` also matches just before a final newline, so the Python
 * pattern accepts a name ending in `\n`; this RegExp's `$` does not.
 */
export const NAME_RE = /^[a-z][a-z0-9_]{0,47}$/;
/** The Anthropic tool name rule: 1-128 of `A-Z a-z 0-9 _ -`. */
export const ANTHROPIC_NAME_RE = /^[a-zA-Z0-9_-]{1,128}$/;
/** The MCP `Tool.name` rule: 1-128 of `A-Z a-z 0-9 _ - .`. */
export const MCP_NAME_RE = /^[A-Za-z0-9_.-]{1,128}$/;
/** Reverse-DNS prefix for OpsCogs keys in an MCP tool's `_meta`. */
export const MCP_META_NAMESPACE = "com.opscogs.octools/";

/** The JSON Schema dialect every emitted schema uses. */
export const SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema";
/** Keywords every supported strict tool mode accepts (the intersection). */
export const STRICT_KEYWORDS: ReadonlySet<string> = new Set([
  "$defs",
  "$ref",
  "additionalProperties",
  "allOf",
  "anyOf",
  "const",
  "default",
  "description",
  "enum",
  "format",
  "items",
  "minItems",
  "properties",
  "required",
  "type",
]);
/** The `type` values every supported strict tool mode accepts. */
export const STRICT_TYPES: ReadonlySet<string> = new Set([
  "array",
  "boolean",
  "integer",
  "null",
  "number",
  "object",
  "string",
]);
/** The `format` values every supported strict tool mode accepts. */
export const STRICT_FORMATS: ReadonlySet<string> = new Set([
  "date",
  "date-time",
  "duration",
  "email",
  "hostname",
  "ipv4",
  "ipv6",
  "time",
  "uri",
  "uuid",
]);
/** The `$defs` key under which `TabularEnvelope` appears when nested. */
export const TABULAR_DEF_NAME = "TabularEnvelope";

/** Fewest sentences a tool description may have. */
export const MIN_SENTENCES = 2;
/** Most sentences a tool description may have. */
export const MAX_SENTENCES = 4;
/** `meta` key recording why a tool has no closed `output_schema`. */
export const SCHEMA_ESCAPE_KEY = "schema_escape";
/** `meta` key on a deprecated alias naming the tool it stands for. */
export const ALIAS_OF_KEY = "alias_of";

/** Every listing style, in documentation order. */
export const LISTING_STYLES = ["table", "md", "txt", "json"] as const;
/** A listing style: `table`, `md`, `txt` or `json`. */
export type ListingStyle = (typeof LISTING_STYLES)[number];
