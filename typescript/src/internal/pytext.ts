/**
 * Text operations with the exact semantics of the Python standard library,
 * so rendered output matches the Python implementation byte for byte.
 *
 * Lengths and padding count code points, as Python's `len` does, not UTF-16
 * units. Whitespace is Python's `str.isspace` set, which is also what `\s`
 * matches in a Python `str` pattern; it differs from JavaScript's `\s`.
 * Python's `\w` is a letter, a number or `_` (categories `L*`, `N*`), and
 * `\d` is category `Nd`.
 *
 * @module
 */

/** The characters Python's `str.isspace` accepts, as a regex class body. */
const WS =
  "\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const LEADING_WS = new RegExp(`^[${WS}]+`, "u");
const TRAILING_WS = new RegExp(`[${WS}]+$`, "u");
/** Python's `str.splitlines` boundaries; `\r\n` counts as one. */
const BREAKS = "\\n\\v\\f\\r\\x1c-\\x1e\\x85\\u2028\\u2029";
const LINE_BREAK = new RegExp(`\\r\\n|[${BREAKS}]`, "gu");

/**
 * A run of sentence-ending punctuation followed by whitespace or the end of
 * the text; `count_sentences` counts its matches in the stripped text.
 */
export const SENTENCE_RE = new RegExp(`[.!?]+(?=[${WS}]|$)`, "u");

const SURROGATE_PAIR = /[\ud800-\udbff][\udc00-\udfff]/g;

/** Return the length of `text` in code points, as Python's `len`. */
export function pyLen(text: string): number {
  return text.length - (text.match(SURROGATE_PAIR)?.length ?? 0);
}

/** Return `text` padded with spaces on the right to `width` code points. */
export function ljust(text: string, width: number): string {
  return text + " ".repeat(Math.max(0, width - pyLen(text)));
}

/** Return `text` without trailing Python whitespace (`str.rstrip`). */
export function rstrip(text: string): string {
  return text.replace(TRAILING_WS, "");
}

/** Return `text` without leading or trailing Python whitespace (`str.strip`). */
export function strip(text: string): string {
  return rstrip(text.replace(LEADING_WS, ""));
}

/** Split `text` at line boundaries as Python's `str.splitlines()` does. */
export function splitlines(text: string): string[] {
  const lines = text.split(LINE_BREAK);
  if (lines.at(-1) === "") {
    lines.pop();
  }
  return lines;
}

/** Expand tabs to the next multiple of 8 columns (`str.expandtabs()`). */
function expandTabs(text: string): string {
  let out = "";
  let column = 0;
  for (const char of text) {
    if (char === "\t") {
      const pad = 8 - (column % 8);
      out += " ".repeat(pad);
      column += pad;
    } else {
      out += char;
      column = char === "\n" || char === "\r" ? 0 : column + 1;
    }
  }
  return out;
}

const WORD = "[\\p{L}\\p{N}_]";
const WORD_PUNCT = "[\\p{L}\\p{N}_!\"'&.,?]";
const LETTER = "[\\p{L}\\p{Nl}\\p{No}_]";
const WRAP_WS = "[\\t\\n\\v\\f\\r ]";
const WRAP_NWS = "[^\\t\\n\\v\\f\\r ]";
/** `textwrap.TextWrapper.wordsep_re`: the chunks a line may break between. */
const WORDSEP_RE = new RegExp(
  `(${WRAP_WS}+` +
    `|(?<=${WORD_PUNCT})-{2,}(?=${WORD})` +
    `|${WRAP_NWS}+?(?:` +
    `-(?:(?<=${LETTER}{2}-)|(?<=${LETTER}-${LETTER}-))(?=${LETTER}-?${LETTER})` +
    `|(?=${WRAP_WS}|$)` +
    `|(?<=${WORD_PUNCT})(?=-{2,}${WORD})` +
    "))",
  "u",
);

/** Return whether `chunk` is all Python whitespace (`chunk.strip() == ''`). */
function blank(chunk: string): boolean {
  return strip(chunk) === "";
}

