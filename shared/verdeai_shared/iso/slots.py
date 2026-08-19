"""Slot-filling ISO requirement schemas — what information a clause demands.

A clause's ``slot_schema`` is a company-blind description of the information ISO
requires for that clause to be fulfilled. It names no document, filename, evidence
source or system of record: it is generated once per ISO version (see
``services/iso-knowledge/app/generate_slot_schemas.py``) and is valid for every tenant.

This exists because compliance adjudication used to be a single LLM judgement ("does
this company comply with clause X?"), and the part of that judgement which is a property
of the *standard* rather than of the evidence — whether a given obligation is mandatory —
was being re-derived by the model on every run, non-deterministically. Here that property
is ``Slot.required``, fixed in data. At analysis time the pipeline answers a fixed list of
precise extraction questions, records a state per slot, and derives the clause result
arithmetically from slot completeness.

Relationship to ``requirements.py``: a slot is a strict superset of a ``SubRequirement``
— ``slot_id`` plays the role of ``id``, and ``question`` is a far more specific form of
``text``. Clauses with no ``slot_schema`` yet get one synthesized from their
``requirements_list`` by :func:`clause_slot_schema`, so the pipeline keeps a single code
path and un-migrated ISO versions behave exactly as they did before.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from verdeai_shared.iso.requirements import clause_requirements_list

SlotValueType = Literal[
    "text",
    "person_or_role",
    "date_or_period",
    "quantity",
    "document_reference",
    "process_description",
    "criteria",
    "list_of_items",
    "boolean",
]
SlotState = Literal["filled", "partially_filled", "not_filled", "not_applicable"]

_SLOT_STATES = ("filled", "partially_filled", "not_filled", "not_applicable")

# Decision strings shared with app.pipeline.schemas.Decision. "Insufficient Evidence" is
# deliberately absent — evidence sufficiency is settled upstream by the retrieval gate
# (_route_after_grade) before any slot is filled, so slot states never produce it.
_STATE_TO_DECISION: dict[str, str] = {
    "filled": "Met",
    "partially_filled": "Partially Met",
    "not_filled": "Not Met",
}

_STATE_TO_FINDING_STATUS: dict[str, str] = {
    "filled": "satisfied",
    "partially_filled": "partial",
    "not_filled": "unmet",
}


class FillRule(BaseModel):
    """The three discriminating conditions that decide a slot's state.

    Written in terms of the information itself, never in terms of compliance — the fill
    step applies these rules without knowing what verdict they will produce.
    """

    filled: str
    partially_filled: str
    not_filled: str


class Slot(BaseModel):
    """One required piece of information, with the question that extracts it."""

    slot_id: str
    label: str
    question: str
    value_type: SlotValueType = "text"
    required: bool = True
    multiple: bool = False
    fill_rule: FillRule
    # How much of the clause this slot accounts for. Defaults to equal weighting; raise it for
    # a slot that carries more of the requirement than its siblings.
    weight: float = 1.0
    # Carries the clause's core determination — the thing the clause exists to require, as
    # opposed to its supporting documentation or its "shall consider" attachments. A critical
    # slot that evidence *contradicts* fails the clause outright regardless of coverage; see
    # score_clause. Averaging cannot express this: benchmark clause 6.1.2 is gold Not Met at
    # coverage 0.79, because one core determination failed while five siblings were satisfied.
    critical: bool = False


class ClauseSlotSchema(BaseModel):
    """Container so LLM schema generation can use structured (validated) output."""

    slots: list[Slot]


class SlotFill(BaseModel):
    """What the evidence had to say about one slot."""

    slot_id: str
    state: SlotState
    value: str = ""
    citation_ids: list[int] = []
    notes: str = ""
    # True only when the evidence *positively establishes* that the requirement is not carried
    # out — an audit nonconformity, a regulator finding, a register recorded as empty. Absence
    # of evidence is never contradiction: silence is uncertainty, not failure. This is the
    # distinction the benchmark's adjudication guide draws for NOT_MET, which it states is
    # "not used merely because a document is absent".
    contradicted: bool = False


class SlotFillResult(BaseModel):
    """Container so the fill step can use structured (validated) output."""

    slot_fills: list[SlotFill]


_GENERIC_FILL_RULE = FillRule(
    filled=(
        "The evidence states this requirement is carried out, with enough specificity to "
        "identify what is done and by whom."
    ),
    partially_filled=(
        "The evidence touches on this requirement but is vague, incomplete, or cannot be "
        "pinned to a specific practice."
    ),
    not_filled="The evidence says nothing that addresses this requirement.",
)


def _synthesize_slots(clause: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a minimal slot schema from a clause's sub-requirement decomposition.

    Lower quality than a generated schema — the question is only the requirement text and
    every slot is mandatory, because the decomposition carries no materiality — but it
    means an un-migrated clause behaves as it did before slots existed.
    """
    return [
        Slot(
            slot_id=r["id"],
            label=r["text"][:80],
            question=r["text"],
            value_type="text",
            required=True,
            multiple=False,
            fill_rule=_GENERIC_FILL_RULE,
        ).model_dump()
        for r in clause_requirements_list(clause)
    ]


