/**
 * Cell-level check of a `TabularEnvelope`, and building one from a schema.
 *
 * Parsing an envelope checks the kind vocabulary, never a cell's content.
 * {@link validateTabular} is the opt-in content check a producer runs in
 * its own tests (`expect(validateTabular(envelope)).toEqual([])`). It
 * reports at most one finding per column, so it stays bounded on a table of
 * any size.
 *
 * JSON does not distinguish `1` from `1.0` once parsed into a JavaScript
 * number, so an integral number cell fits the `integer` and `big_integer`
 * kinds however it was written. Python keeps `1.0` a float, which fits
 * neither.
 *
 * {@link tabularFromModels} builds a table from a zod object schema, so every
 * producer maps a field's type to a column kind the same way.
 *
 * @module
 */
import * as z from "zod";

import { type Cell, TabularEnvelope } from "./envelopes.js";
import { OCToolError } from "./errors.js";
import { Finding } from "./findings.js";
import {
  isAtOrBefore,
  isIpNetwork,
  parseIpAddress,
} from "./internal/ipaddress.js";
import type { ColumnKind } from "./vocabulary.js";

const TIMESTAMP_RE =
  /^([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]+)?([Zz]|[+-]([0-9]{2}):([0-9]{2}))$/;
const LABEL_RE = /^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/;
const MAC_RE = /^[0-9A-Fa-f]{2}([:-])[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){4}$/;
const MAC_LONG_RE = /^[0-9A-Fa-f]{2}([:-])[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){6}$/;
const BIG_INTEGER_RE = /^-?(0|[1-9][0-9]*)$/;

function isNumber(cell: Cell): cell is number {
  return typeof cell === "number" && Number.isFinite(cell);
}

function isInt(cell: Cell): boolean {
  return isNumber(cell) && Number.isInteger(cell);
}

/** An integer a JSON number carries exactly: at most 2^53 - 1 in magnitude. */
function isInteger(cell: Cell): boolean {
  return isNumber(cell) && Number.isSafeInteger(cell);
}