/** Return the code points of `text` from `start` to `end`. */
function slice(text: string, start: number, end?: number): string {
  return Array.from(text).slice(start, end).join("");
}

/**
 * Return `text` wrapped as Python's `textwrap.fill(text, width,
 * initial_indent=indent, subsequent_indent=indent)` with every other option
 * at its default: tabs expanded, whitespace replaced, long words broken,
 * breaks on hyphens, whitespace dropped at line edges.
 */
export function fill(text: string, width: number, indent: string): string {
  const munged = expandTabs(text).replace(/[\t\n\v\f\r]/g, " ");
  const chunks = munged
    .split(WORDSEP_RE)
    .filter((chunk) => chunk !== "")
    .reverse();
  const lines: string[] = [];
  const room = width - pyLen(indent);
  let next = chunks.at(-1);
  while (next !== undefined) {
    const line: string[] = [];
    let used = 0;
    if (lines.length > 0 && blank(next)) {
      chunks.pop();
      next = chunks.at(-1);
    }
    while (next !== undefined && used + pyLen(next) <= room) {
      line.push(next);
      used += pyLen(next);
      chunks.pop();
      next = chunks.at(-1);
    }
    if (next !== undefined && pyLen(next) > room) {
      const spaceLeft = room < 1 ? 1 : room - used;
      let end = spaceLeft;
      const hyphen = slice(next, 0, spaceLeft).lastIndexOf("-");
      if (hyphen > 0 && /[^-]/.test(next.slice(0, hyphen))) {
        end = pyLen(next.slice(0, hyphen)) + 1;
      }
      line.push(slice(next, 0, end));
      next = slice(next, end);
      chunks[chunks.length - 1] = next;
    }
    const last = line.at(-1);
    if (last !== undefined && blank(last)) {
      line.pop();
    }
    if (line.length > 0) {
      lines.push(indent + line.join(""));
    }
  }
  return lines.join("\n");
}

/**
 * Return a finite non-integer `value` formatted as Python's `repr(float)`:
 * the shortest round-tripping digits, in exponent form below `1e-4`.
 * Every double of magnitude `1e16` or more is an integer, so the upper
 * exponent form never applies.
 */
function floatRepr(value: number): string {
  const [mantissa = "", exponent = "0"] = Math.abs(value)
    .toExponential()
    .split("e");
  const sign = value < 0 ? "-" : "";
  const digits = mantissa.replace(".", "");
  const exp = Number(exponent);
  if (exp < -4) {
    const rest = digits.length > 1 ? `.${digits.slice(1)}` : "";
    const power = String(-exp).padStart(2, "0");
    return `${sign}${digits.charAt(0)}${rest}e-${power}`;
  }
  if (exp < 0) {
    return `${sign}0.${"0".repeat(-exp - 1)}${digits}`;
  }
  return `${sign}${digits.slice(0, exp + 1)}.${digits.slice(exp + 1)}`;
}

/**
 * Return a number as Python prints a parsed JSON number: an integral value
 * as a Python `int`, any other as a `float` (`nan`, `inf` from `str`,
 * `NaN`, `Infinity` from `json.dumps`). JSON `1.0` parses to the same
 * number as `1`, so it prints as `1`.
 */
function numberText(value: number | bigint, json: boolean): string {
  if (typeof value === "bigint" || Number.isInteger(value)) {
    return BigInt(value).toString();
  }
  if (Number.isNaN(value)) {
    return json ? "NaN" : "nan";
  }
  if (!Number.isFinite(value)) {
    const sign = value < 0 ? "-" : "";
    return sign + (json ? "Infinity" : "inf");
  }
  return floatRepr(value);
}

const JSON_ESCAPES: Readonly<Record<string, string>> = {
  '"': '\\"',
  "\\": "\\\\",
  "\b": "\\b",
  "\f": "\\f",
  "\n": "\\n",
  "\r": "\\r",
  "\t": "\\t",
};

