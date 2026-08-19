"""Deterministic parent-clause aggregation.

ISO clause ids are hierarchical — 7.4 is the parent of 7.4.1/7.4.2/7.4.3, 6.1 of
6.1.1-6.1.4. Each clause is analysed independently, so a parent is judged on whatever
evidence its own (broader) requirement text retrieved, with no knowledge of its children's
verdicts. That produced parents scored more leniently than their own children: gold 7.4.3 =
Not Met implies gold 7.4 = Not Met, but the analyser returned Partially Met for the parent.

Asking the LLM to reason about hierarchy is the wrong tool — the relationship is exact and
knowable from the id. These are pure functions (no I/O, no LLM) applied as a post-pass once
every clause verdict is persisted.

Some parents are ISO headings with no normative text of their own — 6.1, 6.2, 7.4, 7.5, 9.1,
9.2 (verified against ISO 14001:2015; the "shall" text starts only at the .1 sub-clause).
Those are never independently analysed at all (see
``verdeai_shared.iso.slots.clause_slot_schema``), so their entire result — decision *and*
requirement detail — comes from their children. ``aggregate_children_slots`` builds the
latter: a pooled coverage view assembled from real child slot fills, never a fabricated
schema of the parent's own.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from verdeai_shared.iso.clause_order import clause_sort_key
from verdeai_shared.iso.slots import build_slot_credit_rows, pool_coverage

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


def aggregate_parent_decisions(
    results: list[dict[str, Any]],
    known_clause_ids: set[str] | None = None,
) -> dict[str, str]:
    """Derive parent decisions from their children.

    Returns ``{clause_id: new_decision}`` containing only parents whose decision actually
    changes, so the caller can skip no-op writes.

    Deepest clauses are resolved first, so a parent of parents composes correctly: 7.5.3
    Not Met makes 7.5 Not Met even when 7.5's own analysis said otherwise.

    ``known_clause_ids``, if given, is the full set of clause ids that exist in the ISO
    version being analysed. Without it (the default — every caller had this shape before
    title-only clauses existed), a parent is only recognised if it *already has a persisted
    decision of its own*, which held for every clause when every clause was independently
    analysed. Title-only clauses (see ``verdeai_shared.iso.slots.clause_slot_schema``) are
    never independently analysed, so they never appear in ``results`` before this function
    runs — without their id also being supplied via ``known_clause_ids``, they would
    silently never be recognised as a parent at all, and the whole aggregation step would
    have nothing to attach their children's verdicts to.
    """
    decisions: dict[str, str] = {
        r["clause_id"]: r.get("decision", _UNKNOWN_DECISION)
        for r in results
        if r.get("clause_id")
    }
    parent_candidates = known_clause_ids if known_clause_ids is not None else set(decisions)

    # Only ids that actually exist as a clause can be parents — "7" is not a clause.
    children_by_parent: dict[str, list[str]] = {}
    for cid in decisions:
        parent = parent_of(cid)
        if parent and parent in parent_candidates:
            children_by_parent.setdefault(parent, []).append(cid)

    changed: dict[str, str] = {}
    # Deepest first so an aggregated child feeds into its own parent.
    for parent in sorted(
        children_by_parent,
        key=lambda cid: (-_depth(cid), clause_sort_key(cid)),
    ):
        child_decisions = {
            changed.get(c, decisions[c]) for c in children_by_parent[parent]
        }
        normalised = {d if d in _PRIORITY else _UNKNOWN_DECISION for d in child_decisions}
        derived = next(d for d in _PRIORITY if d in normalised)
        # A title-only parent has no prior decision to compare against (it was never
        # independently analysed) — treat that as "unknown", so its first-ever derived
        # decision always counts as a change and actually gets written.
        previous = decisions.get(parent, _UNKNOWN_DECISION)
        if derived != previous:
            changed[parent] = derived

    return changed


class ChildClauseSlots(BaseModel):
    """One child's real slot detail, carried into a title-only parent's summary verbatim."""

    clause_id: str
    title: str = ""
    decision: str = "Unknown"
    slot_schema: list[dict[str, Any]] = []
    slot_fills: list[dict[str, Any]] = []


class ChildrenSummary(BaseModel):
    """A title-only parent's display detail — pooled coverage over its children's real
    slots, never a schema of the parent's own. This is what ``children_summary`` on a
    persisted result holds; decision derivation stays worst-child-wins
    (``aggregate_parent_decisions``) — coverage here is display-only, computed
    independently for transparency, not fed back into the decision.
    """

    coverage: float
    applicable_required: int
    credit_awarded: float
    weight_total: float
    children: list[ChildClauseSlots] = []


def aggregate_children_slots(
    clause_id: str,
    results: list[dict[str, Any]],
    clause_titles: dict[str, str] | None = None,
) -> ChildrenSummary | None:
    """Pool a title-only parent's children's real slot fills into one coverage view.

    Returns ``None`` when ``clause_id`` has no children present in ``results`` — the parent
    then keeps whatever `slot_fills`/`slot_schema` it already has (empty, for a title-only
    clause; unchanged, for an ordinary leaf clause this is never called on).

    Coverage is pooled with the exact same arithmetic ``score_clause`` uses for a single
    clause (``build_slot_credit_rows`` / ``pool_coverage``, both shared, not reimplemented
    here) — just summed across every child's applicable required slots instead of one
    clause's own.
    """
    children = sorted(
        (r for r in results if r.get("clause_id") and parent_of(r["clause_id"]) == clause_id),
        key=lambda r: clause_sort_key(r["clause_id"]),
    )
    if not children:
        return None

    titles = clause_titles or {}
    pooled: list[Any] = []
    child_views: list[ChildClauseSlots] = []
    for child in children:
        cid = child["clause_id"]
        schema = child.get("slot_schema") or []
        fills = child.get("slot_fills") or []
        rows = build_slot_credit_rows(schema, fills) if schema else []
        pooled.extend(r for r in rows if r.required and r.state != "not_applicable")
        child_views.append(
            ChildClauseSlots(
                clause_id=cid,
                title=titles.get(cid, ""),
                decision=child.get("decision", "Unknown"),
                slot_schema=schema,
                slot_fills=fills,
            )
        )

    weight_total, credit_awarded, coverage = pool_coverage(pooled)
    return ChildrenSummary(
        coverage=round(coverage, 4),
        applicable_required=len(pooled),
        credit_awarded=round(credit_awarded, 4),
        weight_total=round(weight_total, 4),
        children=child_views,
    )
