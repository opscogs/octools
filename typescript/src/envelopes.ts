/**
 * Result envelopes every `OCTool` result is wrapped in.
 *
 * A tool result is always a JSON object. Record-shaped results use
 * {@link RecordsEnvelope}; column-shaped results whose columns are only
 * known at run time use {@link TabularEnvelope}; file-producing tools use
 * {@link ArtifactEnvelope}. Each is a zod schema whose output type has the
 * same name.
 *
 * The two list envelopes page the same way: `truncated` says the list was
 * cut short, an opaque `next_cursor` says how to fetch the rest, and
 * `total_count` is given only when the source knows it exactly.
 * `stop_reason` names what stopped a truncated read early, and the derived
 * `resumable` (`next_cursor` present) says whether the read can go on.
 *
 * Parsing with a schema (`TabularEnvelope.parse(data)`) is strict: unknown
 * keys and unknown vocabulary values fail, so a producer's typo fails in
 * its own tests. The parsed value is the envelope's wire form, ready for
 * `JSON.stringify`: unset optional fields are left out, an empty
 * `warnings` is left out of the list envelopes, and `resumable` is present
 * only when `truncated` is true. A `resumable` key on input is checked
 * against `next_cursor`, never stored as given.
 *
 * {@link readEnvelope} is the tolerant entry point for an envelope from
 * another process: it drops unknown keys and reads an unknown vocabulary
 * value as that vocabulary's fallback, and checks everything else.
 *
 * Wire keys are snake_case in both directions, exactly as the spec spells
 * them.
 *
 * @module
 */
import * as z from "zod";

import type { JsonSchema } from "./internal/jsonSchema.js";
import { outputSchemaFor } from "./schema.js";
import {
  COLUMN_KIND_FALLBACK,
  COLUMN_KINDS,
  COLUMN_SCALE_FALLBACK,
  COLUMN_SCALES,
  type ColumnKind,
  type ColumnScale,
  SENSITIVITIES,
  SENSITIVITY_FALLBACK,
  type Sensitivity,
  TABULAR_DEF_NAME,
} from "./vocabulary.js";

/** A tabular cell: scalars only, so the envelope stays strict-clean. */
export type Cell = string | number | boolean | null;

/** The kinds a non-null `column_scales` entry may apply to. */
const NUMERIC_KINDS: readonly string[] = ["number", "integer", "big_integer"];
const DECIMAL_RE = /^(0|[1-9][0-9]*)$/;

/**
 * An integer field. JavaScript numbers hold integers exactly only up to
 * 2^53 - 1, so an integer beyond that fails here rather than being read
 * with a silently rounded value; Python reads it exactly. The wire format
 * carries larger counts as decimal strings (`total_count`, `big_integer`).
 */
const integer = (): z.ZodInt => z.int();

const TOTAL_COUNT_DESCRIPTION =
  "Exact size of the full result when the source knows it, as an integer, or " +
  "as a decimal string when above 2^53 - 1; omitted when unknown or " +
  "approximate.";
const TRUNCATED_DESCRIPTION =
  "True when a cap, a stop or an interrupted read cut the result short. " +
  "A truncated read whose resumable is false is the terminal case: it " +
  "ended for good and there is nothing left to follow.";
const NEXT_CURSOR_DESCRIPTION =
  "Opaque token that resumes the read where it stopped, present only " +
  "when resumable is true; pass it back as the tool's cursor argument, " +
  "unchanged.";
const WARNINGS_DESCRIPTION =
  "Non-fatal problems the caller should relay, one per entry.";

function stopReasonDescription(items: string): string {
  return (
    "Why the read stopped early. Well-known values include run_deadline, " +
    "page_count, record_limit, interrupted and cursor_stalled; omitted when " +
    "the read ended naturally or the limit simply cut it. A cursor_stalled read " +
    "publishes no next_cursor, because following it would serve the same " +
    `${items} again.`
  );
}

function resumableDescription(items: string): string {
  return (
    `True when next_cursor is present and following it reads more ${items}; ` +
    "false when this read is over: do not call again with the same " +
    "arguments. Present only when truncated is true; absent reads as false."
  );
}

