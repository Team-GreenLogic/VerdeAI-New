"""Chat RAG service settings."""

from verdeai_shared.settings import Settings as BaseSettings


class ChatRAGSettings(BaseSettings):
    SERVICE_NAME: str = "chat-rag"

    # Short-term memory window
    CHAT_HISTORY_WINDOW: int = 10

    # Long-term summary update interval (every N turns)
    MEMORY_SUMMARY_INTERVAL: int = 10


settings = ChatRAGSettings()
