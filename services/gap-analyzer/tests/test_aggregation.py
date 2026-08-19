"""Unit tests for deterministic parent-clause aggregation.

Pure functions over dicts — no LLM, no DB.
"""

from app.pipeline.aggregation import aggregate_children_slots, aggregate_parent_decisions, parent_of


def _r(clause_id: str, decision: str) -> dict:
    return {"clause_id": clause_id, "decision": decision}


def _slot(slot_id: str, *, required: bool = True, critical: bool = False, weight: float = 1.0) -> dict:
    return {
        "slot_id": slot_id,
        "label": slot_id,
        "question": f"Identify the {slot_id}.",
        "value_type": "text",
        "required": required,
        "critical": critical,
        "weight": weight,
        "fill_rule": {"filled": "x", "partially_filled": "y", "not_filled": "z"},
    }


def _fill(slot_id: str, state: str, *, contradicted: bool = False) -> dict:
    return {"slot_id": slot_id, "state": state, "contradicted": contradicted}


def _child(clause_id: str, decision: str, schema: list, fills: list) -> dict:
    return {"clause_id": clause_id, "decision": decision, "slot_schema": schema, "slot_fills": fills}


def test_parent_of():
    assert parent_of("7.4.3") == "7.4"
    assert parent_of("7.4") == "7"
    assert parent_of("7") is None
    assert parent_of("") is None


def test_not_met_child_fails_parent():
    """The 7.4 case: gold 7.4.3 = Not Met implies gold 7.4 = Not Met."""
    results = [
        _r("7.4", "Partially Met"),
        _r("7.4.1", "Met"),
        _r("7.4.2", "Partially Met"),
        _r("7.4.3", "Not Met"),
    ]
    assert aggregate_parent_decisions(results) == {"7.4": "Not Met"}


def test_insufficient_beats_partial_and_met():
    results = [
        _r("9.1", "Met"),
        _r("9.1.1", "Partially Met"),
        _r("9.1.2", "Insufficient Evidence"),
    ]
    assert aggregate_parent_decisions(results) == {"9.1": "Insufficient Evidence"}


def test_partial_child_downgrades_met_parent():
    results = [
        _r("6.2", "Met"),
        _r("6.2.1", "Met"),
        _r("6.2.2", "Partially Met"),
    ]
    assert aggregate_parent_decisions(results) == {"6.2": "Partially Met"}


def test_all_children_met_upgrades_parent():
    results = [
        _r("7.5", "Partially Met"),
        _r("7.5.1", "Met"),
        _r("7.5.2", "Met"),
        _r("7.5.3", "Met"),
    ]
    assert aggregate_parent_decisions(results) == {"7.5": "Met"}


def test_no_change_returns_empty():
    results = [
        _r("7.4", "Not Met"),
        _r("7.4.1", "Not Met"),
    ]
    assert aggregate_parent_decisions(results) == {}


def test_clause_without_children_is_untouched():
    results = [_r("5.2", "Met"), _r("10.3", "Met")]
    assert aggregate_parent_decisions(results) == {}


def test_unknown_decision_treated_as_insufficient_not_met():
    """An "Error" child must never let a parent read as Met."""
    results = [
        _r("6.1", "Met"),
        _r("6.1.1", "Met"),
        _r("6.1.2", "Error"),
    ]
    assert aggregate_parent_decisions(results) == {"6.1": "Insufficient Evidence"}


def test_deepest_first_composition():
    """An aggregated child must feed its own parent: 7.5.3 fails 7.5, which fails 7
    when 7 is itself an analysed clause."""
    results = [
        _r("7", "Met"),
        _r("7.5", "Met"),
        _r("7.5.3", "Not Met"),
    ]
    assert aggregate_parent_decisions(results) == {"7.5": "Not Met", "7": "Not Met"}


def test_parent_not_analysed_is_skipped():
    """ISO has no clause "7.9" — a child whose parent was never analysed is ignored."""
    results = [_r("7.9.1", "Not Met")]
    assert aggregate_parent_decisions(results) == {}


# ── Title-only parents (known_clause_ids) ───────────────────────────────────────────────
#
# A title-only ISO heading (6.1, 6.2, 7.4, 7.5, 9.1, 9.2) is never independently analysed,
# so unlike every case above it has NO row of its own in `results` — the actor's per-clause
# loop skips it entirely (see actors.py). Without `known_clause_ids`, aggregation has no way
# to tell "6.2" apart from a non-clause string prefix like "7", and would silently never
# recognise it as a parent at all.

