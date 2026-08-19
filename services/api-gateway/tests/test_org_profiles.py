"""Org profile soft-delete behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from verdeai_shared.auth.principal import Principal
from verdeai_shared.db.repositories.org_profiles import OrgProfilesRepository


@pytest.mark.asyncio
async def test_repository_soft_delete_flags_profile() -> None:
    collection = MagicMock()
    collection.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=1))
    db = MagicMock()
    db.__getitem__.return_value = collection
    profile_id = str(ObjectId())

    deleted = await OrgProfilesRepository(db, "tenant-1").soft_delete(profile_id)

    assert deleted is True
    query, update = collection.update_one.await_args.args
    assert query == {
        "tenant_id": "tenant-1",
        "_id": ObjectId(profile_id),
        "is_deleted": {"$ne": True},
    }
    assert update["$set"]["is_deleted"] is True
    assert update["$set"]["deleted_at"] is not None
    assert update["$set"]["updated_at"] is not None


@pytest.mark.asyncio
async def test_repository_get_and_list_exclude_deleted_profiles() -> None:
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value=None)
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    collection.find.return_value = cursor
    db = MagicMock()
    db.__getitem__.return_value = collection
    profile_id = str(ObjectId())
    repo = OrgProfilesRepository(db, "tenant-1")

    await repo.get(profile_id)
    await repo.list_all()

    collection.find_one.assert_awaited_once_with({
        "tenant_id": "tenant-1",
        "_id": ObjectId(profile_id),
        "is_deleted": {"$ne": True},
    })
    collection.find.assert_called_once_with(
        {"tenant_id": "tenant-1", "is_deleted": {"$ne": True}},
        sort=[("created_at", 1)],
    )


@pytest.mark.asyncio
async def test_delete_endpoint_preserves_related_data() -> None:
    from app.routers.org_profiles import delete_org_profile

    db = MagicMock()
    repo = MagicMock()
    repo.get = AsyncMock(return_value={"_id": ObjectId()})
    repo.soft_delete = AsyncMock(return_value=True)
    principal = Principal(
        sub="user-1",
        tenant_id="tenant-1",
        email="user@example.com",
        roles=["compliance-officer"],
    )
    profile_id = str(ObjectId())

    with (
        patch("app.routers.org_profiles.get_database", return_value=db),
        patch("app.routers.org_profiles.OrgProfilesRepository", return_value=repo),
    ):
        response = await delete_org_profile(profile_id, principal)

    assert response == {"profile_id": profile_id, "status": "deleted"}
    repo.soft_delete.assert_awaited_once_with(profile_id)
    assert "delete_many" not in str(db.mock_calls)

