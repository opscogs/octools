---
status: accepted
version: 1.1.1
date: 2026-10-08
decision-makers: OpsCogs maintainers
---

# OCTL-0005 column kinds: `ip_block` and `big_integer`

## Context and Problem Statement

`column_kinds` is a closed vocabulary ([OCTL-0001](./OCTL-0001-descriptor-origin.md)):
eight kinds, each chosen so a renderer can align, typeset or chart a column
from the declared kind alone. A producer needs two column shapes the eight
cannot state honestly.

- **Address text that is not one address.** A shared prefix-arithmetic tool
  returns columns such as `prefix`, `within` and `match` whose cells are a
  CIDR prefix (`192.0.2.0/24`) or a `first-last` range. `ip` promises one
  address in `ipv4` or `ipv6` format, so the only honest kind is `text`. A
  renderer then sets `192.0.2.0/24` in the body font beside `first` and
  `last` columns it sets monospace.
- **A count that can outgrow a JSON number.** An IPv6 block's `size` is up
  to 2^128. JSON numbers are exact only to 2^53, so the tool sends large
  values as decimal strings. `integer` maps to the JSON Schema `integer`
  type, so a string cell makes it a lie, and the only honest kind is `text`,
  which renders left-aligned beside a right-aligned `prefix_len`.

A third gap is meaning. A schema-less tabular producer, such as an ad-hoc
query tool, returns terse source column names a model cannot interpret. A
records tool describes its fields in its output schema; a tabular tool has
no equivalent, so a model makes an extra call to learn what the columns
mean, or guesses.

In each case the producer has the right answer and no way to say it, and
the consumer's column-name heuristic cannot override a declared kind (nor
should it). A consumer cannot add a kind of its own, so this is an upstream
change.

How does `column_kinds` let a producer declare address blocks and integers
larger than a JSON number, how does a producer say what a column means, and
how do producers, readers and renderers handle the result?

## Decision Drivers

- Every existing kind keeps the promise it gives a reader today; no reader
  gains a type check it does not know it needs.
- The vocabulary stays closed and serves renderers: a kind exists when a
  renderer treats its column differently.
- A reader never loses precision on a large integer, and a small value never
  needs parsing.
- A reader that predates a kind or field still reads every cell.
- `octools` depends on `pydantic` and the standard library only.

## Considered Options

- **A.** New kinds `ip_block` and `big_integer`
- **B.** Widen `ip` and `integer`
- **C.** Separate `prefix` and `range` kinds
- **D.** A free-form per-column format hint

## Decision Outcome

Chosen option: **A, new kinds `ip_block` and `big_integer`**, because it
states both shapes honestly without weakening any existing kind's promise,
keeps a mixed prefix-and-range column under one kind, and keeps the
vocabulary closed.

### The kinds

Two kinds are added, at the end of `COLUMN_KINDS` and the `ColumnKind`
literal, so documentation order stays stable:

| Kind          | JSON Schema                                                   | Render                  |
| ------------- | ------------------------------------------------------------- | ----------------------- |
| `ip_block`    | `string`: an address, a CIDR prefix, or a `first-last` range  | monospace, left-aligned |
| `big_integer` | `integer`, or `string` of decimal digits with an optional `-` | right-aligned           |

- **`ip_block`** holds any contiguous set of addresses in one family, written
  one of three ways: a bare address (a block of one), `address/length`, or
  `first-last`. A bare address is allowed so a column whose rows mix one
  address with prefixes (`a`, `b`, `target`) still has one kind. A column
  that only ever holds single addresses stays `ip`, which keeps its stronger
  promise. The kind says nothing about whether the prefix is aligned on its
  length; that is the tool's contract, not the renderer's.
