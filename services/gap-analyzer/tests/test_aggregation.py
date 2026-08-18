"""Unit tests for deterministic parent-clause aggregation.

Pure functions over dicts — no LLM, no DB.
"""

from app.pipeline.aggregation import aggregate_parent_decisions, parent_of


def _r(clause_id: str, decision: str) -> dict:
    return {"clause_id": clause_id, "decision": decision}


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
