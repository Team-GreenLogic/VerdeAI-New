"""Unit tests for weighted coverage scoring and critical-slot gating.

Pure functions over dicts — no LLM, no DB. The shapes named in these tests come from real
benchmark clauses, so a regression here maps back to a specific gold label.
"""

from verdeai_shared.iso.slots import (
    MET_THRESHOLD,
    NOT_MET_THRESHOLD,
    score_clause,
)


def _slot(sid, required=True, critical=False, weight=1.0):
    return {
        "slot_id": sid,
        "label": sid.replace("_", " ").capitalize(),
        "question": f"Identify {sid}.",
        "value_type": "text",
        "required": required,
        "multiple": False,
        "critical": critical,
        "weight": weight,
        "fill_rule": {"filled": "f", "partially_filled": "p", "not_filled": "n"},
    }


def _fill(sid, state, contradicted=False):
    return {"slot_id": sid, "state": state, "value": "", "citation_ids": [], "contradicted": contradicted}


# ── Coverage arithmetic ───────────────────────────────────────────────────────

def test_all_filled_is_full_coverage_and_met():
    schema = [_slot("a"), _slot("b")]
    out = score_clause(schema, [_fill("a", "filled"), _fill("b", "filled")])
    assert out.coverage == 1.0
    assert out.decision == "Met"


def test_partial_earns_half_credit():
    """The continuity that a conjunctive rule throws away: a third of real answers are partial."""
    schema = [_slot("a"), _slot("b")]
    out = score_clause(schema, [_fill("a", "filled"), _fill("b", "partially_filled")])
    assert out.coverage == 0.75
    assert out.credit_awarded == 1.5
    assert out.decision == "Partially Met"


def test_missing_fill_counts_as_not_filled():
    """Silence about a requirement is not evidence it is satisfied."""
    schema = [_slot("a"), _slot("b")]
    out = score_clause(schema, [_fill("a", "filled")])
    assert out.coverage == 0.5
    assert out.applicable_required == 2


def test_weights_shift_coverage():
    schema = [_slot("core", weight=3.0), _slot("minor", weight=1.0)]
    out = score_clause(schema, [_fill("core", "filled"), _fill("minor", "not_filled")])
    assert out.coverage == 0.75
    assert out.weight_total == 4.0


# ── Band boundaries ───────────────────────────────────────────────────────────

def test_met_boundary_is_inclusive():
    """Exactly at the threshold is Met — 6.1.3 landed on 0.90 in a real run."""
    schema = [_slot(f"s{i}") for i in range(10)]
    fills = [_fill(f"s{i}", "filled") for i in range(8)] + [
        _fill("s8", "partially_filled"), _fill("s9", "partially_filled")
    ]
    out = score_clause(schema, fills)
    assert out.coverage == 0.9
    assert out.coverage >= MET_THRESHOLD
    assert out.decision == "Met"


def test_just_below_met_is_partial():
    schema = [_slot("a"), _slot("b"), _slot("c"), _slot("d")]
    fills = [_fill("a", "filled"), _fill("b", "filled"), _fill("c", "filled"), _fill("d", "partially_filled")]
    out = score_clause(schema, fills)
    assert out.coverage == 0.875
    assert out.decision == "Met"  # 0.875 >= 0.85


def test_low_coverage_floor_is_not_met():
    schema = [_slot("a"), _slot("b"), _slot("c"), _slot("d")]
    out = score_clause(schema, [_fill(s, "not_filled") for s in "abcd"])
    assert out.coverage == 0.0
    assert out.coverage < NOT_MET_THRESHOLD
    assert out.decision == "Not Met"
    assert out.band_applied.startswith("coverage <")


# ── Critical-slot gating — the primary Not Met mechanism ──────────────────────