- **`big_integer`** is an integer of any size. A cell is a JSON integer when
  its magnitude fits in 2^53 - 1 and a decimal string otherwise, so a reader
  never loses precision and a small value never needs parsing. A producer
  may send every cell as a string. A renderer right-aligns both forms and
  sorts numerically, not lexically. `total_count`
  ([OCTL-0002](./OCTL-0002-result-paging.md)) follows the same
  integer-or-decimal-string rule.
- **Parsing does not check cells against their kind.** `TabularEnvelope`
  checks the vocabulary and the count of `column_kinds`, never a cell's
  content, exactly as for the existing eight. The content check is the
  opt-in `validate_tabular` below.
- `COLUMN_KINDS` stays closed: an unknown value is still a validation error
  on `TabularEnvelope`. Consumers still cannot add kinds.

### Checking cells: `validate_tabular`

```python
def validate_tabular(envelope: TabularEnvelope) -> list[Finding]: ...
```

A function exported from the package root. It returns at most one `Finding`
per column, for each column holding a cell that does not fit its kind, so a
producer's test reads the same way as a descriptor's:

```python
assert validate_tabular(TabularEnvelope.model_validate(tool.func(None))) == []
```

- **Opt-in, never on parse.** `TabularEnvelope` does not call it. A reader
  must not reject a whole result over one bad cell, and a large table should
  not pay for address parsing on every read. The check exists to catch a
  producer's bug in the producer's own tests.
- **Every kind, not only the new two.** A checker that covered two of ten
  kinds would leave the reader guessing which promises hold. An envelope
  with no `column_kinds` has nothing to check and returns `[]`.
- **`None` always passes.** A null cell is a missing value under any kind.
- **One finding per column, bounded by construction.** A table of a million
  rows with a broken column yields one finding, not a million, so the
  function is safe to run over a live result as well as a fixture, with no
  cap to tune. Bad cells in one column almost always share one cause, and a
  producer fixes the cause, not each cell. `rule` is `cell_kind`, `path` is
  a JSON pointer to the first bad cell (`/rows/3/2`), `tool` is `None` (the
  caller may `replace` it), and `message` names the column, the kind, the
  first bad value and how many cells in the column failed
  (`column 'size' (big_integer): 1204 of 50000 cells do not fit; first at
row 3: 'n/a'`). Findings come in column order, so the list is stable and
  diffs cleanly. Not one finding per cell, which is unbounded, and not a
  `max_findings` cap, which truncates arbitrarily, adds a knob, and hides
  whether the rest of the table is clean.
- **Standard library only** (`ipaddress`, `datetime`, `re`), so the
  dependency rule holds.

Each kind accepts:

| Kind          | A cell passes when it is                                                                                                                                   |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `text`        | a `str`                                                                                                                                                    |
| `number`      | an `int` or a finite `float`, not a `bool`                                                                                                                 |
| `integer`     | an `int`, not a `bool`, with magnitude at most 2^53 - 1 (a larger value belongs in `big_integer`)                                                          |
| `boolean`     | a `bool`                                                                                                                                                   |
| `timestamp`   | a `str` in RFC 3339 `date-time` form: date, `T`, time, and a `Z` or numeric offset                                                                         |
| `ip`          | a `str` that `ipaddress.ip_address` accepts                                                                                                                |
| `fqdn`        | a `str` of dot-separated labels, each 1-63 of letters, digits and `-` with no leading or trailing `-`, at most 253 in total, with an optional trailing dot |
| `mac`         | a `str` of six or eight hex pairs joined consistently by `:` or `-`                                                                                        |
| `ip_block`    | a `str` that is an address, an `ip_network(strict=False)` prefix, or `first-last` with both addresses in one family and `first <= last`                    |
| `big_integer` | an `int` (not a `bool`), or a `str` matching `^-?(0\|[1-9][0-9]*)$`                                                                                        |

`integer` stops at 2^53 - 1 because a larger value cannot survive a
JavaScript reader; it belongs in `big_integer`. `ip_block` accepts host bits
set (`192.0.2.1/24`) because the kind makes no alignment promise. Parsing
never applies these checks, so they bind only producers that opt in.