/** The paging fields both list envelopes share, after `truncated`. */
function pagingShape(items: string) {
  return {
    total_count: z
      .union([integer(), z.string(), z.null()])
      .default(null)
      .describe(TOTAL_COUNT_DESCRIPTION),
    next_cursor: z
      .string()
      .nullable()
      .default(null)
      .describe(NEXT_CURSOR_DESCRIPTION),
    stop_reason: z
      .string()
      .nullable()
      .default(null)
      .describe(stopReasonDescription(items)),
    warnings: z.array(z.string()).optional().describe(WARNINGS_DESCRIPTION),
    resumable: z.boolean().optional().describe(resumableDescription(items)),
  };
}

/** The paging fields as parsed, before they are dumped. */
interface ParsedPaging {
  truncated: boolean;
  total_count: number | string | null;
  next_cursor: string | null;
  stop_reason: string | null;
  warnings?: string[] | undefined;
  resumable?: boolean | undefined;
}

/** The paging fields of a list envelope's wire form. */
export interface PagingFields {
  /** True when a cap, a stop or an interrupted read cut the result short. */
  truncated: boolean;
  /** Exact size of the full result, as an integer or a decimal string. */
  total_count?: number | string;
  /** Opaque token that resumes the read; present only when resumable. */
  next_cursor?: string;
  /** Why the read stopped early. */
  stop_reason?: string;
  /** Non-fatal problems the caller should relay; left out when empty. */
  warnings?: string[];
  /** Whether following `next_cursor` reads more; present only when truncated. */
  resumable?: boolean;
}

/** The paging fields of a list envelope as a strict parse accepts them. */
export interface PagingInput {
  truncated: boolean;
  total_count?: number | string | null | undefined;
  next_cursor?: string | null | undefined;
  stop_reason?: string | null | undefined;
  warnings?: string[] | undefined;
  resumable?: boolean | undefined;
}

/** Return why the paging fields contradict the list they describe, or null. */
function pagingProblem(paging: ParsedPaging, returned: number): string | null {
  const { truncated, total_count: total, next_cursor: cursor } = paging;
  if (
    paging.resumable !== undefined &&
    paging.resumable !== (cursor !== null)
  ) {
    return `resumable ${String(paging.resumable)} contradicts next_cursor`;
  }
  if (cursor !== null && !truncated) {
    return "next_cursor is only given when truncated is true";
  }
  if (paging.stop_reason !== null && !truncated) {
    return "stop_reason is only given when truncated is true";
  }
  if (typeof total === "string" && !DECIMAL_RE.test(total)) {
    return `total_count ${JSON.stringify(total)} is not a non-negative decimal string`;
  }
  if (total !== null && BigInt(total) < BigInt(returned)) {
    return `total_count ${String(total)} is below the ${String(returned)} returned`;
  }
  return null;
}

/** Return the paging fields' wire form: unset fields and empty warnings left out. */
function dumpPaging(paging: ParsedPaging): PagingFields {
  const out: PagingFields = { truncated: paging.truncated };
  if (paging.total_count !== null) out.total_count = paging.total_count;
  if (paging.next_cursor !== null) out.next_cursor = paging.next_cursor;
  if (paging.stop_reason !== null) out.stop_reason = paging.stop_reason;
  if (paging.warnings !== undefined && paging.warnings.length > 0) {
    out.warnings = paging.warnings;
  }
  if (paging.truncated) out.resumable = paging.next_cursor !== null;
  return out;
}

function report(ctx: z.RefinementCtx, problem: string | null): void {
  if (problem !== null) {
    ctx.addIssue({ code: "custom", message: problem });
  }
}

/** Records whose keys follow the item schema, with an honest cap. */
export interface RecordsEnvelope<T = unknown> extends PagingFields {
  /** Result records; keys and order follow the item schema. */
  records: T[];
  /** Number of records returned, after any cap; equals `records.length`. */
  count: number;
}

/** A records envelope as a strict parse accepts it. */
export interface RecordsEnvelopeInput<T = unknown> extends PagingInput {
  records: T[];
  count: number;
}

/** A records envelope schema over records of output type `O`, input type `I`. */
export type RecordsEnvelopeSchema<O = unknown, I = unknown> = z.ZodType<
  RecordsEnvelope<O>,
  RecordsEnvelopeInput<I>
