"""Idempotent index creation helpers."""

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase  # type: ignore[import-untyped]
from pymongo import ASCENDING, IndexModel
from pymongo.errors import DuplicateKeyError

_SUMMARY_FIELD_PATHS = {
    "org_name": "org.name",
    "org_industry": "org.industry",
    "org_size": "org.size",
    "org_location": "org.location",
    "primary_activities": "org.primary_activities",
    "leadership_roles": "org.leadership_roles",
}
_BACKFILL_MIGRATION_ID = "org_profiles_backfill_v1"


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
    """Create all required indexes idempotently."""
    # users
    await db.users.create_indexes([
        IndexModel([("keycloak_sub", ASCENDING)], unique=True),
        IndexModel([("tenant_id", ASCENDING)]),
    ])

    # org_profiles — registry of org profiles, one doc per profile
    await db.org_profiles.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("is_deleted", ASCENDING)]),
    ])

    # documents — now unique per (tenant_id, profile_id, ...)
    await db.documents.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("profile_id", ASCENDING), ("sha256", ASCENDING)]),
        IndexModel([("tenant_id", ASCENDING), ("profile_id", ASCENDING), ("status", ASCENDING)]),
    ])

    # chunks
    await db.chunks.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("profile_id", ASCENDING), ("document_id", ASCENDING)]),
        # Staleness detection: new chunks since an analysis baseline
        IndexModel([("tenant_id", ASCENDING), ("profile_id", ASCENDING), ("created_at", ASCENDING)]),
        # Staleness / delta: chunks superseded since an analysis baseline
        IndexModel([
            ("tenant_id", ASCENDING),
            ("profile_id", ASCENDING),
            ("superseded", ASCENDING),
            ("superseded_at", ASCENDING),
        ]),
    ])

    # bm25_indexes — now one doc per (tenant_id, profile_id), not per tenant_id
    try:
        await db.bm25_indexes.drop_index("tenant_id_1")
    except Exception:
        pass
    await db.bm25_indexes.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("profile_id", ASCENDING)], unique=True),
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

    # org_profile — per-clause field store, now unique per (tenant_id, profile_id, version_id, field_path)
    try:
        await db.org_profile.drop_index("tenant_id_1_version_id_1_field_path_1")
    except Exception:
        pass
    await db.org_profile.create_indexes([
        IndexModel(
            [
                ("tenant_id", ASCENDING),
                ("profile_id", ASCENDING),
                ("version_id", ASCENDING),
                ("field_path", ASCENDING),
            ],
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

    # analyses — include profile_id + version_id indexes
    await db.analyses.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("profile_id", ASCENDING), ("status", ASCENDING)]),
        IndexModel([("tenant_id", ASCENDING), ("profile_id", ASCENDING), ("version_id", ASCENDING)]),
    ])

    # chat_history
    await db.chat_history.create_indexes([
        IndexModel([
            ("tenant_id", ASCENDING),
            ("session_id", ASCENDING),
            ("created_at", ASCENDING),
        ]),
        IndexModel([
            ("tenant_id", ASCENDING),
            ("profile_id", ASCENDING),
            ("created_at", ASCENDING),
        ]),
    ])

    # chat_memory_summary
    await db.chat_memory_summary.create_indexes([
        IndexModel([("tenant_id", ASCENDING), ("session_id", ASCENDING)], unique=True),
    ])

    # hash_store — now unique per (tenant_id, profile_id, sha256), so the same
    # file uploaded to two different org profiles isn't wrongly deduped against
    # each other.
    try:
        await db.hash_store.drop_index("tenant_id_1_sha256_1")
    except Exception:
        pass
    await db.hash_store.create_indexes([
        IndexModel(
            [("tenant_id", ASCENDING), ("profile_id", ASCENDING), ("sha256", ASCENDING)],
            unique=True,
        ),
    ])

    # migrations collection needs no explicit index — sentinel docs are keyed by
    # their _id, which MongoDB indexes uniquely by default.
    await _backfill_org_profiles(db)