### Charting `big_integer` and `column_scales`

Precision is not what a chart needs. A JavaScript number is a float64,
exact only to 2^53, but it carries about 16 significant digits and reaches
1.8 x 10^308, so `Number("340282366920938463463374607431768211456")` lands
within one part in 10^16 of 2^128, far below the one part in a few thousand
that a pixel on the widest axis can show. Plotting a float64 is visually
exact. What must stay exact is every digit a person reads. The problem is
range: IPv6 block sizes run from 1 to 2^128, and on a linear axis everything
but the largest bar is invisible.

A renderer plots the float64 and prints the exact value, picks the axis
scale from the data, and follows a producer's scale hint; rescaling into a
unit applies to tick labels only. The rules for the other approaches:

- Chart the column, rather than declining to; it is the column a reader
  most wants charted.
- Rescale into a unit (`x 10^36`, `x 2^64`) for tick labels only. Applied to
  plotted data it does nothing a log axis does not do, and it misleads when
  the renderer picks the wrong base for the domain.
- Use `column_scales`, not a derived log column such as `size_log2`, which
  duplicates data; the column prefix arithmetic would add already exists
  (`prefix_len`).
- Plot `Number(cell)`, not `BigInt`: no mainstream charting library accepts
  `BigInt` on a scale, and the precision it buys is invisible.

The producer hint is needed because the data can tell a renderer whether an
axis should be logarithmic, but not its base. An IPv6 block's size is
exactly 2^(128 - prefix length): on a base-2 axis a tick at 2^64 is a /64,
while ticks at 10^19 and 10^29 line up with nothing a reader knows. Only the
producer knows the domain, so only it can say this. The cost is a new
envelope field and the first presentation hint in an envelope.

`column_scales` ships with the kinds it serves. IPv6 sizes are the main
`big_integer` workload and base-2 ticks are what makes them readable, so
renderers support the kinds and the scale together, in the same release.

```python
ColumnScale = Literal["linear", "log10", "log2"]
COLUMN_SCALES: tuple[str, ...] = ("linear", "log10", "log2")

column_scales: list[ColumnScale | None] | None = Field(
    default=None, exclude_if=_is_none, description=...
)
```

- **Parallel to `columns`**, like `column_kinds`: one entry per column, and
  `TabularEnvelope` rejects a list of the wrong length. `None` for the whole
  field or for one column means the renderer applies the data rule below.
  Omitted, the envelope serializes exactly as before.
- **Numeric columns only.** A non-null scale requires `column_kinds` to be
  present and that column's kind to be `number`, `integer` or
  `big_integer`; anything else is a validation error on strict parse,
  because a scale on an `fqdn` column is a producer bug with no sensible
  reading. Under `read_envelope`, a scale on a column whose kind is
  non-numeric or degraded to `text` reads as `None` instead, so a kind the
  reader does not know never costs it the envelope.
- **Closed**, like `COLUMN_KINDS`, and grown the same way.
- **A hint, not a command.** A renderer that cannot draw a given scale, or
  is not charting at all, ignores it.

```json
{
  "columns": ["prefix", "prefix_len", "size"],
  "column_kinds": ["ip_block", "integer", "big_integer"],
  "column_scales": [null, null, "log2"],
  "rows": [
    ["2001:db8::/32", 32, "79228162514264337593543950336"],
    ["2001:db8::/64", 64, "18446744073709551616"]
  ],
  "row_count": 2,
  "truncated": false
}
```

### Column descriptions: `column_descriptions`

```python
column_descriptions: list[str | None] | None = Field(
    default=None,
    exclude_if=_is_none,
    description=(
        "One short description per column, in column order; "
        "null where a column has none."
    ),
)
```