>;

/** Columns and rows for results whose shape is only known at run time. */
export interface TabularEnvelope extends PagingFields {
  /** Column names, in row order. */
  columns: string[];
  /** Rows of scalar cells; each row has one cell per column. */
  rows: Cell[][];
  /** Number of rows returned, after any cap; equals `rows.length`. */
  row_count: number;
  /** Per-column kind, one per column. */
  column_kinds?: ColumnKind[];
  /** Per-column chart scale hint, one per column; null for no hint. */
  column_scales?: (ColumnScale | null)[];
  /** One short description per column; null where a column has none. */
  column_descriptions?: (string | null)[];
}

/** A tabular envelope as a strict parse accepts it. */
export interface TabularEnvelopeInput extends PagingInput {
  columns: string[];
  rows: Cell[][];
  row_count: number;
  column_kinds?: ColumnKind[] | null | undefined;
  column_scales?: (ColumnScale | null)[] | null | undefined;
  column_descriptions?: (string | null)[] | null | undefined;
}

/** Where one produced artifact lives and what it is. */
export interface ArtifactRef {
  /** Reference the caller can cite: the path or id the sink returned. */
  reference: string;
  /** IANA media type, such as `image/svg+xml`. */
  media_type: string;
  /** Size of the artifact in bytes. */
  bytes: number;
  /** Pixel width when the artifact is an image. */
  width?: number;
  /** Pixel height when the artifact is an image. */
  height?: number;
  /** What the artifact is to the run, such as csv, plan or summary. */
  role?: string;
}

/** An artifact reference as a strict parse accepts it. */
export interface ArtifactRefInput {
  reference: string;
  media_type: string;
  bytes: number;
  width?: number | null | undefined;
  height?: number | null | undefined;
  role?: string | null | undefined;
}

/** Result of a tool that produces a file rather than data to read. */
export interface ArtifactEnvelope {
  /** The primary artifact produced. */
  artifact: ArtifactRef;
  /** Further artifacts produced alongside the primary, if any. */
  artifacts: ArtifactRef[];
  /** Non-fatal problems the caller should relay; always present. */
  warnings: string[];
  /** The artifact is treated as containing every input column. */
  sensitivity: Sensitivity;
}

/** An artifact envelope as a strict parse accepts it. */
export interface ArtifactEnvelopeInput {
  artifact: ArtifactRefInput;
  artifacts?: ArtifactRefInput[] | undefined;
  warnings?: string[] | undefined;
  sensitivity?: Sensitivity | undefined;
}

/** How each envelope schema is read tolerantly, before its strict parse. */
const TOLERATE = new WeakMap<
  z.ZodType,
  (data: Record<string, unknown>) => Record<string, unknown>
>();

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Return a copy of `data` holding only the keys in `known`. */
function pick(
  data: Record<string, unknown>,
  known: ReadonlySet<string>,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(data).filter(([key]) => known.has(key)),
  );
}

/** Return `data` without unknown keys when it is an object, else unchanged. */
function dropUnknown(data: unknown, known: ReadonlySet<string>): unknown {
  return isObject(data) ? pick(data, known) : data;
}

const recordsSchemas = new WeakMap<z.ZodType, RecordsEnvelopeSchema>();
const ANY_RECORD = z.unknown();

/**
 * Return the records envelope schema over records that `item` parses.
 *
 * Called with no argument, records are any JSON value. The same `item`
 * always returns the same schema.
 */
export function RecordsEnvelope(): RecordsEnvelopeSchema;
export function RecordsEnvelope<T extends z.ZodType>(
  item: T,
): RecordsEnvelopeSchema<z.output<T>, z.input<T>>;
export function RecordsEnvelope(
  item: z.ZodType = ANY_RECORD,
): RecordsEnvelopeSchema {
  const cached = recordsSchemas.get(item);
  if (cached !== undefined) {
    return cached;
  }
  const shape = {
    records: z
      .array(item)
      .describe("Result records; keys and order follow the item schema."),
    count: integer().describe(
      "Number of records returned, after any cap; equals len(records).",
    ),
    truncated: z.boolean().describe(TRUNCATED_DESCRIPTION),
    ...pagingShape("records"),
  };
  const known = new Set(Object.keys(shape));
  const schema: RecordsEnvelopeSchema = z
    .strictObject(shape)
    .superRefine((value, ctx) => {
      report(
        ctx,
        value.records.length === value.count
          ? pagingProblem(value, value.count)
          : `count ${String(value.count)} does not match the ` +
              `${String(value.records.length)} records returned`,
      );
    })
    .transform((value): RecordsEnvelope => ({
      records: value.records,
      count: value.count,
      ...dumpPaging(value),
    }));
  recordsSchemas.set(item, schema);
  TOLERATE.set(schema, (data) => pick(data, known));
  return schema;
}

