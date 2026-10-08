/** Every fixture under spec/fixtures/ passes against the TypeScript implementation. */
import { describe, expect, it } from "vitest";

import { fixtures, operations, strayEntries } from "./conformance/fixtures.js";
import { PENDING_OPERATIONS, RUNNERS, run } from "./conformance/runners.js";

const OPERATIONS = operations();
const RUNNABLE = Object.keys(RUNNERS);

describe("fixture discovery", () => {
  it("has a runner or a pending entry for every operation, never both", () => {
    expect([...RUNNABLE, ...PENDING_OPERATIONS].sort()).toEqual(OPERATIONS);
    expect(
      RUNNABLE.filter((name) => PENDING_OPERATIONS.includes(name)),
    ).toEqual([]);
  });

  it("holds only operation directories of .json cases", () => {
    expect(strayEntries()).toEqual([]);
  });

  it("counts every case on disk as run or pending", () => {
    const counted = OPERATIONS.flatMap((operation) => fixtures(operation));
    expect(counted.length).toBeGreaterThan(0);
    expect(
      counted.every(
        (fixture) => fixture.keys.join() === "description,expected,input",
      ),
    ).toBe(true);
    expect(counted.every((fixture) => fixture.description.length > 0)).toBe(
      true,
    );
  });
});

for (const operation of OPERATIONS) {
  describe(operation, () => {
    for (const fixture of fixtures(operation)) {
      if (PENDING_OPERATIONS.includes(operation)) {
        it.todo(fixture.name);
      } else {
        it(fixture.name, () => {
          expect(run(operation, fixture.input)).toStrictEqual(fixture.expected);
        });
      }
    }
  });
}
