"""Deterministic parent-clause aggregation.

ISO clause ids are hierarchical — 7.4 is the parent of 7.4.1/7.4.2/7.4.3, 6.1 of
6.1.1-6.1.4. Each clause is analysed independently, so a parent is judged on whatever
evidence its own (broader) requirement text retrieved, with no knowledge of its children's
verdicts. That produced parents scored more leniently than their own children: gold 7.4.3 =
Not Met implies gold 7.4 = Not Met, but the analyser returned Partially Met for the parent.

Asking the LLM to reason about hierarchy is the wrong tool — the relationship is exact and
knowable from the id. These are pure functions (no I/O, no LLM) applied as a post-pass once
every clause verdict is persisted.
"""

from __future__ import annotations

from typing import Any

# Worst-child-wins order: the first entry present among a parent's children is the parent's
# decision. Anything unrecognised (e.g. the "Error" decision the actor records on an
# exception) is treated as Insufficient Evidence — it means "cannot determine", and must
# never silently read as Met.
_PRIORITY: tuple[str, ...] = ("Not Met", "Insufficient Evidence", "Partially Met", "Met")
_UNKNOWN_DECISION = "Insufficient Evidence"


def parent_of(clause_id: str) -> str | None:
    """Return the parent clause id, or None for a top-level clause.

    "7.4.3" -> "7.4"; "7.4" -> "7"; "7" -> None. Whether the returned id is itself a real
    clause is the caller's problem — ISO has no clause "7", only 7.1, 7.2, ...
    """
    cid = (clause_id or "").strip()
    if "." not in cid:
        return None
    return cid.rsplit(".", 1)[0]


def _depth(clause_id: str) -> int:
    return clause_id.count(".")


def aggregate_parent_decisions(results: list[dict[str, Any]]) -> dict[str, str]:
    """Derive parent decisions from their children.

    Returns ``{clause_id: new_decision}`` containing only parents whose decision actually
    changes, so the caller can skip no-op writes.

    Deepest clauses are resolved first, so a parent of parents composes correctly: 7.5.3
    Not Met makes 7.5 Not Met even when 7.5's own analysis said otherwise.
    """
    decisions: dict[str, str] = {
        r["clause_id"]: r.get("decision", _UNKNOWN_DECISION)
        for r in results
        if r.get("clause_id")
    }

    # Only ids that actually exist as analysed clauses can be parents — "7" is not a clause.
    children_by_parent: dict[str, list[str]] = {}
    for cid in decisions:
        parent = parent_of(cid)
        if parent and parent in decisions:
            children_by_parent.setdefault(parent, []).append(cid)

    changed: dict[str, str] = {}
    # Deepest first so an aggregated child feeds into its own parent.
    for parent in sorted(children_by_parent, key=_depth, reverse=True):
        child_decisions = {
            changed.get(c, decisions[c]) for c in children_by_parent[parent]
        }
        normalised = {d if d in _PRIORITY else _UNKNOWN_DECISION for d in child_decisions}
        derived = next(d for d in _PRIORITY if d in normalised)
        if derived != decisions[parent]:
            changed[parent] = derived

    return changed