- **Parallel to `columns`**, like `column_scales`: one entry per column,
  `None` where a column has no description, and `TabularEnvelope` rejects a
  list of the wrong length with a `ValueError`. Omitted, the envelope
  serializes exactly as before, and `tabular_schema()` declares the field as
  an optional property.
- **Meaning, not presentation.** A description tells a model or a person
  what a column holds, so a result needs no separate describe-table call.
  It says nothing about how to render the column; that is the kind's and the
  scale's job.
- **Tolerant on read.** `read_envelope`
  ([OCTL-0006](./OCTL-0006-tolerant-readers.md)) drops a malformed value
  (a list of the wrong length, or an entry that is neither a string nor
  null) and reads the envelope without it, because a missing description
  never costs a reader a cell. Strict validation still rejects it.
- **First page only, for a paged producer.** Descriptions do not change
  from page to page, so a producer that pages
  ([OCTL-0002](./OCTL-0002-result-paging.md)) may send them on the first
  page and leave them out of later pages to save tokens. A reader keeps the
  descriptions from the first page.

### Renderer guidance

A renderer charting a numeric column:

- never rewrites the cell; the envelope stays exact end to end;
- plots `Number(cell)`, and prints the original cell for every value a
  person reads (table cells, tooltips, data labels, exports), sorting a
  `big_integer` column by `BigInt(cell)`;
- follows the column's scale when one is declared:
  - `log2`: a log axis ticked at whole powers of two labelled `2^n`,
    stepped so there are roughly five to eight ticks (`2^0`, `2^32`,
    `2^64`, `2^96`, `2^128`);
  - `log10`: a log axis ticked at powers of ten;
  - `linear`: a linear axis even when the range is wide;
- otherwise uses a logarithmic axis when every plotted value is positive and
  the largest is at least 1000 times the smallest, and a linear axis
  otherwise;
- falls back to linear for a log scale when a value is zero or negative;
- formats base-10 ticks compactly (`3.4 x 10^38`), since tick labels are
  rounded by nature; exact values stay in tooltips and labels.

### Readers that do not know a kind

A closed vocabulary that grows means an envelope can carry a kind or a scale
its reader predates. The rule:

- **A non-Python reader** (a chat UI, a report renderer) treats a kind it
  does not know as `text`, and a scale it does not know (or the whole
  `column_scales` field) as absent. That is always safe, because every cell
  is at least displayable text and every chart has the data rule.
- **A Python reader** follows the same rule through `read_envelope`
  ([OCTL-0006](./OCTL-0006-tolerant-readers.md)): an unknown kind reads as
  `text`, an unknown scale as `None`, and a scale on a column whose kind is
  non-numeric or degraded to `text` as `None`. Constructing or strictly
  validating a `TabularEnvelope` still rejects all three, so a producer's
  typo fails in the producer's tests. A Python reader of envelopes from another
  process needs `octools >= 1.0`, the first release with `read_envelope`.
- **Either reader** treats an absent or malformed `column_descriptions` as
  no descriptions; a reader that predates the field drops it and reads every
  cell.

### Consequences

- Good: a prefix, range or large count is declared with a kind that
  renders it correctly, instead of falling back to `text`.
- Good: `ip` and `integer` keep their promises, so no existing
  reader changes.
- Good: a large integer is exact end to end, and a small one needs
  no parsing.
- Good: a producer can assert its cells fit their kinds with one
  test line, and the check is bounded on any table size.
- Good: an IPv6 size column charts legibly, with ticks that line up
  with prefix lengths.
- Good: a tabular result carries what its columns mean, so a model
  reads a schema-less table without a separate describe call.
- Bad: every renderer has two more kinds to handle, and a reader
  that predates them falls back to `text`.
- Bad: `column_scales` is the first presentation hint in an
  envelope.
- Bad: descriptions cost tokens on every page that carries them,
  which is why a paged producer sends them on the first page only.
- Bad: a `big_integer` cell has two JSON forms, so a reader
  converts before comparing.
