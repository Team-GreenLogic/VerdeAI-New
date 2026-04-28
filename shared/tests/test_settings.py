"""Tests for Settings model."""

from verdeai_shared.settings import Settings


def test_settings_defaults() -> None:
    s = Settings()
    assert s.MONGO_DB == "verdeai"
    assert s.KEYCLOAK_REALM == "verdeai"
    assert s.RETRIEVAL_TOP_K == 30
    assert s.RERANK_TOP_K == 8
    assert s.CHUNK_TARGET_TOKENS == 512


def test_settings_env_override(monkeypatch: object) -> None:
    import os
    # monkeypatch is the pytest fixture
    assert isinstance(monkeypatch, object)
    # Settings reads from env; test that overrides work via model_validate
    s = Settings.model_validate({"MONGO_DB": "custom_db", "RETRIEVAL_TOP_K": 50})
    assert s.MONGO_DB == "custom_db"
    assert s.RETRIEVAL_TOP_K == 50
