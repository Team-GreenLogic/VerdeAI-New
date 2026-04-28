"""Missing Requirements service settings."""

from verdeai_shared.settings import Settings as BaseSettings


class MissingRequirementsSettings(BaseSettings):
    SERVICE_NAME: str = "missing-requirements"


settings = MissingRequirementsSettings()
