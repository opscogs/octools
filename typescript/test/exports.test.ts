/** The public API is exactly the package root's export list. */
import { expect, it } from "vitest";

import * as octools from "../src/index.js";

it("exports exactly the public names", () => {
  expect(Object.keys(octools).sort()).toEqual(
    [
      "ACCESS_FALLBACK",
      "ACCESS_KINDS",
      "ALIAS_OF_KEY",
      "ANTHROPIC_NAME_RE",
      "ArtifactEnvelope",
      "ArtifactRef",
      "COLUMN_KINDS",
      "COLUMN_KIND_FALLBACK",
      "COLUMN_SCALES",
      "COLUMN_SCALE_FALLBACK",
      "Finding",
      "LISTING_STYLES",
      "MAX_SENTENCES",
      "MCP_META_NAMESPACE",
      "MCP_NAME_RE",
      "MIN_SENTENCES",
      "NAME_RE",
      "OCTool",
      "OCToolError",
      "checkToolListing",
      "countSentences",
      "mergeProviders",
      "toAnthropicTool",
      "toMcpTool",
      "validateProvider",
      "validateTool",
      "RESULT_KINDS",
      "RESULT_KIND_FALLBACK",
      "RecordsEnvelope",
      "SCHEMA_DIALECT",
      "SCHEMA_ESCAPE_KEY",
      "SENSITIVITY_FALLBACK",
      "SPEC_VERSION",
      "STRICT_FORMATS",
      "STRICT_KEYWORDS",
      "STRICT_TYPES",
      "TABULAR_DEF_NAME",
      "TabularEnvelope",
      "VOCABULARY_FALLBACKS",
      "artifactSchema",
      "closeObjects",
      "inputSchemaFor",
      "outputSchemaFor",
      "schemaFor",
      "strictClean",
      "stripKeys",
      "stripTitles",
      "readEnvelope",
      "recordsSchema",
      "tabularSchema",
      "validateTabular",
      "InputSummary",
      "ToolSummary",
      "renderListing",
      "renderMarkdownTable",
      "summarizeProvider",
      "summarizeTool",
    ].sort(),
  );
});

it("builds frozen findings and named errors", () => {
  const finding = new octools.Finding({ rule: "r", message: "m" });
  expect(finding).toMatchObject({
    rule: "r",
    message: "m",
    tool: null,
    path: null,
  });
  expect(Object.isFrozen(finding)).toBe(true);
  const error = new octools.OCToolError("bad", { cause: finding });
  expect(error).toBeInstanceOf(Error);
  expect(error.name).toBe("OCToolError");
  expect(error.cause).toBe(finding);
});
