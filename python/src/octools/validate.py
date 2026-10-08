"""Conformance validation of ``OCTool`` descriptors and providers.

``validate_provider`` is what a library runs in its own tests
(``assert validate_provider(my_tools) == []``). Every rule returns a
``Finding`` rather than raising, so a run reports everything at once.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace

from octools.descriptor import NAME_RE, OCTool, ToolProvider, check_tool_listing
from octools.findings import Finding
from octools.schema import strict_clean

SENTENCE_RE = re.compile(r"[.!?]+(?=\s|$)")
MIN_SENTENCES = 2
MAX_SENTENCES = 4
SCHEMA_ESCAPE_KEY = "schema_escape"
"""``meta`` key recording why a tool has no closed ``output_schema``."""
ALIAS_OF_KEY = "alias_of"
"""``meta`` key on a deprecated alias naming the tool it stands for."""


def count_sentences(text: str) -> int:
    """Count sentences as runs of ``.``, ``!`` or ``?`` followed by space or end.

    A heuristic: an abbreviation such as ``e.g.`` followed by a space counts
    as a sentence end, so write descriptions without them.
    """
    return len(SENTENCE_RE.findall(text.strip()))


def _has_escape(tool: OCTool) -> bool:
    """Return True when ``meta`` records a non-empty schema escape reason."""
    reason = tool.meta.get(SCHEMA_ESCAPE_KEY)
    return isinstance(reason, str) and bool(reason.strip())


def _output_is_open(tool: OCTool) -> bool:
    """Return True when the tool has no output schema or an open root object."""
    return (
        tool.output_schema is None
        or tool.output_schema.get("additionalProperties") is True
    )


def _artifact_shaped(schema: Mapping[str, object] | None) -> bool:
    """Return True when ``schema`` declares an ``artifact`` property."""
    if schema is None:
        return False
    properties = schema.get("properties")
    return isinstance(properties, Mapping) and "artifact" in properties


def validate_tool(tool: OCTool) -> list[Finding]:
    """Return every conformance finding for one descriptor.

    Rules: ``name_pattern``; ``description_sentences`` (two to four); every
    ``strict_clean`` finding on ``input_schema`` (path prefixed with
    ``/input_schema``); ``output_schema_escape`` when the output schema is
    missing or open without ``meta["schema_escape"]``; ``artifact_envelope``
    when ``result_kind`` is ``artifact`` but the output schema has no
    ``artifact`` property; ``deprecated_alias`` when a deprecated tool does
    not name another tool in ``meta["alias_of"]``.
    """
    findings: list[Finding] = []
    if not NAME_RE.fullmatch(tool.name):
        findings.append(
            Finding(
                rule="name_pattern",
                message=f"name must match {NAME_RE.pattern}",
                tool=tool.name,
            )
        )
    sentences = count_sentences(tool.description)
    if not MIN_SENTENCES <= sentences <= MAX_SENTENCES:
        findings.append(
            Finding(
                rule="description_sentences",
                message=f"description has {sentences} sentences; write "
                f"{MIN_SENTENCES} to {MAX_SENTENCES}",
                tool=tool.name,
            )
        )
    findings.extend(
        replace(finding, tool=tool.name, path=f"/input_schema{finding.path}")
        for finding in strict_clean(tool.input_schema)
    )
    if _output_is_open(tool) and not _has_escape(tool):
        findings.append(
            Finding(
                rule="output_schema_escape",
                message="output_schema is missing or open; record the reason in "
                f"meta[{SCHEMA_ESCAPE_KEY!r}] or ship a closed schema",
                tool=tool.name,
            )
        )
    if tool.result_kind == "artifact" and not _artifact_shaped(tool.output_schema):
        findings.append(
            Finding(
                rule="artifact_envelope",
                message="artifact tools return the artifact envelope; output_schema "
                "must declare an 'artifact' property",
                tool=tool.name,
            )
        )
    alias = tool.meta.get(ALIAS_OF_KEY)
    if tool.deprecated and (not isinstance(alias, str) or alias == tool.name):
        findings.append(
            Finding(
                rule="deprecated_alias",
                message="deprecated tools name the tool they alias in "
                f"meta[{ALIAS_OF_KEY!r}]",
                tool=tool.name,
            )
        )
    return findings


def validate_provider(provider: ToolProvider) -> list[Finding]:
    """Return every conformance finding for a provider and all its tools.

    Adds the listing rules (``unstable_order``, ``duplicate_name``),
    ``not_octool`` for foreign objects in the listing, and
    ``alias_target_missing`` when a deprecated alias names a tool the
    provider does not list. An empty list means the provider conforms.
    """
    findings = check_tool_listing(provider)
    tools = list(provider.all_tools())
    names = {tool.name for tool in tools if isinstance(tool, OCTool)}
    for index, tool in enumerate(tools):
        if not isinstance(tool, OCTool):
            findings.append(
                Finding(
                    rule="not_octool",
                    message=f"all_tools()[{index}] is {type(tool).__name__}, "
                    "not OCTool",
                )
            )
            continue
        findings.extend(validate_tool(tool))
        alias = tool.meta.get(ALIAS_OF_KEY)
        if tool.deprecated and isinstance(alias, str) and alias not in names:
            findings.append(
                Finding(
                    rule="alias_target_missing",
                    message=f"alias target {alias!r} is not listed by this provider",
                    tool=tool.name,
                )
            )
    return findings


__all__ = [
    "ALIAS_OF_KEY",
    "MAX_SENTENCES",
    "MIN_SENTENCES",
    "SCHEMA_ESCAPE_KEY",
    "count_sentences",
    "validate_provider",
    "validate_tool",
]
