"""Clause requirement decomposition — atomic sub-requirements from prose.

ISO clauses are seeded with a single prose ``requirements`` blob (see
``services/iso-knowledge/app/seed_iso.py``), which makes both retrieval (one
query vector mixing many obligations) and state comparison (only 3 generic
fields per clause) coarse. ``requirements_list`` decomposes that prose into
atomic, individually-checkable obligations.

Two ways to populate it:
- ``naive_decompose_requirements`` — deterministic sentence-split fallback, used
  at runtime by the gap-analyzer pipeline whenever a clause has no LLM-curated
  ``requirements_list`` yet. Always available, no LLM call, no extra latency.
- The LLM-based decomposition script (``services/iso-knowledge/app/decompose_requirements.py``)
  produces a cleaner, hand-reviewable list using the same ``SubRequirement`` shape
  and persists it onto the clause document, taking priority over the naive split.
"""

from __future__ import annotations

import re

from pydantic import BaseModel


class SubRequirement(BaseModel):
    id: str
    text: str


class SubRequirementList(BaseModel):
    """Container so LLM decomposition can use structured (schema-validated) output."""

    items: list[SubRequirement]


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;])\s+(?=[A-Z(])")
_MIN_SENTENCE_CHARS = 15


def naive_decompose_requirements(clause_id: str, requirements: str) -> list[dict[str, str]]:
    """Deterministically split a requirements blob into sentence-level obligations.

    Not as clean as an LLM decomposition (a single sentence can still bundle
    multiple obligations), but it is a strict improvement over one monolithic
    blob, requires no LLM call, and is always available.
    """
    text = (requirements or "").strip()
    if not text:
        return []

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    sentences = [s for s in sentences if len(s) >= _MIN_SENTENCE_CHARS]
    if not sentences:
        sentences = [text]

    return [{"id": f"{clause_id}-{i + 1}", "text": s} for i, s in enumerate(sentences)]


def clause_requirements_list(clause: dict[str, object]) -> list[dict[str, str]]:
    """Return the best available decomposition for a clause doc.

    Prefers a persisted, LLM-curated ``requirements_list``; falls back to a
    naive sentence split of the ``requirements`` prose.
    """
    stored = clause.get("requirements_list")
    if isinstance(stored, list) and stored:
        return [
            {"id": str(r.get("id", "")), "text": str(r.get("text", ""))}
            for r in stored
            if isinstance(r, dict) and r.get("text")
        ]
    clause_id = str(clause.get("clause_id", ""))
    requirements = str(clause.get("requirements", ""))
    return naive_decompose_requirements(clause_id, requirements)