/** Return `text` as a JSON string with `ensure_ascii=True` escaping. */
function jsonString(text: string): string {
  const body = text.replace(
    /[\\"]|[^ -~]/g,
    (char) =>
      JSON_ESCAPES[char] ??
      `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );
  return `"${body}"`;
}

/** The separators and indent of one `json.dumps` call. */
export interface DumpsOptions {
  /** Spaces per nesting level; `undefined` keeps everything on one line. */
  readonly indent?: number;
  /** Between items and between a key and its value. */
  readonly separators?: readonly [string, string];
}

/**
 * Return `value` as Python's `json.dumps(value, ensure_ascii=True, ...)`:
 * non-ASCII escaped as `\uXXXX` (surrogate pairs above the BMP), Python's
 * float formatting, and its default separators (`", "` and `": "`, or `","`
 * and `": "` when indented).
 */
export function dumps(value: unknown, options: DumpsOptions = {}): string {
  const { indent } = options;
  const [item, key] =
    options.separators ?? (indent === undefined ? [", ", ": "] : [",", ": "]);
  const walk = (node: unknown, depth: number): string => {
    if (typeof node === "string") {
      return jsonString(node);
    }
    if (typeof node === "number" || typeof node === "bigint") {
      return numberText(node, true);
    }
    if (typeof node === "boolean") {
      return String(node);
    }
    if (typeof node !== "object" || node === null) {
      return "null";
    }
    const isArray = Array.isArray(node);
    const parts = isArray
      ? node.map((child: unknown) => walk(child, depth + 1))
      : Object.entries(node).map(
          ([name, child]) => jsonString(name) + key + walk(child, depth + 1),
        );
    const [open, close] = isArray ? ["[", "]"] : ["{", "}"];
    if (parts.length === 0) {
      return open + close;
    }
    if (indent === undefined) {
      return open + parts.join(item) + close;
    }
    const inner = "\n" + " ".repeat(indent * (depth + 1));
    const outer = "\n" + " ".repeat(indent * depth);
    return open + inner + parts.join(item + inner) + outer + close;
  };
  return walk(value, 0);
}

/** Characters Python's `str.isprintable` rejects, except the plain space. */
const UNPRINTABLE = /(?! )[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Zl}\p{Zp}\p{Zs}]/u;
const REPR_ESCAPES: Readonly<Record<string, string>> = {
  "\\": "\\\\",
  "\n": "\\n",
  "\r": "\\r",
  "\t": "\\t",
};

/** Return `text` as Python's `repr(str)`. */
function strRepr(text: string): string {
  const quote = text.includes("'") && !text.includes('"') ? '"' : "'";
  let body = "";
  for (const char of text) {
    const point = Number(char.codePointAt(0));
    if (char === quote) {
      body += `\\${char}`;
    } else if (REPR_ESCAPES[char] !== undefined) {
      body += REPR_ESCAPES[char];
    } else if (!UNPRINTABLE.test(char)) {
      body += char;
    } else if (point < 0x100) {
      body += `\\x${point.toString(16).padStart(2, "0")}`;
    } else if (point < 0x10000) {
      body += `\\u${point.toString(16).padStart(4, "0")}`;
    } else {
      body += `\\U${point.toString(16).padStart(8, "0")}`;
    }
  }
  return quote + body + quote;
}

/** Return `value` as Python's `repr` of the equivalent JSON-decoded value. */
function repr(value: unknown): string {
  if (typeof value === "string") {
    return strRepr(value);
  }
  if (typeof value === "boolean") {
    return value ? "True" : "False";
  }
  if (value === null || value === undefined) {
    return "None";
  }
  return str(value);
}

/**
 * Return `value` as Python's `str` of the equivalent JSON-decoded value:
 * a string unchanged, a number as `int` or `float`, a list or an object as
 * its `repr`.
 */
export function str(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "bigint") {
    return numberText(value, false);
  }
  if (Array.isArray(value)) {
    return `[${value.map(repr).join(", ")}]`;
  }
  if (typeof value === "object" && value !== null) {
    const items = Object.entries(value).map(
      ([key, child]) => `${strRepr(key)}: ${repr(child)}`,
    );
    return `{${items.join(", ")}}`;
  }
  return repr(value);
}