const tabularShape = {
  columns: z.array(z.string()).describe("Column names, in row order."),
  rows: z
    .array(
      z.array(
        z.union([z.string(), integer(), z.number(), z.boolean(), z.null()]),
      ),
    )
    .describe("Rows of scalar cells; each row has one cell per column."),
  row_count: integer().describe(
    "Number of rows returned, after any cap; equals len(rows).",
  ),
  truncated: z.boolean().describe(TRUNCATED_DESCRIPTION),
  column_kinds: z
    .array(z.enum(COLUMN_KINDS))
    .nullable()
    .default(null)
    .describe(
      "Optional per-column kind, one per column, from COLUMN_KINDS: text, " +
        "number, integer, boolean, timestamp (RFC 3339 date-time), ip (v4 or " +
        "v6), fqdn, mac, ip_block (address, CIDR prefix or first-last range), " +
        "big_integer (integer, or a decimal string beyond 2^53 - 1).",
    ),
  column_scales: z
    .array(z.enum(COLUMN_SCALES).nullable())
    .nullable()
    .default(null)
    .describe(
      "Optional per-column chart scale hint, one per column, from " +
        "COLUMN_SCALES: linear, log10, log2; only on number, integer and " +
        "big_integer columns, null for no hint.",
    ),
  column_descriptions: z
    .array(z.string().nullable())
    .nullable()
    .default(null)
    .describe(
      "One short description per column, in column order; null where a " +
        "column has none.",
    ),
  ...pagingShape("rows"),
};

type ParsedTabular = z.output<z.ZodObject<typeof tabularShape>>;

/** Return why the scales contradict the columns and their kinds, or null. */
function scalesProblem(value: ParsedTabular): string | null {
  const { columns, column_kinds: kinds, column_scales: scales } = value;
  if (scales === null) {
    return null;
  }
  if (scales.length !== columns.length) {
    return `column_scales has ${String(scales.length)} entries, expected ${String(columns.length)}`;
  }
  for (const [index, scale] of scales.entries()) {
    if (scale === null) {
      continue;
    }
    if (kinds === null) {
      return "column_scales needs column_kinds";
    }
    const kind = kinds[index];
    if (kind === undefined || !NUMERIC_KINDS.includes(kind)) {
      return (
        `column ${JSON.stringify(columns[index])} has scale ${scale} but kind ` +
        `${String(kind)}; scales apply to ${NUMERIC_KINDS.join(", ")}`
      );
    }
  }
  return null;
}

/** Return why a tabular envelope contradicts itself, or null. */
function tabularProblem(value: ParsedTabular): string | null {
  const width = value.columns.length;
  if (value.rows.length !== value.row_count) {
    return (
      `row_count ${String(value.row_count)} does not match the ` +
      `${String(value.rows.length)} rows returned`
    );
  }
  for (const [index, row] of value.rows.entries()) {
    if (row.length !== width) {
      return `row ${String(index)} has ${String(row.length)} cells, expected ${String(width)}`;
    }
  }
  const kinds = value.column_kinds;
  if (kinds !== null && kinds.length !== width) {
    return `column_kinds has ${String(kinds.length)} entries, expected ${String(width)}`;
  }
  const descriptions = value.column_descriptions;
  if (descriptions !== null && descriptions.length !== width) {
    return (
      `column_descriptions has ${String(descriptions.length)} entries, ` +
      `expected ${String(width)}`
    );
  }
  return scalesProblem(value) ?? pagingProblem(value, value.row_count);
}

