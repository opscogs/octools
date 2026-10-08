/**
 * Human-readable listings of a tool provider: table, Markdown, text and JSON.
 *
 * {@link summarizeTool} flattens a tool into a {@link ToolSummary} a person
 * or a CLI can read without the callable or the full schemas;
 * {@link renderListing} renders a provider's summaries in one of the
 * `LISTING_STYLES`. Output is byte for byte what the Python implementation
 * renders.
 *
 * @module
 */
import {
  dumps,
  fill,
  ljust,
  pyLen,
  rstrip,
  SENTENCE_RE,
  splitlines,
  str,
  strip,
} from "./internal/pytext.js";
import {
  type Access,
  ALIAS_OF_KEY,
  LISTING_STYLES,
  type ListingStyle,
  type ResultKind,
} from "./vocabulary.js";

/** The descriptor fields a listing reads; every `OCTool` has them. */
export interface ListedTool {
  readonly name: string;
  readonly title?: string | null | undefined;
  readonly description: string;
  readonly access: Access;
  readonly target?: string | null | undefined;
  readonly resultKind: ResultKind;
  readonly readOnlyHint: boolean;
  readonly destructiveHint: boolean;
  readonly idempotentHint: boolean;
  readonly inputSchema: Readonly<Record<string, unknown>>;
  readonly deprecated: boolean;
  readonly meta: Readonly<Record<string, unknown>>;
}

/** Anything that lists its tools in a fixed order; every `ToolProvider` is one. */
export interface ListedToolProvider {
  allTools(): Iterable<ListedTool>;
}

/** One input as a JSON-ready row. */
export interface InputSummaryRow {
  name: string;
  type: string;
  required: boolean;
  description: string | null;
}

/** A {@link ToolSummary} as a JSON-ready row, spelled as the wire spells it. */
export interface ToolSummaryRow {
  name: string;
  title: string | null;
  summary: string;
  description: string;
  access: Access;
  target: string | null;
  result_kind: ResultKind;
  read_only: boolean;
  destructive: boolean;
  idempotent: boolean;
  pages: boolean;
  deprecated: boolean;
  alias_of: string | null;
  inputs: InputSummaryRow[];
}

/** One top-level argument of a tool: name, rendered type, requiredness. */
export class InputSummary {
  /** The property name. */
  readonly name: string;
  /** A short rendered type, such as `string|null` or `enum(a|b)`. */
  readonly type: string;
  /** Whether the schema's `required` lists the property. */
  readonly required: boolean;
  /** The property's `description` when it is a string, else `null`. */
  readonly description: string | null;

  /** Build a frozen input summary. */
  constructor(init: InputSummaryRow) {
    this.name = init.name;
    this.type = init.type;
    this.required = init.required;
    this.description = init.description;
    Object.freeze(this);
  }

  /** Return a JSON-ready plain object. */
  asRow(): InputSummaryRow {
    return {
      name: this.name,
      type: this.type,
      required: this.required,
      description: this.description,
    };
  }
}

/** The listing-relevant facts of one tool, without func or schemas. */
export class ToolSummary {
  readonly name: string;
  readonly title: string | null;
  /** The description's first sentence. */
  readonly summary: string;
  readonly description: string;
  readonly access: Access;
  readonly target: string | null;
  readonly resultKind: ResultKind;
  readonly readOnly: boolean;
  readonly destructive: boolean;
  readonly idempotent: boolean;
  /** Whether the input schema takes a `cursor`. */
  readonly pages: boolean;
  readonly deprecated: boolean;
  /** The replacement a deprecated alias names in its `meta`, else `null`. */
  readonly aliasOf: string | null;
  readonly inputs: readonly InputSummary[];

