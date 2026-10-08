/**
 * Run one spec fixture's `input` through the TypeScript implementation.
 *
 * Each runner takes a fixture's `input` and returns the JSON value its
 * `expected` must equal. Findings compare as `rule`, `tool` and `path`,
 * since `message` is for a person and is not part of the contract; errors
 * are `{"error": <code>}`.
 *
 * To implement an operation, add its runner to `RUNNERS` and remove it
 * from `PENDING_OPERATIONS`; the conformance suite fails until every
 * fixture directory has a runner.
 */
import * as z from "zod";

import {
  type Access,
  ArtifactEnvelope,
  type Finding,
  type ListingStyle,
  type JsonSchema,
  OCToolError,
  RecordsEnvelope,
  TabularEnvelope,
  checkToolListing,
  closeObjects,
  countSentences,
  mergeProviders,
  readEnvelope,
  renderListing,
  renderMarkdownTable,
  strictClean,
  stripKeys,
  stripTitles,
  summarizeProvider,
  summarizeTool,
  toAnthropicTool,
  toMcpTool,
  validateProvider,
  validateTabular,
  validateTool,
} from "../../src/index.js";
import type { ErrorCode } from "../../src/errors.js";
import {
  InvalidDescriptor,
  buildTool,
  descriptor,
  provider,
  uncheckedTool,
} from "./tools.js";

/** A runner: a fixture's `input` in, the JSON value it produces out. */
export type Runner = (input: Record<string, unknown>) => unknown;

/** An operation failed in a way the spec names; `code` is the error data. */
export class FixtureError extends Error {
  constructor(readonly code: ErrorCode) {
    super(code);
  }
}

const ENVELOPES: Readonly<Record<string, z.ZodType>> = {
  records: RecordsEnvelope(z.record(z.string(), z.unknown())),
  tabular: TabularEnvelope,
  artifact: ArtifactEnvelope,
};

/** Return `value` as plain JSON data. */
export function plain(value: unknown): unknown {
  return JSON.parse(JSON.stringify(value));
}

/** Return the fields of each finding that are part of the contract. */
export function findings(found: readonly Finding[]): unknown[] {
  return found.map(({ rule, tool, path }) => ({ rule, tool, path }));
}

/** Run `parse`, turning a parse failure into the `invalid_envelope` code. */
function parsing<T>(parse: () => T): T {
  try {
    return parse();
  } catch (error) {
    if (error instanceof z.ZodError || error instanceof SyntaxError) {
      throw new FixtureError("invalid_envelope");
    }
    throw error;
  }
}

function envelope(input: Record<string, unknown>, tolerant: boolean): unknown {
  const model = ENVELOPES[input["model"] as string];
  if (model === undefined) {
    throw new Error(`unknown envelope model ${String(input["model"])}`);
  }
  const data = input["data"];
  return parsing(() =>
    tolerant ? readEnvelope(model, data) : model.parse(data),
  );
}

function convert(
  converter: typeof toMcpTool,
  input: Record<string, unknown>,
): unknown {
  const tool = buildTool(input["tool"] as Record<string, unknown>);
  try {
    return converter(tool, {
      namePrefix: input["name_prefix"] as string | undefined,
    });
  } catch (error) {
    if (error instanceof OCToolError) {
      throw new FixtureError("invalid_name");
    }
    throw error;
  }
}

/** One runner per fixture directory under `spec/fixtures/`. */
export const RUNNERS: Readonly<Record<string, Runner>> = {
  OCTool: (input) =>
    descriptor(buildTool(input["tool"] as Record<string, unknown>)),
  check_tool_listing: (input) => findings(checkToolListing(provider(input))),
  count_sentences: (input) => countSentences(input["text"] as string),
  merge_providers: (input) =>
    mergeProviders(
      ...(input["providers"] as Record<string, unknown>[]).map(provider),
    )
      .allTools()
      .map((tool) => tool.name),
  to_anthropic_tool: (input) => convert(toAnthropicTool, input),
  to_mcp_tool: (input) => convert(toMcpTool, input),
  validate_provider: (input) => findings(validateProvider(provider(input))),
  validate_tool: (input) =>
    findings(
      validateTool(
        (input["unchecked"] === true ? uncheckedTool : buildTool)(
          input["tool"] as Record<string, unknown>,
        ),
      ),
    ),
  close_objects: (input) => closeObjects(input["schema"] as JsonSchema),
  strict_clean: (input) => findings(strictClean(input["schema"])),
  strip_keys: (input) =>
    stripKeys(input["schema"] as JsonSchema, {
      keys: (input["keys"] as string[] | undefined) ?? [],
      prefixes: (input["prefixes"] as string[] | undefined) ?? [],
    }),
  strip_titles: (input) => stripTitles(input["schema"] as JsonSchema),
  read_envelope: (input) => envelope(input, true),
  validate_envelope: (input) => envelope(input, false),
  validate_tabular: (input) =>
    findings(
      validateTabular(parsing(() => TabularEnvelope.parse(input["envelope"]))),
    ),
  summarize_tool: (input) =>
    summarizeTool(buildTool(input["tool"] as Record<string, unknown>)).asRow(),
  summarize_provider: (input) =>
    summarizeProvider(provider(input), {
      access: input["access"] as Access | undefined,
    }).map((summary) => summary.asRow()),
  render_listing: (input) => {
    try {
      return renderListing(provider(input), {
        style: input["style"] as ListingStyle | undefined,
        access: input["access"] as Access | undefined,
        pretty: input["pretty"] as boolean | undefined,
      });
    } catch (error) {
      if (error instanceof RangeError) {
        throw new FixtureError("invalid_style");
      }
      throw error;
    }
  },
  render_markdown_table: (input) =>
    renderMarkdownTable(
      input["rows"] as Record<string, unknown>[],
      input["columns"] as string[],
    ),
};

/**
 * Operations whose module is not implemented yet. Their fixtures are
 * registered as `it.todo`, so the suite counts them; the list must be empty
 * before the package is published.
 */
export const PENDING_OPERATIONS: readonly string[] = [];

/** Return what `operation` produces for `input`, errors as data. */
export function run(
  operation: string,
  input: Record<string, unknown>,
): unknown {
  const runner = RUNNERS[operation];
  if (runner === undefined) {
    throw new Error(`no runner for ${operation}`);
  }
  try {
    return plain(runner(input));
  } catch (error) {
    if (error instanceof FixtureError) {
      return { error: error.code };
    }
    if (error instanceof InvalidDescriptor) {
      return { error: "invalid_descriptor" };
    }
    throw error;
  }
}
