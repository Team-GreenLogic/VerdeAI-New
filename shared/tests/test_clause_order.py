"""Tests for canonical ISO clause ordering."""

from verdeai_shared.iso.clause_order import clause_sort_key


def test_numeric_clause_order() -> None:
    clause_ids = ["10.2", "6.2", "4.2", "9.3", "6.1.10", "10.1", "6.1.2", "4.1"]

    assert sorted(clause_ids, key=clause_sort_key) == [
        "4.1",
        "4.2",
        "6.1.2",
        "6.1.10",
        "6.2",
        "9.3",
        "10.1",
        "10.2",
    ]


def test_parent_clause_precedes_descendants() -> None:
    clause_ids = ["6.1.2", "6.2", "6.1.1", "6.1"]

    assert sorted(clause_ids, key=clause_sort_key) == ["6.1", "6.1.1", "6.1.2", "6.2"]


def test_nonnumeric_and_empty_ids_have_deterministic_fallback() -> None:
    clause_ids = ["Annex B", "", "A.2", "10.1", "A.1"]

    assert sorted(clause_ids, key=clause_sort_key) == ["10.1", "A.1", "A.2", "Annex B", ""]

