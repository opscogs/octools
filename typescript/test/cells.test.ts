/** Cell predicates agree with the Python implementation beyond the spec fixtures. */
import { describe, expect, it } from "vitest";

import {
  type Cell,
  type ColumnKind,
  TabularEnvelope,
  validateTabular,
} from "../src/index.js";

/**
 * Candidate cells per kind, each with whether the Python implementation's
 * check accepts it (computed with Python's `ipaddress` and `datetime`).
 */
const PARITY: Partial<Record<ColumnKind, [Cell, boolean][]>> = {
  ip: [
    ["0.0.0.0", true],
    ["255.255.255.255", true],
    ["1.2.3", false],
    ["1.2.3.4.5", false],
    ["1.2.3.04", false],
    ["1.2.3.0", true],
    ["1.2.3.1000", false],
    ["1..3.4", false],
    ["", false],
    ["a.b.c.d", false],
    ["1.2.3.4/32", false],
    ["::", true],
    ["::1", true],
    ["1::", true],
    ["1:2:3:4:5:6:7:8", true],
    ["1:2:3:4:5:6:7:8:9", false],
    ["1:2:3:4:5:6:7", false],
    ["1::2::3", false],
    [":1:2:3:4:5:6:7", false],
    ["1:2:3:4:5:6:7:", false],
    ["::ffff:1.2.3.4", true],
    ["::ffff:1.2.3.04", false],
    ["1:2:3:4:5:6:1.2.3.4", true],
    ["1:2:3:4:5:6:7:1.2.3.4", false],
    ["::1.2.3.4:1", false],
    ["fe80::1%eth0", true],
    ["fe80::1%", false],
    ["fe80::1%a%b", false],
    ["%eth0", false],
    ["12345::", false],
    ["g::1", false],
    ["1:2:3:4:5:6:7::", true],
    ["::1:2:3:4:5:6:7", true],
    ["1::2:3:4:5:6:7:8", false],
    [":", false],
    ["::::", false],
    ["1:2", false],
    ["0:0:0:0:0:0:0:0", true],
    ["ABCD:ef01::", true],
    [":::1", false],
    ["1:::2", false],
    ["fe80::1/64", false],
    ["1:2:3:4:5:6:7:8:9:0", false],
    [":1::2", false],
    ["1::2:", false],
    [1, false],
  ],
  ip_block: [
    ["10.0.0.0/8", true],
    ["10.0.0.1/24", true],
    ["10.0.0.0/255.0.0.0", true],
    ["10.0.0.0/0.255.255.255", true],
    ["10.0.0.0/255.0.255.0", false],
    ["10.0.0.0/08", true],
    ["10.0.0.0/", false],
    ["10.0.0.0/33", false],
    ["10.0.0.0/32/1", false],
    ["10.0.0.0/-1", false],
    ["10.0.0.0/+8", false],
    ["::/0", true],
    ["::/128", true],
    ["::/129", false],
    ["::/255.0.0.0", false],
    ["fe80::1%eth0/64", true],
    ["10.0.0.1-10.0.0.1", true],
    ["10.0.0.1-10.0.0.0", false],
    ["::1-::2", true],
    ["::2-::1", false],
    ["10.0.0.1-::1", false],
    ["fe80::1%a-fe80::1%a", true],
    ["fe80::1%a-fe80::1%b", false],
    ["fe80::1%a-fe80::2", true],
    ["10.0.0.1-", false],
    ["-10.0.0.1", false],
    ["10.0.0.1-10.0.0.2-10.0.0.3", false],
    ["10.0.0.1", true],
    ["2001:db8::1", true],
    ["nonsense", false],
    ["10.0.0.0/0.0.0.0", true],
    ["10.0.0.0/255.255.255.255", true],
    ["10.0.0.0/1.2.3.4", false],
    ["1.2.3.4/0255.0.0.0", false],
    ["1.2.3.4/ 8", false],
    ["net/8", false],
    [":1::2/64", false],
    [1, false],
  ],
  timestamp: [
    ["2026-10-08T12:00:00Z", true],
    ["2026-10-08T12:00:00.1234567Z", true],
    ["2026-10-08T24:00:00Z", false],
    ["2026-10-08T23:59:60Z", false],
    ["2026-10-08T12:00:00+24:00", false],
    ["2026-10-08T12:00:00+23:60", false],
    ["2026-10-08T12:00:00+23:59", true],
    ["2026-10-08T12:00:00-00:00", true],
    ["0000-01-01T00:00:00Z", false],
    ["0001-01-01T00:00:00Z", true],
    ["2024-02-29T00:00:00Z", true],
    ["2023-02-29T00:00:00Z", false],
    ["1900-02-29T00:00:00Z", false],
    ["2000-02-29T00:00:00Z", true],
    ["2026-04-31T00:00:00Z", false],
    ["2026-13-01T00:00:00Z", false],
    ["2026-00-01T00:00:00Z", false],
    ["2026-01-00T00:00:00Z", false],
    ["2026-10-08 12:00:00Z", false],
    ["2026-10-08T12:00Z", false],
    ["2026-10-08T12:00:00.Z", false],
    ["2026-10-08T12:00:00+0530", false],
    ["9999-12-31T23:59:59z", true],
    [1, false],
  ],
  fqdn: [
    ["a", true],
    ["a.", true],
    ["a..", false],
    ["..", false],
    [".", false],
    ["a-b.c", true],
    ["a-.b", false],
    ["1.2.3.4", true],
    ["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.a", true],
    [
      "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.a",
      false,
    ],
    [
      "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      true,
    ],
    [
      "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      true,
    ],
    ["a b", false],
    [1, false],
  ],
  mac: [
    ["00:11:22:33:44:55", true],
    ["00-11-22-33-44-55", true],
    ["00:11:22:33:44:55:66:77", true],
    ["00:11:22:33:44:55:66", false],
    ["001122334455", false],
    ["GG:11:22:33:44:55", false],
    ["00:11:22:33:44:55\n", false],
    [1, false],
  ],
  big_integer: [
    ["0", true],
    ["-0", true],
    ["00", false],
    ["-", false],
    ["12a", false],
    ["1e3", false],
    [" 1", false],
    ["123456789012345678901234567890", true],
  ],
  integer: [
    [9007199254740991, true],
    [-9007199254740992, false],
    [1.5, false],
    [true, false],
  ],
  number: [
    [0, true],
    [-1.5, true],
    [false, false],
  ],
};

