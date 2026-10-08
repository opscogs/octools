# octools

[![CI](https://github.com/opscogs/octools/actions/workflows/ci_pipeline.yml/badge.svg)](https://github.com/opscogs/octools/actions/workflows/ci_pipeline.yml)
[![PyPI](https://img.shields.io/pypi/v/octools)](https://pypi.org/project/octools/)
[![npm](https://img.shields.io/npm/v/@opscogs/octools)](https://www.npmjs.com/package/@opscogs/octools)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/opscogs/octools/blob/main/LICENSE)

OpsCogs standard interface for AI agent tools: the `OCTool` descriptor,
the result envelopes every tool returns, a conformance validator, and
pure-dict converters to the MCP and Anthropic tool shapes. A library
describes each capability once; any agent runtime registers it without
re-expressing it by hand. The contract is language-neutral and ships as
two packages that pass the same golden cases.

Documentation: [octools.docs.opscogs.com](https://octools.docs.opscogs.com).

## Packages

| Package                                                              | Language                      | Install                            |
| -------------------------------------------------------------------- | ----------------------------- | ---------------------------------- |
| [`octools`](https://pypi.org/project/octools/)                       | Python 3.12+                  | `pip install octools`              |
| [`@opscogs/octools`](https://www.npmjs.com/package/@opscogs/octools) | TypeScript (Node 22.18+, ESM) | `npm install @opscogs/octools zod` |

## Layout

| Path          | Contents                                                                 |
| ------------- | ------------------------------------------------------------------------ |
| `python/`     | The Python package and its tests.                                        |
| `typescript/` | The TypeScript package and its tests.                                    |
| `spec/`       | The language-neutral spec: JSON Schemas, vocabulary and golden fixtures. |
| `docs/`       | Published site sources, decision records and developer docs.             |
| `scripts/`    | Release and repository maintenance scripts.                              |

## Quick start: Python

Describe the arguments and result as pydantic models, wrap the function
in an `OCTool`, and list the tools from `all_tools()`:

```python
from pydantic import BaseModel, Field
from octools import (
    OCTool,
    RecordsEnvelope,
    input_schema_for,
    records_schema,
    to_mcp_tool,
)


class EchoArgs(BaseModel):
    values: list[str] = Field(description="Strings to echo back, one record each.")


class EchoRecord(BaseModel):
    value: str = Field(description="The echoed string.")
    position: int = Field(description="Zero-based position in the input.")


def echo_records(_dependency, *, values: list[str]) -> dict:
    records = [EchoRecord(value=v, position=i) for i, v in enumerate(values)]
    return RecordsEnvelope[EchoRecord](
        records=records, count=len(records), truncated=False
    ).model_dump(mode="json")


ECHO_RECORDS = OCTool(
    name="echo_records",
    description="Return each input string as one record with its position. Use it to check a tool round-trip. Returns a records envelope.",
    input_schema=input_schema_for(EchoArgs),
    output_schema=records_schema(EchoRecord),
    func=echo_records,
    access="local",
)


def all_tools() -> tuple[OCTool, ...]:
    return (ECHO_RECORDS,)


mcp_entry = to_mcp_tool(ECHO_RECORDS)
```

In your test suite, `assert validate_provider(my_tools) == []` lists every
conformance finding. `to_anthropic_tool(ECHO_RECORDS, name_prefix="demo_")`
gives the Anthropic `tools[]` entry the same way.

## Quick start: TypeScript

```ts
import {
  TabularEnvelope,
  readEnvelope,
  validateTabular,
} from "@opscogs/octools";

// Producer: a strict parse returns the wire form, ready for JSON.stringify.
const result = TabularEnvelope.parse({
  columns: ["host", "hits"],
  column_kinds: ["fqdn", "integer"],
  rows: [["a.demo.example", 3]],
  row_count: 1,
  truncated: false,
});
console.log(validateTabular(result)); // []

// Reader: tolerates fields and vocabulary values a newer producer adds.
const read = readEnvelope(TabularEnvelope, JSON.stringify(result));
console.log(read);
```

Wire keys are spelled exactly as the spec spells them (`column_kinds`,
`next_cursor`); API names are camelCase.

## Contributing

Read [CONTRIBUTING.md](https://github.com/opscogs/octools/blob/main/CONTRIBUTING.md) before opening a pull
request. Report vulnerabilities as described in
[SECURITY.md](https://github.com/opscogs/octools/blob/main/SECURITY.md). Everyone taking part follows the
[Code of Conduct](https://github.com/opscogs/octools/blob/main/CODE_OF_CONDUCT.md). Developer setup and the
exact commands CI runs are in
[docs/dev/onboarding.md](https://github.com/opscogs/octools/blob/main/docs/dev/onboarding.md).

## License

MIT. See [LICENSE](https://github.com/opscogs/octools/blob/main/LICENSE). The OpsCogs name and logos are
not covered by that license; see [NOTICE](https://github.com/opscogs/octools/blob/main/NOTICE).
