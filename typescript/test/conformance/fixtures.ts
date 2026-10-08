/** Discovery of the spec's golden cases under `spec/fixtures/`. */
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

/** The repository's `spec/` directory. */
export const SPEC_DIR = fileURLToPath(
  new URL("../../../spec/", import.meta.url),
);
/** The directory holding one subdirectory of cases per operation. */
export const FIXTURES_DIR = `${SPEC_DIR}fixtures/`;

/** One golden case: its operation, its file name and its contents. */
export interface Fixture {
  readonly operation: string;
  readonly name: string;
  readonly description: string;
  readonly input: Record<string, unknown>;
  readonly expected: unknown;
  readonly keys: readonly string[];
}

/** Return the parsed JSON file at `path` under `spec/`. */
export function readSpecJson(path: string): unknown {
  return JSON.parse(readFileSync(`${SPEC_DIR}${path}`, "utf8"));
}

/** Return every operation directory name, sorted. */
export function operations(): string[] {
  return readdirSync(FIXTURES_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

/** Return every entry under `spec/fixtures/` that is not an operation's case file. */
export function strayEntries(): string[] {
  return readdirSync(FIXTURES_DIR, { recursive: true, withFileTypes: true })
    .map((entry) => ({
      entry,
      path: relative(FIXTURES_DIR, join(entry.parentPath, entry.name)),
    }))
    .filter(({ entry, path }) => {
      const depth = path.split(sep).length;
      return entry.isDirectory()
        ? depth !== 1
        : depth !== 2 || !entry.name.endsWith(".json");
    })
    .map(({ path }) => path);
}

/** Return every case of `operation`, sorted by file name. */
export function fixtures(operation: string): Fixture[] {
  return readdirSync(`${FIXTURES_DIR}${operation}`)
    .filter((name) => name.endsWith(".json"))
    .sort()
    .map((name) => {
      const data = readSpecJson(`fixtures/${operation}/${name}`) as Record<
        string,
        unknown
      >;
      return {
        operation,
        name,
        description: data["description"] as string,
        input: data["input"] as Record<string, unknown>,
        expected: data["expected"],
        keys: Object.keys(data).sort(),
      };
    });
}
