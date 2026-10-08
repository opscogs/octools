/**
 * Fixture tools and providers: descriptor objects in, `OCTool` and
 * `ToolProvider` out, and back.
 *
 * A fixture's descriptor uses the wire keys (`input_schema`); `OCTool`
 * fields are their camelCase forms. A key with no camelCase form passes
 * through unchanged, so the constructor rejects it as an unknown field.
 */
import {
  OCTool,
  OCToolError,
  type OCToolInit,
  type ToolProvider,
} from "../../src/index.js";

/** Wire key to `OCTool` field, for every key that differs. */
const FIELDS: Readonly<Record<string, string>> = {
  input_schema: "inputSchema",
  output_schema: "outputSchema",
  result_kind: "resultKind",
  read_only_hint: "readOnlyHint",
  destructive_hint: "destructiveHint",
  idempotent_hint: "idempotentHint",
};
const WIRE_KEYS: Readonly<Record<string, string>> = Object.fromEntries(
  Object.entries(FIELDS).map(([wire, field]) => [field, wire]),
);

/** Thrown for a descriptor that fails construction. */
export class InvalidDescriptor extends Error {}

function handler(): Record<string, never> {
  return {};
}

function fields(data: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(data).map(([key, value]) => [FIELDS[key] ?? key, value]),
  );
}

/** Build a tool from a descriptor object; `func` is supplied here. */
export function buildTool(data: Record<string, unknown>): OCTool {
  try {
    return new OCTool({ func: handler, ...fields(data) } as OCToolInit);
  } catch (error) {
    if (error instanceof OCToolError) {
      throw new InvalidDescriptor("invalid_descriptor", { cause: error });
    }
    throw error;
  }
}

/** Build a tool whose fields skipped construction checks (set afterwards). */
export function uncheckedTool(data: Record<string, unknown>): OCTool {
  const base = new OCTool({
    name: "unchecked",
    description: "Unchecked.",
    inputSchema: { type: "object" },
    func: handler,
    access: "local",
  });
  return Object.assign(
    Object.create(OCTool.prototype) as OCTool,
    base,
    fields(data),
  );
}

/** Return `tool` as a descriptor object: every field but `func`. */
export function descriptor(tool: OCTool): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(tool)
      .filter(([field]) => field !== "func")
      .map(([field, value]) => [WIRE_KEYS[field] ?? field, value]),
  );
}

/** A descriptor object becomes a tool; any other JSON value stays foreign. */
function listed(item: unknown): unknown {
  return typeof item === "object" && item !== null && !Array.isArray(item)
    ? buildTool(item as Record<string, unknown>)
    : item;
}

/** Call `n` of `allTools()` returns `listings[n]`, then the last again. */
class FixtureProvider implements ToolProvider {
  private readonly listings: (readonly OCTool[])[];
  private calls = 0;

  constructor(listings: unknown[][]) {
    this.listings = listings.map((items) => items.map(listed) as OCTool[]);
  }

  allTools(): readonly OCTool[] {
    const last = this.listings.length - 1;
    const listing = this.listings[Math.min(this.calls, last)] ?? [];
    this.calls += 1;
    return listing;
  }
}

/** `tools` is a stable listing; `listings` gives one listing per call. */
export function provider(data: Record<string, unknown>): ToolProvider {
  return new FixtureProvider(
    "listings" in data
      ? (data["listings"] as unknown[][])
      : [data["tools"] as unknown[]],
  );
}
