from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Union
from pydantic import Field, field_validator, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Enterprise Application Configuration using Pydantic Settings."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # General App Information
    APP_NAME: str = "Enterprise RAG AI Assistant"
    APP_ENV: Literal["development", "testing", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = Field(
        default="temporary-insecure-secret-key-replace-in-production-minimum-32-chars",
        min_length=32,
    )

    # JWT & Authentication Configuration
    JWT_SECRET_KEY: str = Field(
        default="jwt-insecure-secret-key-replace-in-production-minimum-32-chars",
        min_length=32,
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "enterprise-rag-api"
    JWT_AUDIENCE: str = "enterprise-rag-client"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Argon2id Parameters
    ARGON2_TIME_COST: int = 3
    ARGON2_MEMORY_COST: int = 65536  # 64 MB
    ARGON2_PARALLELISM: int = 4

    # Storage & Upload Configuration
    STORAGE_PROVIDER: Literal["local", "s3", "azure"] = "local"
    STORAGE_LOCAL_DIR: str = str((Path(__file__).resolve().parent.parent.parent.parent / "storage_data").resolve())
    MAX_UPLOAD_FILE_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB
    ALLOWED_FILE_EXTENSIONS: List[str] = [".pdf", ".docx", ".txt"]
    ALLOWED_MIME_TYPES: List[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    ]

    # Server Binding
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS Settings
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # PostgreSQL Connection Details
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "enterprise_rag_db"
    
    # Optional direct URIs (default built dynamically if absent)
    POSTGRES_ASYNC_URI: str | None = None
    POSTGRES_SYNC_URI: str | None = None

    # Database Pool Settings
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    @property
    def async_database_url(self) -> str:
        """Returns the async database URI for SQLAlchemy + asyncpg."""
        if self.POSTGRES_ASYNC_URI:
            return self.POSTGRES_ASYNC_URI
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_database_url(self) -> str:
        """Returns the sync database URI for Alembic migrations."""
        if self.POSTGRES_SYNC_URI:
            return self.POSTGRES_SYNC_URI
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Logging Settings
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"

    # AI Model & RAG Pipeline Configuration
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    LLM_MODEL: str = "gpt-4o-mini"
    OPENAI_API_KEY: str | None = None
    CHUNK_SIZE_TOKENS: int = 512
    CHUNK_OVERLAP_TOKENS: int = 64
    EMBEDDING_BATCH_SIZE: int = 100
    EMBEDDING_MAX_RETRIES: int = 3


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of the application settings."""
    return Settings()
