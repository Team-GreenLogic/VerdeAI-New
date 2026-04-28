"""ISO Knowledge service settings."""

from verdeai_shared.settings import Settings as BaseSettings


class ISOKnowledgeSettings(BaseSettings):
    SERVICE_NAME: str = "iso-knowledge"

    # Demo tenant populated by seed
    DEMO_TENANT_ID: str = "00000000-0000-0000-0000-000000000001"


settings = ISOKnowledgeSettings()
