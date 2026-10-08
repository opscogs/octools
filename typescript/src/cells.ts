/**
 * Cell-level check of a `TabularEnvelope` against its `column_kinds`.
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
 * @module
 */
import type { Cell, TabularEnvelope } from "./envelopes.js";
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
