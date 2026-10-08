/** Envelope schemas, strict parsing and tolerant reading beyond the spec fixtures. */
import { describe, expect, it } from "vitest";
import * as z from "zod";

import {
  ArtifactEnvelope,
  RecordsEnvelope,
  SCHEMA_DIALECT,
  TabularEnvelope,
  artifactSchema,
  readEnvelope,
  recordsSchema,
  tabularSchema,
} from "../src/index.js";
import { readSpecJson } from "./conformance/fixtures.js";

const ROW = { columns: ["a"], rows: [["x"]], row_count: 1 };
const REF = { reference: "r", media_type: "text/csv", bytes: 1 };

describe("JSON Schemas equal spec/schema", () => {
  it.each([
    [
      "records_envelope",
      () => recordsSchema(z.record(z.string(), z.unknown())),
    ],
    ["tabular_envelope", tabularSchema],
    ["artifact_envelope", artifactSchema],
  ])("%s", (stem, build) => {
    const expected = readSpecJson(`schema/${stem}.schema.json`);
    expect({ $schema: SCHEMA_DIALECT, ...build() }).toStrictEqual(expected);
  });

  it("describes records by the item schema", () => {
    const item = z.strictObject({ name: z.string().describe("Host name.") });
    const schema = recordsSchema(item);
    expect(schema["properties"]).toMatchObject({
      records: {
        items: {
          type: "object",
          properties: { name: { type: "string", description: "Host name." } },
          additionalProperties: false,
        },
      },
    });
    expect(schema["required"]).toEqual(["records", "count", "truncated"]);
  });
});

describe("RecordsEnvelope", () => {
  it("returns one schema per item schema", () => {
    const item = z.string();
    expect(RecordsEnvelope(item)).toBe(RecordsEnvelope(item));
    expect(RecordsEnvelope()).toBe(RecordsEnvelope());
  });

  it("parses records with the item schema", () => {
    const schema = RecordsEnvelope(
      z.string().transform((value) => value.length),
    );
    expect(
      schema.parse({ records: ["abc"], count: 1, truncated: false }),
    ).toEqual({
      records: [3],
      count: 1,
      truncated: false,
    });
  });

  it("accepts any records without an item schema", () => {
    const data = {
      records: [1, "a", null],
      count: 3,
      truncated: true,
      total_count: "3",
    };
    expect(RecordsEnvelope().parse(data)).toEqual({
      ...data,
      resumable: false,
    });
  });

  it.each([
    ["an integer beyond 2^53 - 1", { total_count: 2 ** 60 }],
    ["a string total_count below the count", { total_count: "0" }],
    ["a null resumable", { resumable: null }],
  ])("rejects %s", (_, extra) => {
    const data = { records: [1], count: 1, truncated: false, ...extra };
    expect(() => RecordsEnvelope().parse(data)).toThrow(z.ZodError);
  });
});

describe("TabularEnvelope", () => {
  it.each([
    [
      "a kinds list with a non-numeric kind under a scale",
      { column_kinds: ["text"], column_scales: ["log2"] },
    ],
    [
      "a scale with no kind for its column",
      { column_kinds: [], column_scales: ["log2"] },
    ],
    ["descriptions of the wrong width", { column_descriptions: [] }],
  ])("rejects %s", (_, extra) => {
    expect(() =>
      TabularEnvelope.parse({ ...ROW, truncated: false, ...extra }),
    ).toThrow(z.ZodError);
  });

  it("keeps a numeric scale and drops empty warnings", () => {
    const data = {
      ...ROW,
      rows: [[1]],
      truncated: false,
      column_kinds: ["big_integer"],
      column_scales: ["log10"],
      warnings: [],
    };
    expect(TabularEnvelope.parse(data)).toEqual({
      ...ROW,
      rows: [[1]],
      truncated: false,
      column_kinds: ["big_integer"],
      column_scales: ["log10"],
    });
  });
});

describe("readEnvelope", () => {
  it("rejects a schema that is not an envelope", () => {
    expect(() => readEnvelope(z.object({}), {})).toThrow(TypeError);
  });

  it("reads UTF-8 JSON bytes", () => {
    const bytes = new TextEncoder().encode(
      JSON.stringify({ artifact: REF, role: "x" }),
    );
    expect(readEnvelope(ArtifactEnvelope, bytes)).toEqual({
      artifact: REF,
      artifacts: [],
      warnings: [],
      sensitivity: "inherits_input",
    });
  });

  it("raises SyntaxError on malformed text", () => {
    expect(() => readEnvelope(TabularEnvelope, "{")).toThrow(SyntaxError);
  });

  it.each([
    ["an artifact that is not an object", { artifact: "r" }],
    ["artifacts that are not a list", { artifact: REF, artifacts: "r" }],
  ])("still rejects %s", (_, data) => {
    expect(() => readEnvelope(ArtifactEnvelope, data)).toThrow(z.ZodError);
  });

  it("leaves non-list kinds and scales to the strict checks", () => {
    const data = {
      ...ROW,
      truncated: false,
      column_kinds: "text",
      column_scales: "log2",
    };
    expect(() => readEnvelope(TabularEnvelope, data)).toThrow(z.ZodError);
  });

  it("reads a scale past the end of the kinds as null, then rejects the widths", () => {
    const data = {
      ...ROW,
      truncated: false,
      column_kinds: [],
      column_scales: ["log2"],
    };
    expect(() => readEnvelope(TabularEnvelope, data)).toThrow(z.ZodError);
  });

  it("does not change the caller's object", () => {
    const data = { ...ROW, truncated: false, extra: 1 };
    readEnvelope(TabularEnvelope, data);
    expect(data.extra).toBe(1);
  });
});
