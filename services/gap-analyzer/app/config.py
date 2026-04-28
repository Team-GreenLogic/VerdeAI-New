"""Gap Analyzer service settings."""

from verdeai_shared.settings import Settings as BaseSettings


class GapAnalyzerSettings(BaseSettings):
    SERVICE_NAME: str = "gap-analyzer"


settings = GapAnalyzerSettings()
