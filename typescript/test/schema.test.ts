/**
 * Schema helpers: zod models emit what the Python helpers emit for the
 * equivalent pydantic models, and the strict checker reports as data.
 *
 * Each `PYTHON` entry is `output_schema_for(Model)` from the Python
 * package for the pydantic model the zod schema beside it restates; the
 * Python `input_schema_for(Model)` of each is `close_objects` of it.
 */
import { describe, expect, it } from "vitest";
import * as z from "zod";

import {
  ArtifactEnvelope,
  type JsonSchema,
  RecordsEnvelope,
  SCHEMA_DIALECT,
  TABULAR_DEF_NAME,
  TabularEnvelope,
  artifactSchema,
  closeObjects,
  inputSchemaFor,
  outputSchemaFor,
  recordsSchema,
  schemaFor,
  strictClean,
  stripKeys,
  stripTitles,
  tabularSchema,
} from "../src/index.js";

const Member = z
  .object({
    host_name: z.string().meta({
      description: "Member FQDN.",
      "x-sensitivity": "identifier",
    }),
    vip: z.string().nullable().default(null).describe("Management IPv4."),
  })
  .meta({ id: "Member", title: "Member" });

const Args = z.object({
  include_members: z.boolean().default(false).describe("Also list members."),
  when: z.string().meta({ description: "ISO timestamp.", format: "date-time" }),
  tags: z.array(z.string()).optional().describe("Filter tags."),
  mode: z.enum(["fast", "full"]).default("fast"),
});

const Nested = z.object({
  member: Member.nullable().default(null),
  title: z.string().describe("A property literally named title."),
  options: z.record(z.string(), z.int()).optional(),
});

const Forbidding = z.strictObject({ a: z.int() });

const Bounded = z.object({
  max_results: z.int().min(1).max(1000).default(10),
  name: z.string().min(1),
});

interface NodeShape {
  children?: NodeShape[] | undefined;
}

const Node: z.ZodType<NodeShape> = z
  .object({
    get children() {
      return z.array(Node).optional();
    },
  })
  .meta({ id: "Node" });

const Tree = z.object({ root: Node });

const Item = z
  .object({ name: z.string(), size: z.int().nullable().default(null) })
  .meta({ id: "Item" });

const MEMBER = {
  properties: {
    host_name: {
      description: "Member FQDN.",
      type: "string",
      "x-sensitivity": "identifier",
    },
    vip: {
      anyOf: [{ type: "string" }, { type: "null" }],
      default: null,
      description: "Management IPv4.",
    },
  },
  required: ["host_name"],
  type: "object",
};

const NODE = {
  properties: {
    children: { items: { $ref: "#/$defs/Node" }, type: "array" },
  },
  type: "object",
};

const PYTHON: readonly (readonly [string, z.ZodType, JsonSchema])[] = [
  ["Member", Member, MEMBER],
  [
    "Args",
    Args,
    {
      properties: {
        include_members: {
          default: false,
          description: "Also list members.",
          type: "boolean",
        },
        when: {
          description: "ISO timestamp.",
          format: "date-time",
          type: "string",
        },
        tags: {
          description: "Filter tags.",
          items: { type: "string" },
          type: "array",
        },
        mode: { default: "fast", enum: ["fast", "full"], type: "string" },
      },
      required: ["when"],
      type: "object",
    },
  ],
  [
    "Nested",
    Nested,
    {
      $defs: { Member: MEMBER },
      properties: {
        member: {
          anyOf: [{ $ref: "#/$defs/Member" }, { type: "null" }],
          default: null,
        },
        title: {
          description: "A property literally named title.",
          type: "string",
        },
        options: { additionalProperties: { type: "integer" }, type: "object" },
      },
      required: ["title"],
      type: "object",
    },
  ],
  [
    "Forbidding",
    Forbidding,
    {
      additionalProperties: false,
      properties: { a: { type: "integer" } },
      required: ["a"],
      type: "object",
    },
  ],
  [
    "Bounded",
    Bounded,
    {
      properties: {
        max_results: {
          default: 10,
          maximum: 1000,
          minimum: 1,
          type: "integer",
        },
        name: { minLength: 1, type: "string" },
      },
      required: ["name"],
      type: "object",
    },
  ],
  ["Node", Node, { $defs: { Node: NODE }, $ref: "#/$defs/Node" }],
  [
    "Tree",
    Tree,
    {
      $defs: { Node: NODE },
      properties: { root: { $ref: "#/$defs/Node" } },
      required: ["root"],
      type: "object",
    },
  ],
];

function keysOf(node: unknown, found = new Set<string>()): Set<string> {
  if (Array.isArray(node)) {
    for (const item of node) keysOf(item, found);
  } else if (typeof node === "object" && node !== null) {
    for (const [key, value] of Object.entries(node)) {
      found.add(key);
      if (key === "properties" || key === "$defs") {
        for (const sub of Object.values(value as object)) keysOf(sub, found);
      } else {
        keysOf(value, found);
      }
    }
  }
  return found;
}