def test_title_only_parent_absent_from_results_needs_known_clause_ids():
    """Regression test for the exact bug this caused: a parent with no row of its own was
    silently skipped until `known_clause_ids` was threaded through."""
    results = [_r("6.2.1", "Met"), _r("6.2.2", "Partially Met")]
    assert aggregate_parent_decisions(results) == {}, (
        "without known_clause_ids, a parent absent from results must not be recognised"
    )
    assert aggregate_parent_decisions(results, known_clause_ids={"6.2", "6.2.1", "6.2.2"}) == {
        "6.2": "Partially Met"
    }


def test_title_only_parent_first_aggregation_always_counts_as_a_change():
    """A title-only parent has no prior decision to compare against — its very first
    derived decision must still be emitted, not treated as a no-op."""
    results = [_r("9.1.1", "Not Met")]
    assert aggregate_parent_decisions(results, known_clause_ids={"9.1", "9.1.1"}) == {
        "9.1": "Not Met"
    }


def test_known_clause_ids_does_not_change_ordinary_behaviour():
    """When every parent already has its own row (the pre-title-only shape every existing
    test above uses), passing known_clause_ids must be a no-op."""
    results = [_r("7.4", "Partially Met"), _r("7.4.1", "Met"), _r("7.4.3", "Not Met")]
    known = {"7.4", "7.4.1", "7.4.3"}
    assert aggregate_parent_decisions(results, known_clause_ids=known) == \
        aggregate_parent_decisions(results) == {"7.4": "Not Met"}


# ── aggregate_children_slots ────────────────────────────────────────────────────────────

def test_pools_coverage_across_two_children():
    schema_a = [_slot("a1"), _slot("a2")]
    schema_b = [_slot("b1")]
    results = [
        _child("6.2.1", "Met", schema_a, [_fill("a1", "filled"), _fill("a2", "filled")]),
        _child("6.2.2", "Partially Met", schema_b, [_fill("b1", "partially_filled")]),
    ]
    summary = aggregate_children_slots("6.2", results)
    assert summary is not None
    assert summary.applicable_required == 3
    assert summary.weight_total == 3.0
    assert summary.credit_awarded == 2.5  # 1.0 + 1.0 + 0.5
    assert round(summary.coverage, 4) == round(2.5 / 3.0, 4)
    assert [c.clause_id for c in summary.children] == ["6.2.1", "6.2.2"]


def test_excludes_not_applicable_and_optional_slots():
    schema = [_slot("req"), _slot("opt", required=False)]
    fills = [_fill("req", "filled"), _fill("opt", "not_filled")]
    results = [_child("7.4.1", "Met", schema, fills)]
    summary = aggregate_children_slots("7.4", results)
    assert summary.applicable_required == 1
    assert summary.coverage == 1.0

    schema_na = [_slot("na")]
    results_na = [_child("7.4.1", "Met", schema_na, [_fill("na", "not_applicable")])]
    summary_na = aggregate_children_slots("7.4", results_na)
    assert summary_na.applicable_required == 0
    assert summary_na.weight_total == 0.0


def test_matches_score_clause_credit_weights_exactly():
    """A values test: filled=1.0, partially_filled=0.5, not_filled=0.0, matching
    verdeai_shared.iso.slots._STATE_CREDIT — the two must never diverge."""
    schema = [_slot("s1"), _slot("s2"), _slot("s3")]
    fills = [_fill("s1", "filled"), _fill("s2", "partially_filled"), _fill("s3", "not_filled")]
    summary = aggregate_children_slots("9.2", [_child("9.2.1", "Partially Met", schema, fills)])
    assert summary.credit_awarded == 1.5  # 1.0 + 0.5 + 0.0
    assert summary.weight_total == 3.0


def test_returns_none_when_no_children_present():
    results = [_r("5.2", "Met"), _r("10.3", "Met")]
    assert aggregate_children_slots("6.2", results) is None


def test_carries_titles_and_child_decisions():
    schema = [_slot("s1")]
    results = [_child("9.1.1", "Not Met", schema, [_fill("s1", "not_filled")])]
    summary = aggregate_children_slots("9.1", results, clause_titles={"9.1.1": "General"})
    assert summary.children[0].title == "General"
    assert summary.children[0].decision == "Not Met"
