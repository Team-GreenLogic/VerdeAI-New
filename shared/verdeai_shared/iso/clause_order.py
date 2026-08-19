"""Canonical ordering helpers for ISO clause identifiers."""

from __future__ import annotations

import re
from typing import TypeAlias

ClauseSortPart: TypeAlias = tuple[int, int | str]
ClauseSortKey: TypeAlias = tuple[ClauseSortPart, ...]

_TOKEN_RE = re.compile(r"\d+|[^\d.\-_/\s]+")


def clause_sort_key(clause_id: object) -> ClauseSortKey:
    """Return a natural key for dotted clause ids.

    Numeric components compare numerically, so ``9.3`` precedes ``10.1`` and
    ``6.1.2`` precedes ``6.1.10``. Parent identifiers are prefixes of their
    descendants and therefore sort first. Nonnumeric identifiers remain
    deterministic and sort after numeric clauses.
    """
    value = str(clause_id or "").strip()
    if not value:
        return ((2, ""),)

    parts: list[ClauseSortPart] = []
    for token in _TOKEN_RE.findall(value):
        if token.isdigit():
            parts.append((0, int(token)))
        else:
            parts.append((1, token.casefold()))
    return tuple(parts) or ((2, value.casefold()),)

