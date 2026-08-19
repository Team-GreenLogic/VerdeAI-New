"""API Gateway service-specific settings."""

from verdeai_shared.settings import Settings as BaseSettings


class GatewaySettings(BaseSettings):
    SERVICE_NAME: str = "api-gateway"

    # WebSocket ticket TTL in seconds
    WS_TICKET_TTL_SECONDS: int = 30

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Comma-separated list of allowed CORS origins
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = GatewaySettings()
