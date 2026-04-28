"""Recommendation service settings."""

from verdeai_shared.settings import Settings as BaseSettings


class RecommendationSettings(BaseSettings):
    SERVICE_NAME: str = "recommendation"


settings = RecommendationSettings()
