"""Document Processor service settings."""

from verdeai_shared.settings import Settings as BaseSettings


class ProcessorSettings(BaseSettings):
    SERVICE_NAME: str = "document-processor"

    # Temp upload directory inside container
    UPLOAD_DIR: str = "/tmp/verdeai-uploads"


settings = ProcessorSettings()