function table(kind: ColumnKind, cells: Cell[]): TabularEnvelope {
  return TabularEnvelope.parse({
    columns: cells.map((_, index) => `c${String(index)}`),
    column_kinds: cells.map(() => kind),
    rows: [cells],
    row_count: 1,
    truncated: false,
  });
}

describe("validateTabular parity", () => {
  for (const [kind, cases] of Object.entries(PARITY)) {
    it(kind, () => {
      const cells = cases.map(([cell]) => cell);
      const expected = cases.flatMap(([, fits], index) =>
        fits ? [] : [`/rows/0/${String(index)}`],
      );
      const found = validateTabular(table(kind as ColumnKind, cells));
      expect(found.map((finding) => finding.path)).toEqual(expected);
    });
  }
});

describe("validateTabular findings", () => {
  it("counts the bad cells and quotes the first", () => {
    const envelope = TabularEnvelope.parse({
      columns: ["n"],
      column_kinds: ["integer"],
      rows: [[1], ["x"], [null], [2.5]],
      row_count: 4,
      truncated: false,
    });
    const [finding] = validateTabular(envelope);
    expect(finding).toMatchObject({
      rule: "cell_kind",
      tool: null,
      path: "/rows/1/0",
    });
    expect(finding?.message).toBe(
      'column "n" (integer): 2 of 4 cells do not fit; first at row 1: "x"',
    );
  });

  it("treats an integral number as an integer however JSON wrote it", () => {
    const envelope = table("integer", JSON.parse("[1.0, 1e3]") as Cell[]);
    expect(validateTabular(envelope)).toEqual([]);
  });
});
