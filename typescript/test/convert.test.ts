/** Converter output is plain, independent data. */
import { expect, it } from "vitest";

import {
  OCTool,
  OCToolError,
  toAnthropicTool,
  toMcpTool,
} from "../src/index.js";

const tool = new OCTool({
  name: "cluster_info",
  description: "Return the cluster identity. Use it first.",
  inputSchema: {
    type: "object",
    properties: { tags: { type: "array", items: { type: "string" } } },
    additionalProperties: false,
  },
  func: () => ({}),
  access: "remote",
  meta: { nested: { list: [1, "a", null] } },
});

it("returns deep copies the caller may change", () => {
  const mcp = toMcpTool(tool);
  const schema = mcp["inputSchema"] as { properties: { tags: object } };
  expect(schema).toEqual(tool.inputSchema);
  expect(schema.properties.tags).not.toBe(
    (tool.inputSchema["properties"] as { tags: object }).tags,
  );
  const meta = (mcp["_meta"] as Record<string, unknown>)[
    "com.opscogs.octools/meta"
  ];
  expect(meta).toEqual(tool.meta);
  expect(meta).not.toBe(tool.meta);
});

it("names the broken name in the error", () => {
  expect(() => toAnthropicTool(tool, { namePrefix: "a.b_" })).toThrow(
    new OCToolError(
      'tool name "a.b_cluster_info" does not match ^[a-zA-Z0-9_-]{1,128}$',
    ),
  );
});