def clause_slot_schema(clause: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the best available slot schema for a clause doc.

    Prefers a persisted, generated ``slot_schema``; falls back to synthesizing one from
    ``requirements_list`` (itself falling back to a naive sentence split). A malformed
    stored slot is dropped rather than failing the analysis; if nothing survives, the
    clause falls through to synthesis.

    ``title_only`` clauses (e.g. ISO 14001's 6.2 "Environmental objectives and planning to
    achieve them", which carries no normative text of its own — the "shall" statements start
    only at 6.2.1) always return ``[]`` here, ahead of the synthesis fallback. Without this
    check, a title-only clause's ``requirements`` text — which is essentially its children's
    prose concatenated under the parent heading — got naively sentence-split into a
    fabricated, all-required schema, and the clause was independently analysed against
    requirements that were never its own. Its result comes entirely from aggregating its
    children instead; see ``aggregation.aggregate_children_slots``.
    """
    if clause.get("title_only"):
        return []
    stored = clause.get("slot_schema")
    if isinstance(stored, list) and stored:
        slots: list[dict[str, Any]] = []
        for raw in stored:
            if not isinstance(raw, dict):
                continue
            try:
                slots.append(Slot.model_validate(raw).model_dump())
            except Exception:  # one bad slot must not fail the clause
                continue
        if slots:
            return slots
    return _synthesize_slots(clause)


def _fills_by_id(fills: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(f.get("slot_id", "")): f for f in fills if isinstance(f, dict)}


def _fill_states(
    schema: list[dict[str, Any]], fills: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], str]]:
    """Pair each schema slot with its reported state.

    A slot the fill step failed to report counts as ``not_filled`` — silence about a
    requirement is not evidence that it is satisfied. Fills naming a slot_id absent from
    the schema are ignored.
    """
    by_id = _fills_by_id(fills)
    out: list[tuple[dict[str, Any], str]] = []
    for slot in schema:
        fill = by_id.get(str(slot.get("slot_id", "")))
        state = str(fill.get("state", "not_filled")) if fill else "not_filled"
        if state not in _SLOT_STATES:
            state = "not_filled"
        out.append((slot, state))
    return out


class SlotCredit(BaseModel):
    """One slot's contribution to its clause's coverage — a row of the decision trace."""

    slot_id: str
    label: str = ""
    state: SlotState
    required: bool
    critical: bool
    contradicted: bool
    weight: float
    credit: float


class ClauseScore(BaseModel):
    """The full derivation of a clause decision. This *is* the explanation.

    Persisted on the result as ``decision_trace`` so the verdict can be re-checked against the
    arithmetic that produced it, rather than against prose the model wrote alongside it.
    """

    decision: str
    coverage: float
    applicable_required: int
    credit_awarded: float
    weight_total: float
    critical_failures: list[str] = []
    band_applied: str
    per_slot: list[SlotCredit] = []


# Credit each state contributes toward coverage. "partially_filled" earning half is what makes
# the score continuous — 33.7% of real slot answers are partial, and a conjunctive rule throws
# all of that information away.
_STATE_CREDIT: dict[str, float] = {"filled": 1.0, "partially_filled": 0.5, "not_filled": 0.0}

# Band boundaries. Fitted on company A of the five-company benchmark (the development set);
# companies B-E are held out. A sweep showed 0.85 optimal for the upper band, and that raising
# the lower band above ~0.25 *costs* accuracy by inventing Not Met where the gold says
# Partially Met — because Not Met is a critical-slot phenomenon, not a low-coverage one.
MET_THRESHOLD = 0.85
NOT_MET_THRESHOLD = 0.15


def build_slot_credit_rows(
    schema: list[dict[str, Any]], fills: list[dict[str, Any]]
) -> list[SlotCredit]:
    """Pair a clause's slot schema with its fills, one ``SlotCredit`` row per slot.

    Shared by ``score_clause`` (a single clause's own slots) and
    ``aggregation.aggregate_children_slots`` (pooling several children's slots for a
    title-only parent) — extracted so the two can never compute credit differently.
    """
    by_id = _fills_by_id(fills)
    rows: list[SlotCredit] = []
    for slot, state in _fill_states(schema, fills):
        fill = by_id.get(str(slot.get("slot_id", "")), {})
        rows.append(
            SlotCredit(
                slot_id=str(slot.get("slot_id", "")),
                label=str(slot.get("label", "")),
                state=state,  # type: ignore[arg-type]
                required=bool(slot.get("required", True)),
                critical=bool(slot.get("critical", False)),
                contradicted=bool(fill.get("contradicted", False)),
                weight=float(slot.get("weight", 1.0) or 1.0),
                credit=_STATE_CREDIT.get(state, 0.0),
            )
        )
    return rows


def pool_coverage(applicable: list[SlotCredit]) -> tuple[float, float, float]:
    """Weighted coverage over already-filtered (required, applicable) rows.

    Returns ``(weight_total, credit_awarded, coverage)``. Pure arithmetic, shared by
    ``score_clause`` and ``aggregate_children_slots`` for the same reason as
    ``build_slot_credit_rows`` above.
    """
    weight_total = sum(r.weight for r in applicable)
    credit_awarded = sum(r.weight * r.credit for r in applicable)
    coverage = credit_awarded / weight_total if weight_total else 0.0
    return weight_total, credit_awarded, coverage


def score_clause(schema: list[dict[str, Any]], fills: list[dict[str, Any]]) -> ClauseScore:
    """Derive a clause decision from weighted slot coverage plus critical-slot gating.

    Order:

    1. A ``critical`` slot that evidence **contradicts** -> ``Not Met``. This is the primary
       Not Met mechanism. Averaging cannot express it: a single core determination failing
       among satisfied siblings still fails the clause.
    2. coverage >= ``MET_THRESHOLD`` -> ``Met``
    3. coverage >= ``NOT_MET_THRESHOLD`` -> ``Partially Met``
    4. otherwise -> ``Not Met``

    Coverage runs over *applicable required* slots only (``required`` and not
    ``not_applicable``), so a conditional obligation the standard qualifies with "as
    appropriate" cannot drag a clause down.
    """
    rows = build_slot_credit_rows(schema, fills)
    applicable = [r for r in rows if r.required and r.state != "not_applicable"]

    # Step 1 — a contradicted critical slot fails the clause outright. "not_filled" alone is
    # not enough: the benchmark reserves Not Met for affirmative evidence of failure, so a
    # requirement nobody documented either way stays Partially Met / Insufficient Evidence.
    critical_failures = [
        r.slot_id
        for r in applicable
        if r.critical and r.contradicted and r.state in ("not_filled", "partially_filled")
    ]

    if not applicable:
        # No required slots apply. Fall back to the optional ones so a clause made entirely of
        # conditional obligations is not scored as a failure for having none of them triggered.
        optional = [r for r in rows if not r.required]
        got = any(r.state == "filled" for r in optional)
        return ClauseScore(
            decision="Met" if got else "Partially Met",
            coverage=1.0 if got else 0.0,
            applicable_required=0,
            credit_awarded=0.0,
            weight_total=0.0,
            critical_failures=[],
            band_applied="no-applicable-required-slots",
            per_slot=rows,
        )

    weight_total, credit_awarded, coverage = pool_coverage(applicable)

    if critical_failures:
        decision, band = "Not Met", "critical-slot-contradicted"
    elif coverage >= MET_THRESHOLD:
        decision, band = "Met", f"coverage >= {MET_THRESHOLD}"
    elif coverage >= NOT_MET_THRESHOLD:
        decision, band = "Partially Met", f"{NOT_MET_THRESHOLD} <= coverage < {MET_THRESHOLD}"
    else:
        decision, band = "Not Met", f"coverage < {NOT_MET_THRESHOLD}"

    return ClauseScore(
        decision=decision,
        coverage=round(coverage, 4),
        applicable_required=len(applicable),
        credit_awarded=round(credit_awarded, 4),
        weight_total=round(weight_total, 4),
        critical_failures=critical_failures,
        band_applied=band,
        per_slot=rows,
    )


def derive_clause_state(schema: list[dict[str, Any]], fills: list[dict[str, Any]]) -> str:
    """Clause-level *state* (not decision), kept as the inverse mapping of :func:`score_clause`.

    Retained because callers and tests predating the scoring model speak in slot-state terms.
    """
    decision = score_clause(schema, fills).decision
    for state, mapped in _STATE_TO_DECISION.items():
        if mapped == decision:
            return state
    return "partially_filled"


def slot_state_to_decision(state: str) -> str:
    return _STATE_TO_DECISION.get(state, "Partially Met")


def slot_fills_to_findings(
    schema: list[dict[str, Any]], fills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Project slot fills onto the ``SubRequirementFinding`` shape the rest of the stack reads.

    ``material`` comes from the slot's ``required`` flag rather than from an LLM judgement
    — the whole point of the schema. ``not_applicable`` slots emit no finding at all, so
    they neither defeat an all-satisfied clause nor read as a failure.
    """
    by_id = _fills_by_id(fills)
    findings: list[dict[str, Any]] = []
    for slot, state in _fill_states(schema, fills):
        if state == "not_applicable":
            continue
        fill = by_id.get(str(slot.get("slot_id", "")), {})
        findings.append(
            {
                "req_id": str(slot.get("slot_id", "")),
                "status": _STATE_TO_FINDING_STATUS[state],
                "citation_ids": [
                    int(c) for c in fill.get("citation_ids", []) if isinstance(c, int)
                ],
                "notes": str(fill.get("notes", "")),
                "material": bool(slot.get("required", True)) and state == "not_filled",
            }
        )
    return findings
