"""Tests for Principal model."""

import pytest
from verdeai_shared.auth.principal import Principal


def test_principal_construction() -> None:
    p = Principal(
        sub="user-123",
        tenant_id="tenant-abc",
        email="user@example.com",
        roles=["compliance-officer"],
    )
    assert p.sub == "user-123"
    assert p.tenant_id == "tenant-abc"
    assert p.email == "user@example.com"
    assert "compliance-officer" in p.roles


def test_principal_requires_all_fields() -> None:
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Principal.model_validate({})  # type: ignore[call-arg]


def test_principal_roles_default_list() -> None:
    p = Principal(sub="u", tenant_id="t", email="e@e.com", roles=[])
    assert p.roles == []
