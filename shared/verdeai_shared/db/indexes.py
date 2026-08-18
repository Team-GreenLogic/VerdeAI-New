"""Idempotent index creation helpers."""

from motor.motor_asyncio import AsyncIOMotorDatabase  # type: ignore[import-untyped]
from pymongo import ASCENDING, IndexModel


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
    """Create all required indexes idempotently."""
    # users
    await db.users.create_indexes([
        IndexModel([("keycloak_sub", ASCENDING)], unique=True),
        IndexModel([("tenant_id", ASCENDING)]),
    ])

    # documents
    await db.documents.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("sha256", ASCENDING)]),
        IndexModel([("tenant_id", ASCENDING), ("status", ASCENDING)]),
    ])

    # chunks
    await db.chunks.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("document_id", ASCENDING)]),
        # Staleness detection: new chunks since an analysis baseline
        IndexModel([("tenant_id", ASCENDING), ("created_at", ASCENDING)]),
        # Staleness / delta: chunks superseded since an analysis baseline
        IndexModel([("tenant_id", ASCENDING), ("superseded", ASCENDING), ("superseded_at", ASCENDING)]),
    ])

    # bm25_indexes
    await db.bm25_indexes.create_indexes([
        IndexModel([("tenant_id", ASCENDING)], unique=True),
    ])

    # iso_versions (global, no tenant)
    await db.iso_versions.create_indexes([
        IndexModel([("version_id", ASCENDING)], unique=True),
        IndexModel([("status", ASCENDING)]),
    ])

    # iso_clauses — now unique per (version_id, clause_id)
    # Drop legacy single-field unique index if it still exists from old schema
    try:
        await db.iso_clauses.drop_index("clause_id_1")
    except Exception:
        pass
    await db.iso_clauses.create_indexes([
        IndexModel([("version_id", ASCENDING), ("clause_id", ASCENDING)], unique=True),
        IndexModel([("version_id", ASCENDING)]),
    ])

    # iso_state_template — now unique per (version_id, field_path)
    # Drop legacy single-field unique indexes if they still exist
    for _old_idx in ("field_path_1", "clause_id_1"):
        try:
            await db.iso_state_template.drop_index(_old_idx)
        except Exception:
            pass
    await db.iso_state_template.create_indexes([
        IndexModel([("version_id", ASCENDING), ("field_path", ASCENDING)], unique=True),
        IndexModel([("version_id", ASCENDING), ("clause_id", ASCENDING)]),
    ])

    # org_profile — now unique per (tenant_id, version_id, field_path)
    await db.org_profile.create_indexes([
        IndexModel(
            [("tenant_id", ASCENDING), ("version_id", ASCENDING), ("field_path", ASCENDING)],
            unique=True,
        ),
    ])

    # state_store — now unique per (tenant_id, version_id, clause_id)
    await db.state_store.create_indexes([
        IndexModel(
            [("tenant_id", ASCENDING), ("version_id", ASCENDING), ("clause_id", ASCENDING)],
            unique=True,
        ),
    ])

    # result_store
    await db.result_store.create_indexes([
        IndexModel([("analysis_id", ASCENDING)]),
        IndexModel(
            [("tenant_id", ASCENDING), ("analysis_id", ASCENDING), ("clause_id", ASCENDING)],
            unique=True,
        ),
    ])

    # recommendation_store
    await db.recommendation_store.create_indexes([
        IndexModel([("analysis_id", ASCENDING), ("priority", ASCENDING)]),
    ])

    # missing_request_store
    await db.missing_request_store.create_indexes([
        IndexModel([("analysis_id", ASCENDING)]),
    ])

    # analyses — include version_id index
    await db.analyses.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("status", ASCENDING)]),
        IndexModel([("tenant_id", ASCENDING), ("version_id", ASCENDING)]),
    ])

    # chat_history
    await db.chat_history.create_indexes([
        IndexModel([
            ("tenant_id", ASCENDING),
            ("session_id", ASCENDING),
            ("created_at", ASCENDING),
        ]),
    ])

    # chat_memory_summary
    await db.chat_memory_summary.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("session_id", ASCENDING)], unique=True),
    ])

    # hash_store
    await db.hash_store.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("sha256", ASCENDING)], unique=True),
    ])