/** Return the tabular envelope's wire form. */
function dumpTabular(value: ParsedTabular): TabularEnvelope {
  const out: TabularEnvelope = {
    columns: value.columns,
    rows: value.rows,
    row_count: value.row_count,
    truncated: value.truncated,
  };
  if (value.column_kinds !== null) out.column_kinds = value.column_kinds;
  if (value.column_scales !== null) out.column_scales = value.column_scales;
  if (value.column_descriptions !== null) {
    out.column_descriptions = value.column_descriptions;
  }
  return { ...out, ...dumpPaging(value) };
}

/** The tabular envelope schema: strict parse to the wire form. */
export const TabularEnvelope: z.ZodType<TabularEnvelope, TabularEnvelopeInput> =
  z
    .strictObject(tabularShape)
    .superRefine((value, ctx) => {
      report(ctx, tabularProblem(value));
    })
    .transform(dumpTabular)
    .meta({
      id: TABULAR_DEF_NAME,
      description:
        "Columns and rows for results whose shape is only known at run time.",
    });

/** True when `descriptions` is absent or one string-or-null per column. */
function descriptionsFit(descriptions: unknown, columns: unknown): boolean {
  if (descriptions === undefined || descriptions === null) {
    return true;
  }
  return (
    Array.isArray(descriptions) &&
    Array.isArray(columns) &&
    descriptions.length === columns.length &&
    descriptions.every((entry) => entry === null || typeof entry === "string")
  );
}

const TABULAR_KEYS: ReadonlySet<string> = new Set(Object.keys(tabularShape));
const KNOWN_KINDS: ReadonlySet<unknown> = new Set(COLUMN_KINDS);
const KNOWN_SCALES: ReadonlySet<unknown> = new Set(COLUMN_SCALES);

TOLERATE.set(TabularEnvelope, (raw) => {
  const data = pick(raw, TABULAR_KEYS);
  if (!descriptionsFit(data["column_descriptions"], data["columns"])) {
    delete data["column_descriptions"];
  }
  let kinds = data["column_kinds"];
  if (Array.isArray(kinds)) {
    kinds = kinds.map((kind: unknown) =>
      typeof kind === "string" && !KNOWN_KINDS.has(kind)
        ? COLUMN_KIND_FALLBACK
        : kind,
    );
    data["column_kinds"] = kinds;
  }
  const scales = data["column_scales"];
  if (Array.isArray(scales)) {
    const numeric = (index: number): boolean =>
      Array.isArray(kinds) &&
      index < kinds.length &&
      NUMERIC_KINDS.includes(kinds[index] as string);
    data["column_scales"] = scales.map((scale: unknown, index) =>
      typeof scale !== "string" || (KNOWN_SCALES.has(scale) && numeric(index))
        ? scale
        : COLUMN_SCALE_FALLBACK,
    );
  }
  return data;
});

const artifactRefShape = {
  reference: z
    .string()
    .describe(
      "Reference the caller can cite: the path or id the sink returned.",
    ),
  media_type: z.string().describe("IANA media type, e.g. 'image/svg+xml'."),
  bytes: integer().describe("Size of the artifact in bytes."),
  width: integer()
    .nullable()
    .default(null)
    .describe("Pixel width when the artifact is an image; omitted otherwise."),
  height: integer()
    .nullable()
    .default(null)
    .describe("Pixel height when the artifact is an image; omitted otherwise."),
  role: z
    .string()
    .nullable()
    .default(null)
    .describe("What the artifact is to the run, such as csv, plan or summary."),
};

const ARTIFACT_REF_KEYS: ReadonlySet<string> = new Set(
  Object.keys(artifactRefShape),
);

/** The artifact reference schema: strict parse to the wire form. */
export const ArtifactRef: z.ZodType<ArtifactRef, ArtifactRefInput> = z
  .strictObject(artifactRefShape)
  .transform((value): ArtifactRef => {
    const out: ArtifactRef = {
      reference: value.reference,
      media_type: value.media_type,
      bytes: value.bytes,
    };
    if (value.width !== null) out.width = value.width;
    if (value.height !== null) out.height = value.height;
    if (value.role !== null) out.role = value.role;
    return out;
  })
  .meta({
    id: "ArtifactRef",
    description: "Where one produced artifact lives and what it is.",
  });