  /** Build a frozen summary from its row. */
  constructor(row: ToolSummaryRow) {
    this.name = row.name;
    this.title = row.title;
    this.summary = row.summary;
    this.description = row.description;
    this.access = row.access;
    this.target = row.target;
    this.resultKind = row.result_kind;
    this.readOnly = row.read_only;
    this.destructive = row.destructive;
    this.idempotent = row.idempotent;
    this.pages = row.pages;
    this.deprecated = row.deprecated;
    this.aliasOf = row.alias_of;
    this.inputs = Object.freeze(
      row.inputs.map((item) => new InputSummary(item)),
    );
    Object.freeze(this);
  }

  /** Return a JSON-ready flat object; `inputs` is a list of plain objects. */
  asRow(): ToolSummaryRow {
    return {
      name: this.name,
      title: this.title,
      summary: this.summary,
      description: this.description,
      access: this.access,
      target: this.target,
      result_kind: this.resultKind,
      read_only: this.readOnly,
      destructive: this.destructive,
      idempotent: this.idempotent,
      pages: this.pages,
      deprecated: this.deprecated,
      alias_of: this.aliasOf,
      inputs: this.inputs.map((item) => item.asRow()),
    };
  }
}

const MD_COLUMNS = [
  "name",
  "access",
  "mode",
  "result_kind",
  "pages",
  "deprecated",
  "summary",
] as const;
const INPUT_COLUMNS = ["name", "type", "required", "description"] as const;
const WRAP_WIDTH = 88;
const ENUM_WIDTH = 40;