def test_contradicted_critical_slot_fails_a_high_coverage_clause():
    """The 6.1.2 shape: gold Not Met at coverage 0.79.

    Five of six required slots satisfied, but the one carrying the clause's core determination
    is contradicted by an audit nonconformity. Averaging buries this; the gate must not.
    """
    schema = [
        _slot("aspects_and_impacts"),
        _slot("life_cycle_perspective"),
        _slot("change_taken_into_account", critical=True),
        _slot("significance_criteria"),
        _slot("significant_aspects"),
        _slot("documented_information"),
    ]
    fills = [
        _fill("aspects_and_impacts", "filled"),
        _fill("life_cycle_perspective", "filled"),
        _fill("change_taken_into_account", "partially_filled", contradicted=True),
        _fill("significance_criteria", "filled"),
        _fill("significant_aspects", "filled"),
        _fill("documented_information", "filled"),
    ]
    out = score_clause(schema, fills)
    assert out.coverage > MET_THRESHOLD, "precondition: coverage alone would say Met"
    assert out.decision == "Not Met"
    assert out.critical_failures == ["change_taken_into_account"]
    assert out.band_applied == "critical-slot-contradicted"


def test_uncontradicted_critical_slot_does_not_force_not_met():
    """The 7.4.2 shape: gold Partially Met.

    A required slot is unfilled, but the gold reason reads "limited evidence that…" — absence
    of proof, not proof of absence. The benchmark reserves Not Met for affirmative failure.
    """
    schema = [_slot("internal_communication"), _slot("contribution_enabled", critical=True)]
    fills = [_fill("internal_communication", "partially_filled"), _fill("contribution_enabled", "not_filled")]
    out = score_clause(schema, fills)
    assert out.decision == "Partially Met"
    assert out.critical_failures == []


def test_critical_slot_filled_is_never_a_failure():
    schema = [_slot("a", critical=True), _slot("b")]
    out = score_clause(schema, [_fill("a", "filled", contradicted=True), _fill("b", "filled")])
    assert out.critical_failures == []
    assert out.decision == "Met"


def test_contradicted_non_critical_slot_does_not_gate():
    """Only the core determination gates. A contradicted supporting slot lowers coverage only."""
    schema = [_slot("core", critical=True), _slot("documented_information")]
    out = score_clause(schema, [_fill("core", "filled"), _fill("documented_information", "not_filled", contradicted=True)])
    assert out.critical_failures == []
    assert out.decision == "Partially Met"


# ── Applicability ─────────────────────────────────────────────────────────────

def test_not_applicable_excluded_from_denominator():
    schema = [_slot("a"), _slot("b"), _slot("c")]
    out = score_clause(schema, [_fill("a", "filled"), _fill("b", "filled"), _fill("c", "not_applicable")])
    assert out.applicable_required == 2
    assert out.coverage == 1.0
    assert out.decision == "Met"


def test_optional_slots_never_reduce_coverage():
    """A "shall consider" obligation the standard qualifies must not drag the clause down."""
    schema = [_slot("a"), _slot("opt", required=False)]
    out = score_clause(schema, [_fill("a", "filled"), _fill("opt", "not_filled")])
    assert out.applicable_required == 1
    assert out.coverage == 1.0
    assert out.decision == "Met"


def test_critical_but_not_applicable_does_not_gate():
    schema = [_slot("a"), _slot("cond", critical=True)]
    out = score_clause(schema, [_fill("a", "filled"), _fill("cond", "not_applicable", contradicted=True)])
    assert out.critical_failures == []
    assert out.decision == "Met"


def test_empty_schema_does_not_fail_the_clause():
    """A clause with no slots at all must not read as a failure."""
    out = score_clause([], [])
    assert out.applicable_required == 0
    assert out.decision == "Partially Met"
    assert out.band_applied == "no-applicable-required-slots"


# ── The trace itself ──────────────────────────────────────────────────────────

def test_per_slot_trace_reproduces_the_coverage():
    schema = [_slot("a", weight=2.0), _slot("b"), _slot("opt", required=False)]
    out = score_clause(schema, [_fill("a", "partially_filled"), _fill("b", "filled"), _fill("opt", "filled")])
    applicable = [r for r in out.per_slot if r.required and r.state != "not_applicable"]
    recomputed = sum(r.weight * r.credit for r in applicable) / sum(r.weight for r in applicable)
    # coverage is rounded to 4dp for storage, so compare at that precision.
    assert abs(recomputed - out.coverage) < 1e-4
    assert len(out.per_slot) == 3, "every slot appears in the trace, including optional ones"
