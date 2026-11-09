/** OCTool construction, provider merging and listing checks beyond the spec fixtures. */
import { describe, expect, it } from "vitest";

import {
  OCTool,
  type OCToolInit,
  OCToolError,
  type ToolProvider,
  checkToolListing,
  mergeProviders,
  prefixTools,
  selectTools,
  toAnthropicTool,
  toMcpTool,
  validateNamespace,
  validateProvider,
  validateTags,
} from "../src/index.js";

const BASE: OCToolInit = {
  name: "cluster_info",
  description: "Return the cluster identity. Use it first.",
  inputSchema: { type: "object", properties: {}, additionalProperties: false },
  func: () => ({}),
  access: "remote",
};

function listing(...items: unknown[]): ToolProvider {
  return { allTools: () => items as OCTool[] };
}

describe("OCTool", () => {
  it("is frozen and fills defaults", () => {
    const tool = new OCTool(BASE);
    expect(Object.isFrozen(tool)).toBe(true);
    expect(tool).toMatchObject({
      target: null,
      outputSchema: null,
      resultKind: "records",
      title: null,
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      deprecated: false,
      meta: {},
    });
  });

  it.each([
    ["a trailing newline in the name", { name: "cluster_info\n" }],
    ["a non-string name", { name: 7 }],
    ["an async func", { func: async () => Promise.resolve({}) }],
    [
      "an async generator func",
      {
        func: async function* gen() {
          yield await Promise.resolve(1);
        },
      },
    ],
    ["a func that is not a function", { func: "run" }],
    ["an output schema that is not an object", { outputSchema: [] }],
    ["an unknown field", { version: "2" }],
    ["an undefined unknown field", { inputschema: undefined }],
    ["a null meta", { meta: null }],
    ["a null hint", { readOnlyHint: null }],
    ["a null result kind", { resultKind: null }],
  ])("rejects %s", (_label, change) => {
    expect(
      () => new OCTool({ ...BASE, ...change } as unknown as OCToolInit),
    ).toThrow(OCToolError);
  });

  it("accepts a sync generator and an explicitly undefined optional", () => {
    expect(
      new OCTool({
        ...BASE,
        func: function* gen() {
          yield 1;
        },
        target: undefined,
      }).target,
    ).toBeNull();
  });
});

describe("mergeProviders", () => {
  it("re-reads each provider on every call", () => {
    let calls = 0;
    const counting: ToolProvider = {
      allTools: () => {
        calls += 1;
        return [new OCTool(BASE)];
      },
    };
    const merged = mergeProviders(counting, listing());
    expect(merged.allTools().map((tool) => tool.name)).toEqual([
      "cluster_info",
    ]);
    merged.allTools();
    expect(calls).toBe(2);
  });
});

describe("foreign items", () => {
  class Widget {
    readonly id = 1;
  }
  it.each([
    [null, "<null>"],
    [[1], "<array>"],
    [new Widget(), "<Widget>"],
    [Object.create(null), "<object>"],
    [{}, "<Object>"],
    ["x", "<string>"],
    [3, "<number>"],
  ])("reports %j by its type", (item, shown) => {
    const found = checkToolListing(listing(item, item));
    expect(found.map((finding) => finding.tool)).toEqual([shown]);
    expect(validateProvider(listing(item))[0]?.message).toContain(
      shown.slice(1, -1),
    );
  });
});

describe("selectTools", () => {
  it("requires every tag when nested", () => {
    const tool = (name: string, tags: string[]): OCTool =>
      new OCTool({ ...BASE, name, tags });
    const tools = [
      tool("both_tags", ["network", "recommended"]),
      tool("one_tag", ["network"]),
    ];
    const provider = { allTools: () => tools };
    const selected = selectTools(selectTools(provider, { tags: ["network"] }), {
      tags: ["recommended"],
    });
    expect(selected.allTools().map((item) => item.name)).toEqual(["both_tags"]);
  });

  it.each([
    ["drops a deprecated alias without its target", ["advanced"], ["other"]],
    [
      "keeps a deprecated alias with its target",
      ["recommended"],
      ["target", "alias", "other"],
    ],
  ])("%s", (_, targetTags, expected) => {
    const tools = [
      new OCTool({ ...BASE, name: "target", tags: targetTags }),
      new OCTool({
        ...BASE,
        name: "alias",
        tags: ["recommended"],
        deprecated: true,
        meta: { alias_of: "target" },
      }),
      new OCTool({ ...BASE, name: "other", tags: ["recommended"] }),
    ];
    const selected = selectTools(
      { allTools: () => tools },
      {
        tags: ["recommended"],
      },
    );
    expect(selected.allTools().map((item) => item.name)).toEqual(expected);
    const rules = validateProvider(selected).map((finding) => finding.rule);
    expect(rules).not.toContain("alias_target_missing");
  });

  it("rejects a bare string for validateTags", () => {
    expect(() => validateTags(mergeProviders(), { allowed: "custom" })).toThrow(
      OCToolError,
    );
  });

  it("rejects a bare string", () => {
    expect(() =>
      selectTools(mergeProviders(), { tags: "recommended" }),
    ).toThrow(OCToolError);
  });
});