describe("zod models emit the Python helpers' schemas", () => {
  it.each(PYTHON)("%s output schema", (_name, model, expected) => {
    expect(outputSchemaFor(model)).toStrictEqual(expected);
  });

  it.each(PYTHON)("%s input schema", (_name, model, expected) => {
    expect(inputSchemaFor(model)).toStrictEqual(closeObjects(expected));
  });

  it("closes model objects but not records", () => {
    const schema = inputSchemaFor(Nested);
    expect(schema["additionalProperties"]).toBe(false);
    expect(schema).toMatchObject({
      $defs: { Member: { additionalProperties: false } },
      properties: { options: { additionalProperties: { type: "integer" } } },
    });
  });

  it("strips titles but keeps a property named title", () => {
    expect(keysOf(z.toJSONSchema(Member)).has("title")).toBe(true);
    const schema = schemaFor(Nested);
    expect(Object.keys(schema["properties"] as object)).toContain("title");
    expect([...keysOf(schema)].filter((key) => key === "title")).toEqual([]);
  });

  it("describes the output side on request", () => {
    expect(schemaFor(Member, { io: "output" })).toStrictEqual({
      ...MEMBER,
      required: ["host_name", "vip"],
      additionalProperties: false,
    });
  });

  it("emits a records envelope over a model as Python does", () => {
    const schema = recordsSchema(Item);
    expect(schema).toStrictEqual(outputSchemaFor(RecordsEnvelope(Item)));
    expect(schema["properties"]).toMatchObject({
      records: {
        description: "Result records; keys and order follow the item schema.",
        items: { $ref: "#/$defs/Item" },
        type: "array",
      },
    });
    expect(schema["$defs"]).toStrictEqual({
      Item: {
        properties: {
          name: { type: "string" },
          size: {
            anyOf: [{ type: "integer" }, { type: "null" }],
            default: null,
          },
        },
        required: ["name"],
        type: "object",
      },
    });
  });

  it("nests the envelopes by $ref, strict-clean", () => {
    const Consumer = z.object({
      data: TabularEnvelope,
      // A default over a transform describes the output side, so the input
      // side states it only through prefault.
      art: ArtifactEnvelope.nullable().prefault(null),
    });
    const schema = inputSchemaFor(Consumer);
    const { $defs: defs, ...root } = schema;
    expect(root).toStrictEqual({
      properties: {
        data: { $ref: `#/$defs/${TABULAR_DEF_NAME}` },
        art: {
          anyOf: [{ $ref: "#/$defs/ArtifactEnvelope" }, { type: "null" }],
          default: null,
        },
      },
      required: ["data"],
      type: "object",
      additionalProperties: false,
    });
    const { $defs: artifactDefs, ...artifact } = closeObjects(artifactSchema());
    expect(defs).toStrictEqual({
      [TABULAR_DEF_NAME]: closeObjects(tabularSchema()),
      ArtifactEnvelope: artifact,
      ...(artifactDefs as object),
    });
    expect(strictClean(schema)).toEqual([]);
    expect(strictClean(inputSchemaFor(TabularEnvelope))).toEqual([]);
  });
});

