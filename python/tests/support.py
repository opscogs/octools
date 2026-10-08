"""Helpers shared by unit tests. Callers pass the contracts their file requires."""

from octools import OCTool

_UNSET = object()


def build_tool(
    *,
    description: str,
    func,
    input_schema: dict,
    output_schema=_UNSET,
    **overrides,
) -> OCTool:
    """Build an ``OCTool`` from explicit description, callable, and schemas."""
    fields = {
        "name": "sample_tool",
        "description": description,
        "input_schema": input_schema,
        "func": func,
        "access": "local",
    }
    if output_schema is not _UNSET:
        fields["output_schema"] = output_schema
    fields.update(overrides)
    return OCTool(**fields)
