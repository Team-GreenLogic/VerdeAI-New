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
    ])

    # bm25_indexes
    await db.bm25_indexes.create_indexes([
        IndexModel([("tenant_id", ASCENDING)], unique=True),
    ])

    # iso_clauses
    await db.iso_clauses.create_indexes([
        IndexModel([("clause_id", ASCENDING)], unique=True),
    ])

    # iso_state_template
    await db.iso_state_template.create_indexes([
        IndexModel([("field_path", ASCENDING)], unique=True),
        IndexModel([("clause_id", ASCENDING)]),
    ])

    # org_profile
    await db.org_profile.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("field_path", ASCENDING)], unique=True),
    ])

    # state_store
    await db.state_store.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("clause_id", ASCENDING)], unique=True),
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

    # analyses
    await db.analyses.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("status", ASCENDING)]),
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
