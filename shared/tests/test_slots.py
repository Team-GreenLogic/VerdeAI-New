"""Unit tests for slot-filling schemas and the clause-state derivation.

Pure functions over dicts — no LLM, no DB. These encode the decision rule that replaced
the analyser's own judgement, so a change here changes every clause verdict.
"""

from verdeai_shared.iso.slots import (
    clause_slot_schema,
    derive_clause_state,
    slot_fills_to_findings,
    slot_state_to_decision,
)


def _slot(slot_id: str, *, required: bool = True) -> dict:
    return {
        "slot_id": slot_id,
        "label": slot_id,
        "question": f"Identify the {slot_id}.",
        "value_type": "text",
        "required": required,
        "multiple": False,
        "fill_rule": {"filled": "f", "partially_filled": "p", "not_filled": "n"},
    }


def _fill(slot_id: str, state: str) -> dict:
    return {"slot_id": slot_id, "state": state, "value": "", "citation_ids": [], "notes": ""}


# ── derive_clause_state ───────────────────────────────────────────────────────

def test_all_required_filled_is_filled():
    schema = [_slot("a"), _slot("b")]
    fills = [_fill("a", "filled"), _fill("b", "filled")]
    assert derive_clause_state(schema, fills) == "filled"


def test_no_required_information_is_not_filled():
    schema = [_slot("a"), _slot("b")]
    fills = [_fill("a", "not_filled"), _fill("b", "not_filled")]
    assert derive_clause_state(schema, fills) == "not_filled"


def test_mixed_is_partially_filled():
    schema = [_slot("a"), _slot("b")]
    fills = [_fill("a", "filled"), _fill("b", "not_filled")]
    assert derive_clause_state(schema, fills) == "partially_filled"


def test_partial_alone_is_partially_filled():
    """A single vague answer is still information — it is not "no meaningful required
    information", which is what not_filled means."""
    schema = [_slot("a")]
    assert derive_clause_state(schema, [_fill("a", "partially_filled")]) == "partially_filled"


def test_not_applicable_leaves_the_denominator():
    """A slot ISO does not apply to this organisation must not drag the clause down."""
    schema = [_slot("a"), _slot("b")]
    fills = [_fill("a", "filled"), _fill("b", "not_applicable")]
    assert derive_clause_state(schema, fills) == "filled"


def test_optional_slots_never_decide_a_clause_with_required_ones():
    schema = [_slot("a"), _slot("opt", required=False)]
    fills = [_fill("a", "filled"), _fill("opt", "not_filled")]
    assert derive_clause_state(schema, fills) == "filled"


def test_optional_only_clause_falls_back_to_optional_slots():
    """A clause with no applicable required slots is judged on its optional ones.

    When none of them carries information the answer is deliberately NOT "not_filled": every
    obligation in the clause is one the standard itself conditions, and nothing established
    that any of them was triggered. Asserting failure there would be an affirmative claim of
    nonconformity the evidence does not support — the most damaging error an audit tool can
    make. It degrades to "partially_filled" instead.
    """
    schema = [_slot("opt1", required=False), _slot("opt2", required=False)]
    assert derive_clause_state(schema, [_fill("opt1", "filled"), _fill("opt2", "not_filled")]) == "filled"
    assert (
        derive_clause_state(schema, [_fill("opt1", "not_filled"), _fill("opt2", "not_filled")])
        == "partially_filled"
    )


def test_all_required_not_applicable_falls_back_to_optional():
    schema = [_slot("a"), _slot("opt", required=False)]
    fills = [_fill("a", "not_applicable"), _fill("opt", "filled")]
    assert derive_clause_state(schema, fills) == "filled"


def test_slot_missing_from_fills_counts_as_not_filled():
    """Silence about a requirement is not evidence it is satisfied — the fill step
    skipping a slot must never read as compliance."""
    schema = [_slot("a"), _slot("b")]
    assert derive_clause_state(schema, [_fill("a", "filled")]) == "partially_filled"


def test_empty_fills_is_not_filled():
    assert derive_clause_state([_slot("a"), _slot("b")], []) == "not_filled"


def test_unknown_state_is_treated_as_not_filled():
    schema = [_slot("a")]
    assert derive_clause_state(schema, [_fill("a", "probably_fine")]) == "not_filled"


def test_fill_for_unknown_slot_id_is_ignored():
    schema = [_slot("a")]
    fills = [_fill("a", "filled"), _fill("invented", "not_filled")]
    assert derive_clause_state(schema, fills) == "filled"


# ── slot_state_to_decision ────────────────────────────────────────────────────

def test_state_to_decision_mapping():
    assert slot_state_to_decision("filled") == "Met"
    assert slot_state_to_decision("partially_filled") == "Partially Met"
    assert slot_state_to_decision("not_filled") == "Not Met"


# ── slot_fills_to_findings ────────────────────────────────────────────────────

