/**
 * octools: the OpsCogs standard interface for AI agent tools.
 *
 * One `OCTool` descriptor per capability, result envelopes, a conformance
 * validator, and plain-object converters. The public API is exactly this
 * module's exports; each name maps one to one onto a name in the Python
 * package's `__all__` (see the package README).
 *
 * @packageDocumentation
 */
export { validateTabular } from "./cells.js";
export { type ConvertOptions, toAnthropicTool, toMcpTool } from "./convert.js";
export {
  OCTool,
  type OCToolInit,
  type ToolFunc,
  type ToolProvider,
  checkToolListing,
  mergeProviders,
} from "./descriptor.js";
export {
  ArtifactEnvelope,
  type ArtifactEnvelopeInput,
  ArtifactRef,
  type ArtifactRefInput,
  type Cell,
  type PagingFields,
  type PagingInput,
  RecordsEnvelope,
  type RecordsEnvelopeInput,
  type RecordsEnvelopeSchema,
  TabularEnvelope,
  type TabularEnvelopeInput,
  artifactSchema,
  readEnvelope,
  recordsSchema,
  tabularSchema,
} from "./envelopes.js";
export { OCToolError } from "./errors.js";
export { Finding, type FindingInit } from "./findings.js";
export type { JsonSchema } from "./internal/jsonSchema.js";
export {
  InputSummary,
  type InputSummaryRow,
  type ListedTool,
  type ListedToolProvider,
  type RenderListingOptions,
  type SummarizeOptions,
  ToolSummary,
  type ToolSummaryRow,
  renderListing,
  renderMarkdownTable,
  summarizeProvider,
  summarizeTool,
} from "./listing.js";
export {
  type SchemaForOptions,
  type SchemaIO,
  type StripKeysOptions,
  closeObjects,
  inputSchemaFor,
  outputSchemaFor,
  schemaFor,
  strictClean,
  stripKeys,
  stripTitles,
} from "./schema.js";
export { countSentences, validateProvider, validateTool } from "./validate.js";
export {
  ACCESS_FALLBACK,
  ACCESS_KINDS,
  ALIAS_OF_KEY,
  ANTHROPIC_NAME_RE,
  COLUMN_KIND_FALLBACK,
  COLUMN_KINDS,
  COLUMN_SCALE_FALLBACK,
  COLUMN_SCALES,
  LISTING_STYLES,
  MAX_SENTENCES,
  MCP_META_NAMESPACE,
  MCP_NAME_RE,
  MIN_SENTENCES,
  NAME_RE,
  RESULT_KIND_FALLBACK,
  RESULT_KINDS,
  SCHEMA_DIALECT,
  SCHEMA_ESCAPE_KEY,
  SENSITIVITY_FALLBACK,
  SPEC_VERSION,
  STRICT_FORMATS,
  STRICT_KEYWORDS,
  STRICT_TYPES,
  TABULAR_DEF_NAME,
  VOCABULARY_FALLBACKS,
  type Access,
  type ColumnKind,
  type ColumnScale,
  type ListingStyle,
  type ResultKind,
  type Sensitivity,
} from "./vocabulary.js";
