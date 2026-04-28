"""API Gateway service-specific settings."""

from verdeai_shared.settings import Settings as BaseSettings


class GatewaySettings(BaseSettings):
    SERVICE_NAME: str = "api-gateway"

    # WebSocket ticket TTL in seconds
    WS_TICKET_TTL_SECONDS: int = 30

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60


settings = GatewaySettings()