async def _backfill_org_profiles(db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
    """One-off idempotent migration: create a Default org profile per tenant that
    already has profile_id-less data, and stamp that data with its profile_id.

    Safe to call on every service startup — claims the migration via an
    insert-once sentinel doc, so concurrent replicas race harmlessly (only the
    one that wins the insert proceeds; everyone else returns immediately).
    """
    try:
        await db.migrations.insert_one({
            "_id": _BACKFILL_MIGRATION_ID,
            "claimed_at": datetime.now(timezone.utc),
        })
    except DuplicateKeyError:
        return

    tenants: set[str] = set()
    tenants |= set(await db.org_profile.distinct("tenant_id", {"profile_id": {"$exists": False}}))
    tenants |= set(await db.documents.distinct("tenant_id", {"profile_id": {"$exists": False}}))
    tenants |= set(await db.analyses.distinct("tenant_id", {"profile_id": {"$exists": False}}))
    tenants |= set(await db.chat_history.distinct("tenant_id", {"profile_id": {"$exists": False}}))
    tenants |= set(await db.hash_store.distinct("tenant_id", {"profile_id": {"$exists": False}}))

    for tenant_id in tenants:
        old_rows = await db.org_profile.find({
            "tenant_id": tenant_id,
            "profile_id": {"$exists": False},
        }).to_list(length=None)
        old_by_path = {row["field_path"]: row.get("value") for row in old_rows}

        description_parts: list[str] = []
        primary_activities = old_by_path.get(_SUMMARY_FIELD_PATHS["primary_activities"])
        leadership_roles = old_by_path.get(_SUMMARY_FIELD_PATHS["leadership_roles"])
        if primary_activities:
            description_parts.append(f"Primary activities: {primary_activities}")
        if leadership_roles:
            description_parts.append(f"Leadership roles: {leadership_roles}")

        profile_doc = {
            "tenant_id": tenant_id,
            "is_deleted": False,
            "deleted_at": None,
            "org_name": old_by_path.get(_SUMMARY_FIELD_PATHS["org_name"]),
            "org_industry": old_by_path.get(_SUMMARY_FIELD_PATHS["org_industry"]),
            "org_size": old_by_path.get(_SUMMARY_FIELD_PATHS["org_size"]),
            "org_location": old_by_path.get(_SUMMARY_FIELD_PATHS["org_location"]),
            "description": "\n\n".join(description_parts) or None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        result = await db.org_profiles.insert_one(profile_doc)
        profile_id = str(result.inserted_id)

        await db.documents.update_many(
            {"tenant_id": tenant_id, "profile_id": {"$exists": False}},
            {"$set": {"profile_id": profile_id}},
        )
        await db.analyses.update_many(
            {"tenant_id": tenant_id, "profile_id": {"$exists": False}},
            {"$set": {"profile_id": profile_id}},
        )
        await db.chunks.update_many(
            {"tenant_id": tenant_id, "profile_id": {"$exists": False}},
            {"$set": {"profile_id": profile_id}},
        )
        await db.chat_history.update_many(
            {"tenant_id": tenant_id, "profile_id": {"$exists": False}},
            {"$set": {"profile_id": profile_id}},
        )
        await db.hash_store.update_many(
            {"tenant_id": tenant_id, "profile_id": {"$exists": False}},
            {"$set": {"profile_id": profile_id}},
        )

        # Remaining (per-clause) org_profile rows keep living in this collection —
        # stamp them with the new profile_id. The migrated summary rows are removed.
        summary_paths = list(_SUMMARY_FIELD_PATHS.values())
        await db.org_profile.update_many(
            {
                "tenant_id": tenant_id,
                "profile_id": {"$exists": False},
                "field_path": {"$nin": summary_paths},
            },
            {"$set": {"profile_id": profile_id}},
        )
        await db.org_profile.delete_many({
            "tenant_id": tenant_id,
            "profile_id": {"$exists": False},
            "field_path": {"$in": summary_paths},
        })

        # Rebuild the tenant's BM25 index under the new (tenant_id, profile_id) key.
        old_bm25 = await db.bm25_indexes.find_one({"tenant_id": tenant_id, "profile_id": {"$exists": False}})
        if old_bm25:
            await db.bm25_indexes.update_one(
                {"tenant_id": tenant_id, "profile_id": {"$exists": False}},
                {"$set": {"profile_id": profile_id}},
            )

    await db.migrations.update_one(
        {"_id": _BACKFILL_MIGRATION_ID},
        {"$set": {"completed_at": datetime.now(timezone.utc)}},
    )