const artifactShape = {
  artifact: ArtifactRef.describe("The primary artifact produced."),
  artifacts: z
    .array(ArtifactRef)
    .optional()
    .describe("Further artifacts produced alongside the primary, if any."),
  warnings: z.array(z.string()).optional().describe(WARNINGS_DESCRIPTION),
  sensitivity: z
    .literal(SENSITIVITIES)
    .default("inherits_input")
    .describe(
      "Per-field extras cannot annotate a file, so the artifact is treated " +
        "as containing every input column.",
    ),
};

/** The artifact envelope schema: strict parse to the wire form. */
export const ArtifactEnvelope: z.ZodType<
  ArtifactEnvelope,
  ArtifactEnvelopeInput
> = z
  .strictObject(artifactShape)
  .transform((value): ArtifactEnvelope => ({
    artifact: value.artifact,
    artifacts: value.artifacts ?? [],
    warnings: value.warnings ?? [],
    sensitivity: value.sensitivity,
  }))
  .meta({
    id: "ArtifactEnvelope",
    description:
      "Result of a tool that produces a file rather than data to read.",
  });

const ARTIFACT_KEYS: ReadonlySet<string> = new Set(Object.keys(artifactShape));
const KNOWN_SENSITIVITIES: ReadonlySet<unknown> = new Set(SENSITIVITIES);

TOLERATE.set(ArtifactEnvelope, (raw) => {
  const data = pick(raw, ARTIFACT_KEYS);
  if ("artifact" in data) {
    data["artifact"] = dropUnknown(data["artifact"], ARTIFACT_REF_KEYS);
  }
  const artifacts = data["artifacts"];
  if (Array.isArray(artifacts)) {
    data["artifacts"] = artifacts.map((entry: unknown) =>
      dropUnknown(entry, ARTIFACT_REF_KEYS),
    );
  }
  const sensitivity = data["sensitivity"];
  if (
    typeof sensitivity === "string" &&
    !KNOWN_SENSITIVITIES.has(sensitivity)
  ) {
    data["sensitivity"] = SENSITIVITY_FALLBACK;
  }
  return data;
});

const UTF8 = new TextDecoder("utf-8", { fatal: true });

/**
 * Parse an envelope another process produced, tolerating newer additions.
 *
 * `model` is {@link TabularEnvelope}, {@link ArtifactEnvelope} or a schema
 * {@link RecordsEnvelope} returned; any other schema is a `TypeError`.
 * `data` is the decoded object, or JSON text as a string or UTF-8 bytes
 * (malformed text raises `SyntaxError`). Unknown keys are dropped at the
 * envelope level and in nested artifact references, but not inside
 * `records`, whose item schema decides for itself. An unknown value in a
 * vocabulary reads as its `VOCABULARY_FALLBACKS` entry, and a scale on a
 * column that is not numeric reads as `null`. Every other check still runs
 * and raises `ZodError`.
 *
 * Bytes are decoded as UTF-8, the JSON wire encoding; Python's reader also
 * detects UTF-16 and UTF-32.
 */
export function readEnvelope<O>(model: z.ZodType<O>, data: unknown): O {
  const tolerate = TOLERATE.get(model);
  if (tolerate === undefined) {
    throw new TypeError("readEnvelope needs an octools envelope schema");
  }
  let parsed: unknown = data;
  if (typeof data === "string") {
    parsed = JSON.parse(data);
  } else if (data instanceof Uint8Array) {
    parsed = JSON.parse(UTF8.decode(data));
  }
  return model.parse(isObject(parsed) ? tolerate(parsed) : parsed);
}

// A parse's output is the wire shape a parse accepts with unset optional
// fields left out, so outputSchemaFor's input side is the published contract.

/** Return the output schema of a records envelope over `item` records. */
export function recordsSchema(item: z.ZodType): JsonSchema {
  return outputSchemaFor(RecordsEnvelope(item));
}

/** Return the shared tabular envelope schema (the published `$ref` target). */
export function tabularSchema(): JsonSchema {
  return outputSchemaFor(TabularEnvelope);
}

/** Return the artifact envelope schema. */
export function artifactSchema(): JsonSchema {
  return outputSchemaFor(ArtifactEnvelope);
}