/** Days in `month` (1-12) of `year` in the proleptic Gregorian calendar. */
function daysIn(year: number, month: number): number {
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  if (month === 2) {
    return leap ? 29 : 28;
  }
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

/** An RFC 3339 `date-time` string with a real date, time and offset. */
function isTimestamp(cell: Cell): boolean {
  const match = typeof cell === "string" ? TIMESTAMP_RE.exec(cell) : null;
  if (match === null) {
    return false;
  }
  const at = (group: number): number => Number(match[group] ?? 0);
  const [year, month, day] = [at(1), at(2), at(3)];
  return (
    year >= 1 &&
    month >= 1 &&
    month <= 12 &&
    day >= 1 &&
    day <= daysIn(year, month) &&
    at(4) <= 23 &&
    at(5) <= 59 &&
    at(6) <= 59 &&
    at(9) <= 23 &&
    at(10) <= 59
  );
}

function isIp(cell: Cell): boolean {
  return typeof cell === "string" && parseIpAddress(cell) !== null;
}

/** Dot-separated host labels, at most 253 characters; one final dot allowed. */
function isFqdn(cell: Cell): boolean {
  if (typeof cell !== "string") {
    return false;
  }
  const name = cell.endsWith(".") ? cell.slice(0, -1) : cell;
  return (
    name.length > 0 &&
    name.length <= 253 &&
    name.split(".").every((label) => LABEL_RE.test(label))
  );
}

/** Six or eight hex pairs joined consistently by `:` or `-`. */
function isMac(cell: Cell): boolean {
  return (
    typeof cell === "string" && (MAC_RE.test(cell) || MAC_LONG_RE.test(cell))
  );
}

/** An address, a CIDR prefix, or a `first-last` range of one version. */
function isIpBlock(cell: Cell): boolean {
  if (typeof cell !== "string") {
    return false;
  }
  if (cell.includes("/")) {
    return isIpNetwork(cell);
  }
  const dash = cell.indexOf("-");
  if (dash >= 0) {
    const first = parseIpAddress(cell.slice(0, dash));
    const last = parseIpAddress(cell.slice(dash + 1));
    return (
      first !== null &&
      last !== null &&
      first.version === last.version &&
      isAtOrBefore(first, last)
    );
  }
  return parseIpAddress(cell) !== null;
}

/** An integer, or a string of decimal digits with an optional `-`. */
function isBigInteger(cell: Cell): boolean {
  return isInt(cell) || (typeof cell === "string" && BIG_INTEGER_RE.test(cell));
}

/** One cell predicate per `ColumnKind`; `null` cells never reach them. */
const CHECKS: Readonly<Record<ColumnKind, (cell: Cell) => boolean>> = {
  text: (cell) => typeof cell === "string",
  number: isNumber,
  integer: isInteger,
  boolean: (cell) => typeof cell === "boolean",
  timestamp: isTimestamp,
  ip: isIp,
  fqdn: isFqdn,
  mac: isMac,
  ip_block: isIpBlock,
  big_integer: isBigInteger,
};

/**
 * Report each column holding a cell that does not fit its declared kind.
 *
 * Returns `[]` when `column_kinds` is absent. A `null` cell always fits.
 * Each failing column yields one `cell_kind` finding, in column order,
 * whose `path` points at the first bad cell (`/rows/3/2`) and whose message
 * counts the bad cells and quotes the first. `tool` is `null`; a caller may
 * build a copy with it set.
 */
export function validateTabular(envelope: TabularEnvelope): Finding[] {
  const kinds = envelope.column_kinds;
  if (kinds === undefined) {
    return [];
  }
  const findings: Finding[] = [];
  const total = envelope.rows.length;
  for (const [column, kind] of kinds.entries()) {
    const fits = CHECKS[kind];
    let first: number | null = null;
    let firstCell: Cell = null;
    let bad = 0;
    for (const [index, row] of envelope.rows.entries()) {
      const cell = row[column] as Cell;
      if (cell !== null && !fits(cell)) {
        bad += 1;
        if (first === null) {
          first = index;
          firstCell = cell;
        }
      }
    }
    if (first !== null) {
      const name = JSON.stringify(envelope.columns[column]);
      findings.push(
        new Finding({
          rule: "cell_kind",
          message:
            `column ${name} (${kind}): ${String(bad)} of ${String(total)} cells do ` +
            `not fit; first at row ${String(first)}: ${JSON.stringify(firstCell)}`,
          path: `/rows/${String(first)}/${String(column)}`,
        }),
      );
    }
  }
  return findings;
}

/** Return the kind of one literal or enum value. */
function valueKind(value: unknown): ColumnKind {
  if (typeof value === "boolean") {
    return "boolean";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? "integer" : "number";
  }
  return "text";
}

/** Return the kind every value shares, or text when they differ. */
function valuesKind(values: Iterable<unknown>): ColumnKind {
  const [kind, ...others] = new Set([...values].map(valueKind));
  return others.length === 0 ? (kind ?? "text") : "text";
}

/** Return a field with its optional, nullable and default wrappers removed. */
function unwrapped(field: z.ZodType): {
  inner: z.ZodType;
  description: string | undefined;
} {
  let inner = field;
  let description = field.description;
  while (
    inner instanceof z.ZodOptional ||
    inner instanceof z.ZodNullable ||
    inner instanceof z.ZodDefault ||
    inner instanceof z.ZodPrefault
  ) {
    inner = inner.def.innerType as z.ZodType;
    description ??= inner.description;
  }
  return { inner, description };
}

/** Return the column kind of an unwrapped field; anything unknown is text. */
function columnKind(field: z.ZodType): ColumnKind {
  if (field instanceof z.ZodBoolean) {
    return "boolean";
  }
  if (field instanceof z.ZodNumber) {
    return (field.format ?? "").includes("int") ? "integer" : "number";
  }
  if (field instanceof z.ZodDate) {
    return "timestamp";
  }
  if (field instanceof z.ZodISODateTime) {
    return field._zod.def.local ? "text" : "timestamp";
  }
  if (field instanceof z.ZodIPv4 || field instanceof z.ZodIPv6) {
    return "ip";
  }
  if (field instanceof z.ZodCIDRv4 || field instanceof z.ZodCIDRv6) {
    return "ip_block";
  }
  if (field instanceof z.ZodEnum) {
    return valuesKind(field.options);
  }
  if (field instanceof z.ZodLiteral) {
    return valuesKind(field.values);
  }
  return "text";
}

/** Return a dumped value as a cell; an array or object is compact JSON text. */
function modelCell(value: unknown): Cell {
  if (typeof value === "object" && value !== null) {
    return JSON.stringify(value);
  }
  return (value ?? null) as Cell;
}

/** Options {@link tabularFromModels} takes. */
export interface TabularFromModelsOptions {
  /** Kinds overriding the inferred ones, by column. */
  readonly columnKinds?: Readonly<Record<string, ColumnKind>> | undefined;
}

/**
 * Return `items` as one complete table with `schema`'s fields as columns.
 *
 * Columns are the fields in declaration order. Each kind comes from the
 * field's schema, optional, nullable and default wrappers removed: a date or
 * a `z.iso.datetime()` that requires an offset is `timestamp`; `z.ipv4()` or
 * `z.ipv6()` is `ip`, `z.cidrv4()` or `z.cidrv6()` is `ip_block`; an enum or
 * literal takes the kind its values share; anything else is `text`, and an
 * array or object is compact JSON text. `columnKinds` overrides per column,
 * which is how a column becomes `big_integer` or `fqdn`; a key that is not a
 * column throws {@link OCToolError}. Field descriptions fill
 * `column_descriptions` when any field has one.
 */
export function tabularFromModels(
  schema: z.ZodObject,
  items: Iterable<unknown>,
  options: TabularFromModelsOptions = {},
): TabularEnvelope {
  const fields = Object.entries(schema.shape as Record<string, z.ZodType>).map(
    ([name, field]) => ({ name, ...unwrapped(field) }),
  );
  const columns = fields.map((field) => field.name);
  const overrides = options.columnKinds ?? {};
  const unknown = Object.keys(overrides)
    .filter((name) => !columns.includes(name))
    .sort();
  if (unknown.length > 0) {
    throw new OCToolError(
      `columnKinds names unknown columns: ${unknown.join(", ")}`,
    );
  }
  const rows = [...items].map((item) => {
    const dump = JSON.parse(JSON.stringify(item)) as Record<string, unknown>;
    return columns.map((name) => modelCell(dump[name]));
  });
  const descriptions = fields.map((field) => field.description ?? null);
  return TabularEnvelope.parse({
    columns,
    rows,
    row_count: rows.length,
    truncated: false,
    column_kinds: fields.map(
      (field) => overrides[field.name] ?? columnKind(field.inner),
    ),
    column_descriptions: descriptions.some((entry) => entry !== null)
      ? descriptions
      : null,
  });
}