describe("selectTools alias chains", () => {
  it("drops an alias of a dropped alias", () => {
    const tools = [
      new OCTool({
        ...BASE,
        name: "older",
        tags: ["recommended"],
        deprecated: true,
        meta: { alias_of: "old" },
      }),
      new OCTool({ ...BASE, name: "root", tags: ["advanced"] }),
      new OCTool({
        ...BASE,
        name: "old",
        tags: ["recommended"],
        deprecated: true,
        meta: { alias_of: "root" },
      }),
    ];
    const selected = selectTools(listing(...tools), { tags: ["recommended"] });
    expect(selected.allTools()).toEqual([]);
    expect(validateProvider(selected)).toEqual([]);
  });
});

describe("prefixTools", () => {
  const func = (): Record<string, never> => ({});
  const outputSchema = BASE.inputSchema;
  const tools = [
    new OCTool({
      ...BASE,
      name: "get_rows",
      func,
      title: "Rows",
      outputSchema,
    }),
    new OCTool({
      ...BASE,
      name: "fetch_rows",
      outputSchema,
      description: "Return rows. Use get_rows instead.",
      deprecated: true,
      meta: { alias_of: "get_rows" },
    }),
  ];

  it("keeps each func, is idempotent and conforms", () => {
    const once = prefixTools(tools, "demo_");
    expect(Object.isFrozen(once)).toBe(true);
    expect(once.map((tool) => tool.func)).toEqual(
      tools.map((tool) => tool.func),
    );
    expect(once[0]?.title).toBe("Rows");
    expect(prefixTools(once, "demo_")).toEqual(once);
    expect(validateNamespace(listing(...once), "demo")).toEqual([]);
    expect(validateProvider(listing(...once))).toEqual([]);
    for (const tool of once) {
      expect(toMcpTool(tool)["name"]).toBe(tool.name);
      expect(toAnthropicTool(tool)["name"]).toBe(tool.name);
    }
  });

  it.each([
    ["Ping the host, then ping again.", "Ping the host, then ping again."],
    [
      "Run `ping` first. A ping is cheap.",
      "Run `demo_ping` first. A ping is cheap.",
    ],
    ["Run `ping and get_rows`.", "Run `demo_ping and demo_get_rows`."],
    [
      "Call get_rows, then `get_rows`.",
      "Call demo_get_rows, then `demo_get_rows`.",
    ],
    ["An open ` ping is prose.", "An open ` ping is prose."],
  ])("rewrites a one-word name only in code: %s", (text, expected) => {
    const listed = [
      new OCTool({ ...BASE, name: "ping", description: text }),
      new OCTool({ ...BASE, name: "get_rows" }),
    ];
    expect(prefixTools(listed, "demo")[0]?.description).toBe(expected);
  });

  it.each([[["get_rows", "demo_get_rows"]], [["echo", "echo"]]])(
    "names both sources of a collision: %j",
    (names) => {
      const listed = names.map((name) => new OCTool({ ...BASE, name }));
      expect(() => prefixTools(listed, "demo")).toThrow(
        new RegExp(names.map((name) => `"${name}"`).join(".*")),
      );
    },
  );

  it("rewrites only descriptions", () => {
    const tool = new OCTool({
      ...BASE,
      name: "get_rows",
      title: "Like get_rows",
      inputSchema: {
        type: "object",
        title: "get_rows input",
        properties: {
          q: {
            type: "string",
            title: "get_rows",
            description: "See get_rows.",
          },
        },
        additionalProperties: false,
      },
      meta: { alias_of: "get_rows", note: "see get_rows" },
    });
    const [published] = prefixTools([tool], "demo");
    expect(published?.title).toBe("Like get_rows");
    expect(published?.meta).toEqual({
      alias_of: "demo_get_rows",
      note: "see get_rows",
    });
    expect(published?.inputSchema).toEqual({
      type: "object",
      title: "get_rows input",
      properties: {
        q: {
          type: "string",
          title: "get_rows",
          description: "See demo_get_rows.",
        },
      },
      additionalProperties: false,
    });
  });

  it("rejects an item that is not a tool", () => {
    expect(() =>
      prefixTools(["get_rows"] as unknown as OCTool[], "demo_"),
    ).toThrow(OCToolError);
  });
});

describe("validateNamespace", () => {
  it.each([
    ["other_rows", 'does not start with "demo_"'],
    ["demo_", 'the name after "demo_"'],
    ["demo__rows", 'the name after "demo_"'],
    ["demo_1rows", 'the name after "demo_"'],
  ])("says which part of %s failed", (name, part) => {
    const findings = validateNamespace(
      listing(
        new OCTool({ ...BASE, name: "demo_rows" }),
        new OCTool({ ...BASE, name }),
      ),
      "demo",
    );
    expect(findings).toHaveLength(1);
    expect(findings[0]).toMatchObject({
      rule: "name_outside_namespace",
      tool: name,
    });
    expect(findings[0]?.message).toContain(part);
  });
});
