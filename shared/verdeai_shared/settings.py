"""Global settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Core ---
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "verdeai"

    # --- Keycloak ---
    KEYCLOAK_URL: str = "http://keycloak:8080"
    KEYCLOAK_PUBLIC_URL: str = "http://localhost:8080"
    KEYCLOAK_REALM: str = "verdeai"
    KEYCLOAK_FRONTEND_CLIENT_ID: str = "verdeai-frontend"
    KEYCLOAK_ADMIN_CLIENT_ID: str = "verdeai-admin"
    KEYCLOAK_ADMIN_CLIENT_SECRET: str = ""
    KEYCLOAK_ADMIN_USER: str = "admin"
    KEYCLOAK_ADMIN_PASSWORD: str = "admin"
    KEYCLOAK_JWKS_CACHE_TTL_SECONDS: int = 3600
    KEYCLOAK_TOKEN_LEEWAY_SECONDS: int = 10

    # --- MongoDB ---
    MONGO_URI: str = "mongodb://mongodb:27017/?directConnection=true"
    MONGO_DB: str = "verdeai"
    VECTOR_INDEX_NAME: str = "chunks_vector_idx"
    ISO_VECTOR_INDEX_NAME: str = "iso_clauses_vector_idx"

    # --- RabbitMQ ---
    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672/"

    # --- Redis ---
    REDIS_URL: str = "redis://redis:6379/0"

    # --- OpenRouter ---
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_APP_URL: str = "https://verdeai.local"
    OPENROUTER_APP_NAME: str = "VerdeAI"
    PRIMARY_REASONING_MODEL: str = "deepseek/deepseek-r1-0528"
    CHEAP_REASONING_MODEL: str = "qwen/qwen3-coder"
    CHAT_MODEL: str = "deepseek/deepseek-chat"
    VISION_MODEL: str = "mistralai/mistral-small-3.1-24b-instruct"
    LLM_MAX_RETRIES: int = 3

    # --- Voyage AI ---
    VOYAGE_API_KEY: str = ""
    VOYAGE_EMBEDDING_MODEL: str = "voyage-3-large"
    VOYAGE_RERANKER_MODEL: str = "rerank-2.5"
    EMBEDDING_DIMENSIONS: int = 1024

    # --- LlamaParse ---
    LLAMA_CLOUD_API_KEY: str = ""
    LLAMA_PARSE_TIER: str = "agentic"          # fast | cost_effective | agentic | agentic_plus

    # --- Tavily ---
    TAVILY_API_KEY: str = ""

    # --- Observability ---
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    LANGFUSE_BASE_URL: str = ""  # alias used by some Langfuse SDK versions
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_SERVICE_NAME: str = ""

    # --- Service URLs ---
    CHAT_RAG_URL: str = "http://chat-rag:8001"

    # --- Admin ---
    ADMIN_EMAILS: str = ""  # comma-separated emails that auto-receive the admin role

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5173"  # comma-separated list of allowed origins

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # --- Tuning ---
    EMBED_BATCH_SIZE: int = 128
    EMBED_BATCH_DELAY: float = 0.0  # seconds between batches; set >0 on free-tier Voyage (3 RPM)
    RETRIEVAL_TOP_K: int = 30
    RERANK_TOP_K: int = 8
    CHUNK_TARGET_TOKENS: int = 512
    CHUNK_OVERLAP_TOKENS: int = 64

    # --- Gap-analysis validation (evidence grading / groundedness verification) ---
    RERANK_SCORE_THRESHOLD: float = 0.3   # chunks below this rerank score are dropped before analysis
    MIN_RELEVANT_CHUNKS: int = 2          # below this, a clause is routed to Insufficient Evidence
    MAX_VERIFY_RETRIES: int = 2           # bounded repair loop when a verdict fails grounding checks
    EVIDENCE_GRADER_ENABLED: bool = True  # toggle the LLM relevance-grading pass (CRAG-style)
    GRADER_MODEL: str = ""                # blank -> falls back to CHEAP_REASONING_MODEL

    def admin_email_set(self) -> set[str]:
        """Return the set of lowercase admin emails from the env var."""
        return {e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip()}


settings = Settings()
