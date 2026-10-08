"""Conformance findings shared by the schema checker and the validator.

A finding is plain data: a library asserts ``findings == []`` in its own
tests and gets a readable diff when something drifts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class Finding:
    """One conformance problem.

    ``rule`` is a stable snake_case identifier for the rule that fired,
    ``message`` explains it for a person, ``tool`` names the descriptor it
    concerns (``None`` for a bare schema check), and ``path`` is a JSON
    pointer into the schema where that applies.
    """

    rule: str
    message: str
    tool: str | None = None
    path: str | None = None


__all__ = ["Finding"]
