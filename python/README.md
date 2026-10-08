# octools

[![PyPI](https://img.shields.io/pypi/v/octools)](https://pypi.org/project/octools/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/opscogs/octools/blob/main/LICENSE)

OpsCogs standard interface for AI agent tools: the `OCTool` descriptor,
the result envelopes every tool returns, a conformance validator, and
pure-dict converters to the MCP and Anthropic tool shapes. A library
describes each capability once; any agent runtime registers it without
re-expressing it by hand.

A TypeScript package, [`@opscogs/octools`](https://www.npmjs.com/package/@opscogs/octools),
implements the same contract.

## Install

Python 3.12 or newer and pydantic 2.12 or newer (the only dependency).

```sh
pip install octools
```

## Quick start

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
conformance finding. List a provider from the command line with
`octools list my_tools`; `octools list octools.example` lists the built-in
demo provider.

## Links

- [Documentation](https://octools.docs.opscogs.com)
- [Source and issues](https://github.com/opscogs/octools)
- [Changelog](https://github.com/opscogs/octools/blob/main/CHANGELOG.md)

## License

MIT. See [LICENSE](https://github.com/opscogs/octools/blob/main/LICENSE). The OpsCogs name and logos are
not covered by that license; see [NOTICE](https://github.com/opscogs/octools/blob/main/NOTICE).
