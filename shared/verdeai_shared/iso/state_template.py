"""Standard per-clause state-template fields — single source of truth.

Both ``services/iso-knowledge/app/seed_iso.py`` (default version) and
``services/iso-knowledge/app/pipeline/build_version.py`` (custom-built versions) persist these
same 3 fields per clause into the global ``iso_state_template`` collection. If that collection is
missing rows for a given version — e.g. a custom version built before this seeding step existed,
or an interrupted build — ``synthesize_state_fields`` reproduces the exact same shape on the fly,
so ``generate_missing_requests`` never has to hard-depend on the DB having been pre-seeded.
"""

from __future__ import annotations

from typing import Any

STANDARD_STATE_FIELDS: list[dict[str, Any]] = [
    {"suffix": "gap_identified", "label": "Gap identified", "field_type": "boolean", "default": False},
    {"suffix": "conformance_score", "label": "Conformance score (0–1)", "field_type": "float", "default": 0.0},
    {"suffix": "evidence_notes", "label": "Evidence notes", "field_type": "string", "default": ""},
]


def synthesize_state_fields(clause_id: str) -> list[dict[str, Any]]:
    """Build the standard 3-field template for a clause, matching
    ``ISOStateRepository.list_for_clause``'s row shape (``field_path``, ``label``,
    ``field_type``, ``default``) without requiring a DB round-trip or pre-seeded data.
    """
    return [
        {
            "field_path": f"{clause_id}.{field['suffix']}",
            "label": field["label"],
            "field_type": field["field_type"],
            "default": field["default"],
        }
        for field in STANDARD_STATE_FIELDS
    ]