def test_findings_take_material_from_the_schema_not_the_model():
    """The whole point of the slot layer: materiality is a property of the standard,
    recorded in `required`, rather than something the LLM volunteers per run."""
    schema = [_slot("a"), _slot("opt", required=False)]
    fills = [_fill("a", "not_filled"), _fill("opt", "not_filled")]
    findings = {f["req_id"]: f for f in slot_fills_to_findings(schema, fills)}
    assert findings["a"]["material"] is True
    assert findings["opt"]["material"] is False


def test_material_is_only_set_on_unfilled_slots():
    schema = [_slot("a"), _slot("b")]
    fills = [_fill("a", "filled"), _fill("b", "partially_filled")]
    assert all(f["material"] is False for f in slot_fills_to_findings(schema, fills))


def test_finding_status_mapping():
    schema = [_slot("a"), _slot("b"), _slot("c")]
    fills = [_fill("a", "filled"), _fill("b", "partially_filled"), _fill("c", "not_filled")]
    statuses = {f["req_id"]: f["status"] for f in slot_fills_to_findings(schema, fills)}
    assert statuses == {"a": "satisfied", "b": "partial", "c": "unmet"}


def test_not_applicable_emits_no_finding():
    """Otherwise an inapplicable slot would defeat an all-satisfied clause."""
    schema = [_slot("a"), _slot("b")]
    fills = [_fill("a", "filled"), _fill("b", "not_applicable")]
    findings = slot_fills_to_findings(schema, fills)
    assert [f["req_id"] for f in findings] == ["a"]


def test_findings_carry_citations_and_notes():
    schema = [_slot("a")]
    fills = [{"slot_id": "a", "state": "filled", "value": "x", "citation_ids": [1, 3], "notes": "why"}]
    finding = slot_fills_to_findings(schema, fills)[0]
    assert finding["citation_ids"] == [1, 3]
    assert finding["notes"] == "why"


# ── clause_slot_schema ────────────────────────────────────────────────────────

def test_prefers_a_stored_slot_schema():
    clause = {"clause_id": "6.2.2", "requirements": "prose", "slot_schema": [_slot("responsible_party")]}
    schema = clause_slot_schema(clause)
    assert [s["slot_id"] for s in schema] == ["responsible_party"]


def test_synthesizes_from_requirements_list_when_no_schema():
    clause = {
        "clause_id": "6.1.2",
        "requirements": "ignored when requirements_list is present",
        "requirements_list": [{"id": "6.1.2-1", "text": "Determine environmental aspects."}],
    }
    schema = clause_slot_schema(clause)
    assert [s["slot_id"] for s in schema] == ["6.1.2-1"]
    assert schema[0]["question"] == "Determine environmental aspects."
    assert schema[0]["required"] is True


def test_synthesizes_from_bare_requirements_prose():
    clause = {
        "clause_id": "5.2",
        "requirements": "The organization shall establish a policy. The policy shall be documented.",
    }
    schema = clause_slot_schema(clause)
    assert [s["slot_id"] for s in schema] == ["5.2-1", "5.2-2"]


def test_malformed_stored_slots_are_dropped_not_fatal():
    clause = {
        "clause_id": "7.2",
        "requirements": "The organization shall determine competence.",
        "slot_schema": [_slot("good"), {"slot_id": "bad"}],  # second has no fill_rule
    }
    assert [s["slot_id"] for s in clause_slot_schema(clause)] == ["good"]


def test_entirely_unusable_stored_schema_falls_back_to_synthesis():
    clause = {
        "clause_id": "7.2",
        "requirements": "The organization shall determine competence.",
        "slot_schema": [{"nonsense": True}],
    }
    assert [s["slot_id"] for s in clause_slot_schema(clause)] == ["7.2-1"]


def test_title_only_clause_has_no_schema_even_with_requirements_text():
    """ISO 14001's 6.2 "Environmental objectives and planning to achieve them" is a
    heading with no normative text of its own — the "shall" text starts only at 6.2.1.
    Its `requirements` field is essentially its children's prose concatenated under the
    parent heading, so without this check it would get a fabricated schema via naive
    sentence-split synthesis, indistinguishable from a real, independently-analysable
    clause. `title_only` must short-circuit before synthesis is ever attempted."""
    clause = {
        "clause_id": "6.2",
        "title_only": True,
        "requirements": "The organization shall establish environmental objectives... "
        "the organization shall determine what will be done...",
        "requirements_list": [{"id": "6.2-1", "text": "This should never be reached."}],
    }
    assert clause_slot_schema(clause) == []


def test_title_only_false_or_absent_synthesizes_normally():
    # Explicit False and simply-absent must behave identically — only a truthy flag
    # short-circuits.
    base = {"clause_id": "5.2", "requirements": "The organization shall establish a policy."}
    assert clause_slot_schema({**base, "title_only": False}) != []
    assert clause_slot_schema(base) != []
