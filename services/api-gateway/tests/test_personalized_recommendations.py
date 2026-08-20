"""Personalized recommendation API helper contracts."""

from app.routers.personalized_recommendations import _recommendation_key


def test_recommendation_key_is_stable_and_clause_scoped() -> None:
    first = _recommendation_key({"clause_id": "8.1", "text": "  Add a spill plan  "})
    second = _recommendation_key({"clause_id": "8.1", "text": "add a spill plan"})
    other_clause = _recommendation_key({"clause_id": "6.1", "text": "add a spill plan"})

    assert first == second
    assert first != other_clause
    assert first.startswith("8.1:")