- Bad: remote readers see `SPEC_VERSION` `"1.0"`, a new major, so a
  reader that accepts only major `0` and a consumer test that pins `"0.1"`
  each update once.

### Confirmation

- The `TabularEnvelope` model rejects an unknown kind or scale, a
  `column_scales` or `column_descriptions` list of the wrong length, and a
  non-null scale on a column that is not `number`, `integer` or
  `big_integer`.
- `column_descriptions` is left out of the dump when unset, appears in
  `tabular_schema()` as an optional property, and a malformed value is
  dropped by `read_envelope` and rejected by strict validation.
- `validate_tabular` has tests for each kind's pass and fail cells, `None`
  cells, an envelope without `column_kinds`, and one finding per column
  with the first bad cell's pointer and the failure count.
- `read_envelope` has tests that an unknown kind reads as `text`, an
  unknown scale as `None`, and a scale on a non-numeric or degraded column
  as `None`.
- A producer's own tests assert `validate_tabular(...) == []` on its
  tabular results.

## Pros and Cons of the Options

### A. New kinds `ip_block` and `big_integer` (chosen)

- Good: each existing kind keeps its guarantee.
- Good: one kind covers addresses, prefixes and ranges, which
  prefix arithmetic mixes in one column.
- Good: the vocabulary stays closed.
- Bad: a renderer has two more kinds to support.

### B. Widen `ip` and `integer`

- Good: no new kinds.
- Bad: widening `ip` to accept prefixes and ranges breaks the one
  guarantee `ip` gives a reader: a value that parses as an address. A reader
  that feeds an `ip` cell to an address parser starts failing on
  `192.0.2.0/24`.
- Bad: widening `integer` to accept strings does the same to a
  reader that treats an `integer` cell as a JSON number, and makes the
  `integer` row of the kind-to-schema table false. `big_integer` costs a
  renderer one more right-aligned kind; widening costs every existing
  reader a type check it does not know it needs.

### C. Separate `prefix` and `range` kinds

- Good: each kind names a single notation.
- Bad: a column that mixes them, which prefix arithmetic produces
  routinely (a summary of a range is a list of prefixes, an exclusion of a
  prefix is a range), goes back to `text`.
- Bad: the renderer treats them identically, and the vocabulary is
  for renderers.

### D. A free-form per-column format hint

- Good: a producer can describe any shape without a spec change.
- Bad: it ends the closed vocabulary, which is the property
  [OCTL-0001](./OCTL-0001-descriptor-origin.md) chose it for.

## More Information

Ships in octools 1.0.0.

`SPEC_VERSION` is `"1.0"` at this release; the major follows
[OCTL-0006](./OCTL-0006-tolerant-readers.md), where 1.0 starts the
compatibility contract. The envelopes are part of the published spec,
and `spec_version` in an MCP tool's `_meta` is the only signal a remote
reader has that the output may carry a kind or field it does
not know. `SPEC_VERSION` tracks the format, not the function surface: two
kinds and one optional field are a format change, where a new helper such
as `validate_tabular` is not.

`column_descriptions` ships in octools 1.1.0 with `SPEC_VERSION` `"1.1"`.
A Python reader needs
`octools >= 1.1` to keep the descriptions; an older one drops them.

Every addition passes the minor-release test in
[OCTL-0006](./OCTL-0006-tolerant-readers.md): the new kinds have the `text`
fallback, and a reader that drops `column_scales` or `column_descriptions`
still reads every cell correctly.

This is not on the 1.x scope fence in
[OCTL-0001](./OCTL-0001-descriptor-origin.md), which lists descriptor
fields and runtime behaviour, not envelope fields or vocabulary values.

Related records: [OCTL-0001](./OCTL-0001-descriptor-origin.md) (the closed
`column_kinds` vocabulary) and [OCTL-0006](./OCTL-0006-tolerant-readers.md)
(`read_envelope` and the minor-release test).