describe("strictClean", () => {
  it("has the 2020-12 dialect", () => {
    expect(SCHEMA_DIALECT).toMatch(/2020-12\/schema$/);
  });

  it.each([Args, Forbidding])("passes a generated input schema", (model) => {
    expect(strictClean(inputSchemaFor(model))).toEqual([]);
  });

  it("reports bounds without mutating the schema", () => {
    const schema = inputSchemaFor(Bounded);
    const before = JSON.stringify(schema);
    const rules = strictClean(schema).map((finding) => finding.rule);
    expect(new Set(rules)).toEqual(new Set(["unsupported_keyword"]));
    expect(JSON.stringify(schema)).toBe(before);
  });

  it("reports the extension key and a zod format's pattern", () => {
    const rules = strictClean(
      inputSchemaFor(z.object({ m: Member, at: z.iso.datetime() })),
    ).map((finding) => [finding.rule, finding.path]);
    expect(rules).toEqual([
      ["unsupported_keyword", "/properties/at"],
      ["extension_key", "/$defs/Member/properties/host_name"],
    ]);
  });

  it("reports a recursive $defs entry and a $ref root", () => {
    const tree = strictClean(inputSchemaFor(Tree));
    expect(
      tree.filter((f) => f.rule === "recursive_ref").map((f) => f.path),
    ).toEqual(["/$defs/Node"]);
    expect(strictClean(inputSchemaFor(Node)).map((f) => f.rule)).toEqual([
      "root_not_object",
    ]);
  });

  const closed = { type: "object", additionalProperties: false };
  const prop = (n: unknown) => ({ ...closed, properties: { n } });

  it.each([
    ["not an object", "nope", ["root_not_object"]],
    ["null $defs", { ...closed, $defs: null }, ["bad_defs"]],
    ["open", { type: "object" }, ["open_object"]],
    [
      "open true",
      { type: "object", additionalProperties: true },
      ["open_object"],
    ],
    [
      "open schema",
      { type: "object", additionalProperties: { type: "string" } },
      ["open_object"],
    ],
    ["title", { ...closed, title: "T" }, ["title_present"]],
    ["type list", prop({ type: ["string", "money"] }), ["unsupported_type"]],
    ["type null", prop({ type: null }), ["unsupported_type"]],
    [
      "format",
      prop({ type: "string", format: "binary" }),
      ["unsupported_format"],
    ],
    [
      "format not string",
      prop({ type: "string", format: 1 }),
      ["unsupported_format"],
    ],
    [
      "min items",
      prop({ type: "array", items: {}, minItems: 2 }),
      ["min_items"],
    ],
    ["enum objects", prop({ enum: [{ a: 1 }] }), ["enum_not_primitive"]],
    ["enum string", prop({ enum: "ab" }), ["enum_not_primitive"]],
    ["enum primitives", prop({ enum: ["a", 1, true, null] }), []],
    [
      "external ref",
      prop({ $ref: "https://demo.example/x.json" }),
      ["unknown_ref"],
    ],
    ["missing ref", prop({ $ref: "#/$defs/Missing" }), ["unknown_ref"]],
    ["items true", prop({ type: "array", items: true }), ["boolean_schema"]],
    ["items false", prop({ type: "array", items: false }), ["boolean_schema"]],
    ["nested defs", prop({ ...closed, $defs: {} }), ["defs_not_at_root"]],
    ["properties not an object", { ...closed, properties: 3 }, []],
    ["anyOf not a list", { ...closed, anyOf: 3 }, []],
  ])("%s", (_name, schema, rules) => {
    const found = strictClean(schema);
    expect(found.map((finding) => finding.rule)).toEqual(rules);
    expect(found.every((finding) => finding.tool === null)).toBe(true);
    expect(found.every((finding) => finding.message.length > 0)).toBe(true);
  });

  it("finds mutual recursion and revisits a seen node", () => {
    const ref = (name: string) => ({ $ref: `#/$defs/${name}` });
    const node = (field: string, name: string) => ({
      ...closed,
      properties: { [field]: ref(name) },
    });
    const recursive = (defs: Record<string, unknown>) =>
      strictClean({ ...closed, $defs: defs, properties: { a: ref("A") } })
        .filter((finding) => finding.rule === "recursive_ref")
        .map((finding) => finding.path)
        .sort();
    expect(
      recursive({
        A: node("b", "B"),
        B: node("a", "A"),
        C: { type: "string" },
      }),
    ).toEqual(["/$defs/A", "/$defs/B"]);
    expect(
      recursive({ A: node("b", "B"), B: node("c", "C"), C: node("b", "B") }),
    ).toEqual(["/$defs/B", "/$defs/C"]);
  });
});

describe("rewriting helpers", () => {
  it("strips titles from a copy and keeps data values", () => {
    const original = {
      type: "object",
      title: "T",
      properties: {
        a: { type: "string", title: "A", default: { title: "keep" } },
      },
      enum: [{ title: "keep" }],
      anyOf: [true, { type: "null", title: "N" }],
    };
    const stripped = stripTitles(original);
    expect(stripped).toStrictEqual({
      type: "object",
      properties: { a: { type: "string", default: { title: "keep" } } },
      enum: [{ title: "keep" }],
      anyOf: [true, { type: "null" }],
    });
    expect(original.title).toBe("T");
    const props = stripped["properties"] as Record<string, JsonSchema>;
    expect(props["a"]?.["default"]).not.toBe(original.properties.a.default);
  });

  it("strips extension keys by prefix from a copy", () => {
    const schema = outputSchemaFor(Member);
    const clean = stripKeys(schema, { prefixes: ["x-"] });
    expect(clean).toStrictEqual({
      ...MEMBER,
      properties: {
        ...MEMBER.properties,
        host_name: { description: "Member FQDN.", type: "string" },
      },
    });
    expect(schema).toStrictEqual(MEMBER);
    expect(stripKeys(schema)).toStrictEqual(MEMBER);
  });

  it("closes only objects that declare properties", () => {
    const closed = closeObjects({
      type: "object",
      properties: { m: { type: "object" } },
      $defs: 3,
    });
    expect(closed).toStrictEqual({
      type: "object",
      properties: { m: { type: "object" } },
      $defs: 3,
      additionalProperties: false,
    });
  });
});
