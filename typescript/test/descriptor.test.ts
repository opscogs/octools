/** OCTool construction, provider merging and listing checks beyond the spec fixtures. */
import { describe, expect, it } from "vitest";

import {
  OCTool,
  type OCToolInit,
  OCToolError,
  type ToolProvider,
  checkToolListing,
  mergeProviders,
  validateProvider,
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
