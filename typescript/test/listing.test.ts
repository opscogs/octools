/** Listings agree with the Python implementation beyond the spec fixtures. */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  InputSummary,
  type ListedTool,
  ToolSummary,
  renderListing,
  renderMarkdownTable,
  summarizeProvider,
  summarizeTool,
} from "../src/index.js";
import { dumps, fill, str } from "../src/internal/pytext.js";
import { buildTool } from "./conformance/tools.js";

/** Inputs and the output the Python implementation renders for them. */
interface Parity {
  fill: [string, number, string, string][];
  md: [Record<string, unknown>[], string];
  summ: unknown[];
  listing: Record<"table" | "md" | "txt" | "json" | "compact", string>;
  tools: Record<string, unknown>[];
}

const PARITY = JSON.parse(
  readFileSync(new URL("listing.parity.json", import.meta.url), "utf8"),
) as Parity;
const TOOLS = PARITY.tools.map(buildTool);
const PROVIDER = { allTools: () => TOOLS };

describe("textwrap.fill parity", () => {
  it.each(PARITY.fill)("wraps %j at %i", (text, width, indent, expected) => {
    expect(fill(text, width, indent)).toBe(expected);
  });
});

describe("listing parity", () => {
  it("summarizes non-ASCII, whitespace and enum edge cases", () => {
    expect(TOOLS.map((tool) => summarizeTool(tool).asRow())).toEqual(
      PARITY.summ,
    );
  });

  it.each(["table", "md", "txt", "json"] as const)("renders %s", (style) => {
    expect(renderListing(PROVIDER, { style })).toBe(PARITY.listing[style]);
  });

  it("renders compact json", () => {
    expect(renderListing(PROVIDER, { style: "json", pretty: false })).toBe(
      PARITY.listing.compact,
    );
  });

  it("renders cells as Python's str", () => {
    const [rows, expected] = PARITY.md;
    expect(renderMarkdownTable(rows, ["v", "w", "absent"])).toBe(expected);
  });

  it("renders values JSON cannot carry as Python does", () => {
    const rows = [
      { v: [NaN, Infinity, -Infinity, 10n, "\ud800"] },
      { v: NaN },
      { v: -Infinity },
    ];
    expect(renderMarkdownTable(rows, ["v"])).toBe(
      "| v                              |\n| ------------------------------ |\n" +
        "| [nan, inf, -inf, 10, '\\ud800'] |\n" +
        "| nan                            |\n" +
        "| -inf                           |\n",
    );
    expect(dumps([NaN, Infinity, -Infinity, "\ud800", 10n, undefined])).toBe(
      '[NaN, Infinity, -Infinity, "\\ud800", 10, null]',
    );
    expect([str(-0), str(1e20), str(undefined), str([undefined])]).toEqual([
      "0",
      "100000000000000000000",
      "None",
      "[None]",
    ]);
  });
});

describe("summaries", () => {
  const tool: ListedTool = {
    name: "plain",
    description: "Plain. Tool.",
    access: "local",
    resultKind: "records",
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
    inputSchema: { type: "object", properties: { a: { type: "string" } } },
    deprecated: false,
    meta: { alias_of: 3 },
  };

  it("reads a structural tool and fills absent title and target", () => {
    const summary = summarizeTool(tool);
    expect(summary).toBeInstanceOf(ToolSummary);
    expect(summary.inputs[0]).toBeInstanceOf(InputSummary);
    expect(summary).toMatchObject({
      title: null,
      target: null,
      aliasOf: null,
      summary: "Plain.",
    });
    expect(Object.isFrozen(summary)).toBe(true);
    expect(Object.isFrozen(summary.inputs)).toBe(true);
  });

  it("filters by access and accepts any iterable", () => {
    const provider = {
      *allTools() {
        yield tool;
        yield { ...tool, name: "far", access: "remote" as const };
      },
    };
    expect(summarizeProvider(provider).map((s) => s.name)).toEqual([
      "plain",
      "far",
    ]);
    expect(
      summarizeProvider(provider, { access: "remote" }).map((s) => s.name),
    ).toEqual(["far"]);
    expect(
      summarizeProvider(provider, { access: null }).map((s) => s.name),
    ).toEqual(["plain", "far"]);
  });

  it("renders malformed unions and enums as any and enum", () => {
    const odd = {
      ...tool,
      inputSchema: {
        properties: { a: { anyOf: {} }, b: { oneOf: "ab" }, c: { enum: "x" } },
      },
    };
    expect(summarizeTool(odd).inputs.map((item) => item.type)).toEqual([
      "any",
      "any",
      "enum",
    ]);
  });

  it("shows an empty target as a dash, as Python's falsy check does", () => {
    const text = renderListing(
      { allTools: () => [{ ...tool, target: "" }] },
      { style: "txt" },
    );
    expect(text).toContain("  access: local  target: -  result: records\n");
  });

  it("throws RangeError for a style outside LISTING_STYLES", () => {
    expect(() =>
      renderListing(
        { allTools: () => [] },
        { style: "markdown" as unknown as "md" },
      ),
    ).toThrow(RangeError);
  });
});
