/** The package ships the repository's license and notice unchanged. */
import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

it.each(["LICENSE", "NOTICE"])("ships the repository %s", (name) => {
  const read = (path: string) =>
    readFileSync(new URL(path, import.meta.url), "utf8");
  expect(read(`../${name}`)).toBe(read(`../../${name}`));
});
