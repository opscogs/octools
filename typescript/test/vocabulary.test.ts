/** The exported vocabularies, fallbacks and constants equal spec/vocabulary.json. */
import { describe, expect, it } from "vitest";

import * as octools from "../src/index.js";
import { SENSITIVITIES } from "../src/vocabulary.js";
import { readSpecJson } from "./conformance/fixtures.js";

interface Vocabulary {
  values: unknown[];
  fallback: unknown;
  values_constant: string | null;
  fallback_constant: string;
}

const SPEC = readSpecJson("vocabulary.json") as {
  spec_version: string;
  vocabularies: Record<string, Vocabulary>;
  constants: Record<string, unknown>;
};
const EXPORTS = octools as unknown as Record<string, unknown>;

/** Return an exported constant as the JSON value vocabulary.json holds. */
function asJson(value: unknown): unknown {
  if (value instanceof RegExp) {
    return value.source;
  }
  if (value instanceof Set) {
    return [...(value as Set<string>)].sort();
  }
  return value;
}

describe("spec/vocabulary.json", () => {
  it("has the same spec version", () => {
    expect(octools.SPEC_VERSION).toBe(SPEC.spec_version);
  });

  for (const [name, vocabulary] of Object.entries(SPEC.vocabularies)) {
    it(`has the ${name} values and fallback`, () => {
      const values =
        vocabulary.values_constant === null
          ? SENSITIVITIES
          : EXPORTS[vocabulary.values_constant];
      expect(values).toEqual(vocabulary.values);
      expect(EXPORTS[vocabulary.fallback_constant]).toEqual(
        vocabulary.fallback,
      );
    });
  }

  it("has every constant", () => {
    const constants = Object.fromEntries(
      Object.keys(SPEC.constants).map((name) => [name, asJson(EXPORTS[name])]),
    );
    expect(constants).toEqual(SPEC.constants);
  });

  it("maps every envelope vocabulary to its fallback", () => {
    const envelope = ["column_kinds", "column_scales", "sensitivity"];
    expect(octools.VOCABULARY_FALLBACKS).toEqual(
      Object.fromEntries(
        envelope.map((name) => [name, SPEC.vocabularies[name]?.fallback]),
      ),
    );
  });
});
