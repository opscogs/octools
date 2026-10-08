/**
 * Conformance validation of `OCTool` descriptors and providers.
 *
 * `validateProvider` is what a library runs in its own tests
 * (`expect(validateProvider(myTools)).toEqual([])`). Every rule returns a
 * {@link Finding} rather than throwing, so a run reports everything at once.
 *
 * @module
 */
import {
  OCTool,
  type ToolProvider,
  checkToolListing,
  typeName,
} from "./descriptor.js";
import { Finding } from "./findings.js";
import { SENTENCE_RE as PY_SENTENCE_RE, strip } from "./internal/pytext.js";
import type { JsonSchema } from "./internal/jsonSchema.js";
import { strictClean } from "./schema.js";
import {
  ALIAS_OF_KEY,
  MAX_SENTENCES,
  MIN_SENTENCES,
  NAME_RE,
  SCHEMA_ESCAPE_KEY,
} from "./vocabulary.js";

// Python's whitespace set, so counts match the Python implementation.
const SENTENCE_RE = new RegExp(PY_SENTENCE_RE.source, "gu");

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Count sentences as runs of `.`, `!` or `?` followed by space or the end.
 *
 * A heuristic: an abbreviation such as `e.g.` followed by a space counts as
 * a sentence end, so write descriptions without them.
 */
export function countSentences(text: string): number {
  return strip(text).match(SENTENCE_RE)?.length ?? 0;
}

/** Return true when `meta` records a non-blank schema escape reason. */
function hasEscape(tool: OCTool): boolean {
  const reason = tool.meta[SCHEMA_ESCAPE_KEY];
  return typeof reason === "string" && strip(reason) !== "";
}

/** Return true when the tool has no output schema or an open root object. */
function outputIsOpen(tool: OCTool): boolean {
  return (
    tool.outputSchema === null ||
    tool.outputSchema["additionalProperties"] === true
  );
}

/** Return true when `schema` declares an `artifact` property. */
function artifactShaped(schema: JsonSchema | null): boolean {
  const properties = schema?.["properties"];
  return isObject(properties) && Object.hasOwn(properties, "artifact");
}

/**
 * Return every conformance finding for one descriptor.
 *
 * Rules: `name_pattern`; `description_sentences` (two to four); every
 * `strictClean` finding on `inputSchema` (path prefixed with
 * `/input_schema`); `output_schema_escape` when the output schema is missing
 * or open without `meta["schema_escape"]`; `artifact_envelope` when
 * `resultKind` is `artifact` but the output schema has no `artifact`
 * property; `deprecated_alias` when a deprecated tool does not name another
 * tool in `meta["alias_of"]`.
 */
export function validateTool(tool: OCTool): Finding[] {
  const findings: Finding[] = [];
  const add = (rule: string, message: string): void => {
    findings.push(new Finding({ rule, message, tool: tool.name }));
  };
  if (!NAME_RE.test(tool.name)) {
    add("name_pattern", `name must match ${NAME_RE.source}`);
  }
  const sentences = countSentences(tool.description);
  if (sentences < MIN_SENTENCES || sentences > MAX_SENTENCES) {
    add(
      "description_sentences",
      `description has ${String(sentences)} sentences; write ` +
        `${String(MIN_SENTENCES)} to ${String(MAX_SENTENCES)}`,
    );
  }
  for (const finding of strictClean(tool.inputSchema)) {
    findings.push(
      new Finding({
        rule: finding.rule,
        message: finding.message,
        tool: tool.name,
        path: `/input_schema${String(finding.path)}`,
      }),
    );
  }
  if (outputIsOpen(tool) && !hasEscape(tool)) {
    add(
      "output_schema_escape",
      "outputSchema is missing or open; record the reason in " +
        `meta["${SCHEMA_ESCAPE_KEY}"] or ship a closed schema`,
    );
  }
  if (tool.resultKind === "artifact" && !artifactShaped(tool.outputSchema)) {
    add(
      "artifact_envelope",
      "artifact tools return the artifact envelope; outputSchema must " +
        "declare an 'artifact' property",
    );
  }
  const alias = tool.meta[ALIAS_OF_KEY];
  if (tool.deprecated && (typeof alias !== "string" || alias === tool.name)) {
    add(
      "deprecated_alias",
      `deprecated tools name the tool they alias in meta["${ALIAS_OF_KEY}"]`,
    );
  }
  return findings;
}

/**
 * Return every conformance finding for a provider and all its tools.
 *
 * Adds the listing rules (`unstable_order`, `duplicate_name`), `not_octool`
 * for foreign items in the listing, and `alias_target_missing` when a
 * deprecated alias names a tool the provider does not list. An empty array
 * means the provider conforms.
 */
export function validateProvider(provider: ToolProvider): Finding[] {
  const findings = checkToolListing(provider);
  const items: readonly unknown[] = provider.allTools();
  const names = new Set(
    items.filter((item) => item instanceof OCTool).map((tool) => tool.name),
  );
  items.forEach((item, index) => {
    if (!(item instanceof OCTool)) {
      findings.push(
        new Finding({
          rule: "not_octool",
          message: `allTools()[${String(index)}] is ${typeName(item)}, not OCTool`,
        }),
      );
      return;
    }
    findings.push(...validateTool(item));
    const alias = item.meta[ALIAS_OF_KEY];
    if (item.deprecated && typeof alias === "string" && !names.has(alias)) {
      findings.push(
        new Finding({
          rule: "alias_target_missing",
          message: `alias target ${JSON.stringify(alias)} is not listed by this provider`,
          tool: item.name,
        }),
      );
    }
  });
  return findings;
}