function isObject(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Return `destructive`, `write` or `read` from the safety hints. */
function mode(summary: ToolSummary): string {
  if (summary.destructive) {
    return "destructive";
  }
  return summary.readOnly ? "read" : "write";
}

/** Return `text` up to and including its first sentence end, stripped. */
function firstSentence(text: string): string {
  const stripped = strip(text);
  const match = SENTENCE_RE.exec(stripped);
  return match
    ? strip(stripped.slice(0, match.index + match[0].length))
    : stripped;
}

/** Render `anyOf` / `oneOf` members as their types joined with `|`. */
function membersType(members: unknown): string {
  if (!Array.isArray(members)) {
    return "any";
  }
  return members.map(schemaType).join("|") || "any";
}

/** Render one `enum` or `const` value: strings bare, others as JSON. */
function value(item: unknown): string {
  return typeof item === "string" ? item : dumps(item);
}

/** Render `enum(a|b)`, cut to the values fitting in 40 characters. */
function enumType(values: unknown): string {
  if (!Array.isArray(values)) {
    return "enum";
  }
  const shown: string[] = [];
  for (const text of values.map(value)) {
    if (pyLen([...shown, text].join("|")) > ENUM_WIDTH) {
      return `enum(${[...shown, "..."].join("|")})`;
    }
    shown.push(text);
  }
  return `enum(${shown.join("|")})`;
}

/** Render a short type name for a JSON Schema property; never throws. */
function schemaType(schema: unknown): string {
  if (!isObject(schema)) {
    return "any";
  }
  if (Object.hasOwn(schema, "enum")) {
    return enumType(schema["enum"]);
  }
  if (Object.hasOwn(schema, "const")) {
    return `const(${value(schema["const"])})`;
  }
  const ref = schema["$ref"];
  if (typeof ref === "string") {
    return ref.slice(ref.lastIndexOf("/") + 1);
  }
  for (const key of ["anyOf", "oneOf"]) {
    if (Object.hasOwn(schema, key)) {
      return membersType(schema[key]);
    }
  }
  const kind = schema["type"];
  if (Array.isArray(kind)) {
    return kind.map(str).join("|");
  }
  if (kind === "array" && Object.hasOwn(schema, "items")) {
    return `array[${schemaType(schema["items"])}]`;
  }
  return typeof kind === "string" ? kind : "any";
}

/** Summarize the top-level `properties` of an input schema, in order. */
function inputs(schema: Readonly<Record<string, unknown>>): InputSummaryRow[] {
  const properties = schema["properties"];
  if (!isObject(properties)) {
    return [];
  }
  const required = schema["required"];
  const names: readonly unknown[] = Array.isArray(required) ? required : [];
  return Object.entries(properties).map(([name, prop]) => {
    const description = isObject(prop) ? prop["description"] : undefined;
    return {
      name,
      type: schemaType(prop),
      required: names.includes(name),
      description: typeof description === "string" ? description : null,
    };
  });
}

/** Return whether the input schema's properties include `cursor`. */
function hasCursor(schema: Readonly<Record<string, unknown>>): boolean {
  const properties = schema["properties"];
  return isObject(properties) && Object.hasOwn(properties, "cursor");
}

/** Flatten one tool into the facts a listing shows. */
export function summarizeTool(tool: ListedTool): ToolSummary {
  const alias = tool.meta[ALIAS_OF_KEY];
  return new ToolSummary({
    name: tool.name,
    title: tool.title ?? null,
    summary: firstSentence(tool.description),
    description: tool.description,
    access: tool.access,
    target: tool.target ?? null,
    result_kind: tool.resultKind,
    read_only: tool.readOnlyHint,
    destructive: tool.destructiveHint,
    idempotent: tool.idempotentHint,
    pages: hasCursor(tool.inputSchema),
    deprecated: tool.deprecated,
    alias_of: typeof alias === "string" && alias !== "" ? alias : null,
    inputs: inputs(tool.inputSchema),
  });
}

/** The tool filter {@link summarizeProvider} takes. */
export interface SummarizeOptions {
  /** Keep only tools with this `access`; `null` or absent keeps all. */
  readonly access?: Access | null | undefined;
}

/** Summarize `provider.allTools()` in order, keeping only `access` if set. */
export function summarizeProvider(
  provider: ListedToolProvider,
  options: SummarizeOptions = {},
): ToolSummary[] {
  const { access } = options;
  return [...provider.allTools()]
    .filter((tool) => access == null || tool.access === access)
    .map(summarizeTool);
}

/** Render one cell as one line: yes/no for booleans, blank for null. */
function plain(cell: unknown): string {
  let text: string;
  if (typeof cell === "boolean") {
    text = cell ? "yes" : "no";
  } else if (cell === null || cell === undefined) {
    text = "";
  } else {
    text = str(cell);
  }
  return splitlines(text).join(" ");
}

/** Pad every column but the last to its width, with two-space gutters. */
function aligned(rows: readonly (readonly string[])[]): string[] {
  const widths: number[] = [];
  for (const row of rows) {
    for (const [index, cell] of row.slice(0, -1).entries()) {
      widths[index] = Math.max(widths[index] ?? 0, pyLen(cell));
    }
  }
  return rows.map((row) =>
    row.map((cell, index) => ljust(cell, widths[index] ?? 0)).join("  "),
  );
}

/**
 * Render `rows` as a padded GitHub Markdown table over `columns`.
 *
 * A boolean renders as `yes` / `no` and a missing or `null` value as an
 * empty cell; other values render as Python's `str` would. A pipe is
 * escaped and line breaks become spaces. The result ends with a newline;
 * no rows gives the header and dash rows only.
 */
export function renderMarkdownTable(
  rows: readonly Readonly<Record<string, unknown>>[],
  columns: readonly string[],
): string {
  const cells = rows.map((row) =>
    columns.map((column) =>
      plain(Object.hasOwn(row, column) ? row[column] : null).replaceAll(
        "|",
        "\\|",
      ),
    ),
  );
  const widths = columns.map((column, index) =>
    Math.max(
      pyLen(column),
      3,
      ...cells.map((line) => pyLen(String(line[index]))),
    ),
  );
  const line = (values: readonly string[]): string =>
    `| ${values.map((text, index) => ljust(text, Number(widths[index]))).join(" | ")} |`;
  const lines = [
    line(columns),
    line(widths.map((width) => "-".repeat(width))),
    ...cells.map(line),
  ];
  return lines.join("\n") + "\n";
}

/** Return the summary with a deprecation marker when the tool has one. */
function tableSummary(summary: ToolSummary): string {
  if (!summary.deprecated) {
    return summary.summary;
  }
  const marker = summary.aliasOf
    ? `deprecated; use ${summary.aliasOf}`
    : "deprecated";
  return `${summary.summary} [${marker}]`;
}

/** Render one padded line per tool: name, access, mode and summary. */
function renderTable(summaries: readonly ToolSummary[]): string {
  if (summaries.length === 0) {
    return "";
  }
  const rows = summaries.map((s) => [
    s.name,
    s.access,
    mode(s),
    tableSummary(s),
  ]);
  return aligned(rows)
    .map((line) => `${line}\n`)
    .join("");
}

/** Render one tool as a header line followed by indented facts. */
function txtBlock(summary: ToolSummary): string {
  const header = summary.name + (summary.title ? ` - ${summary.title}` : "");
  const hints = [summary.readOnly ? "read-only" : "writes"];
  if (summary.destructive) {
    hints.push("destructive");
  }
  if (summary.idempotent) {
    hints.push("idempotent");
  }
  if (summary.pages) {
    hints.push("pages");
  }
  const lines = [
    header,
    fill(summary.description, WRAP_WIDTH, "  "),
    `  access: ${summary.access}  target: ${(summary.target === "" ? null : summary.target) ?? "-"}  ` +
      `result: ${summary.resultKind}`,
    `  hints: ${hints.join(", ")}`,
  ];
  if (summary.deprecated) {
    lines.push(
      summary.aliasOf
        ? `  deprecated: use ${summary.aliasOf}`
        : "  deprecated: yes",
    );
  }
  if (summary.inputs.length > 0) {
    const rows: (readonly string[])[] = [INPUT_COLUMNS];
    for (const item of summary.inputs) {
      const row = item.asRow();
      rows.push(INPUT_COLUMNS.map((column) => plain(row[column])));
    }
    lines.push("  inputs:");
    lines.push(...aligned(rows).map((line) => rstrip(`    ${line}`)));
  } else {
    lines.push("  inputs: none");
  }
  return lines.join("\n") + "\n";
}

/** How {@link renderListing} renders and filters. */
export interface RenderListingOptions extends SummarizeOptions {
  /** One of `LISTING_STYLES`; `table` when absent. */
  readonly style?: ListingStyle | undefined;
  /** For `json` only: indented when true (the default), else compact. */
  readonly pretty?: boolean | undefined;
}

/**
 * Render a provider's tools in `style`, keeping only `access` if set.
 *
 * Throws `RangeError` for a style outside `LISTING_STYLES`. Output ends
 * with a newline, except an empty listing is `""` for `table` and `txt`;
 * `md` then renders the header and divider, `json` `[]`. `pretty` affects
 * `json` only: indented when true, else compact. JSON escapes non-ASCII
 * characters as `\uXXXX`.
 */
export function renderListing(
  provider: ListedToolProvider,
  options: RenderListingOptions = {},
): string {
  const { style = "table", pretty = true } = options;
  if (!(LISTING_STYLES as readonly string[]).includes(style)) {
    const allowed = LISTING_STYLES.map((name) => `'${name}'`).join(", ");
    throw new RangeError(
      `style must be one of (${allowed}), got ${JSON.stringify(style)}`,
    );
  }
  const summaries = summarizeProvider(provider, options);
  switch (style) {
    case "table":
      return renderTable(summaries);
    case "md":
      return renderMarkdownTable(
        summaries.map((s) => ({ ...s.asRow(), mode: mode(s) })),
        MD_COLUMNS,
      );
    case "txt":
      return summaries.map(txtBlock).join("\n");
    case "json": {
      const rows = summaries.map((s) => s.asRow());
      return (
        (pretty
          ? dumps(rows, { indent: 2 })
          : dumps(rows, { separators: [",", ":"] })) + "\n"
      );
    }
  }
}
