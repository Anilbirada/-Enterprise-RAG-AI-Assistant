import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_settings_defaults():
    """Verify default configuration values."""
    settings = Settings(
        SECRET_KEY="a" * 32,
        POSTGRES_SERVER="db.example.com",
        POSTGRES_PORT=5432,
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_db",
        POSTGRES_ASYNC_URI=None,
        POSTGRES_SYNC_URI=None,
    )
    assert settings.APP_NAME == "Enterprise RAG AI Assistant"
    assert settings.APP_ENV == "testing" or settings.APP_ENV == "development"
    assert settings.PORT == 8000
    assert "postgresql+asyncpg://test_user:test_password@db.example.com:5432/test_db" == settings.async_database_url
    assert "postgresql+psycopg2://test_user:test_password@db.example.com:5432/test_db" == settings.sync_database_url


def test_cors_origins_parsing():
    """Verify that comma-separated CORS strings are properly converted to lists."""
    settings = Settings(
        SECRET_KEY="a" * 32,
        CORS_ORIGINS="http://localhost:3000, http://example.com ,https://app.company.internal",
    )
    assert settings.CORS_ORIGINS == [
        "http://localhost:3000",
        "http://example.com",
        "https://app.company.internal",
    ]


def test_invalid_app_env_raises_validation_error():
    """Verify that an unsupported APP_ENV raises a clear validation error."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="invalid_environment_name",
            SECRET_KEY="a" * 32,
        )
    assert "APP_ENV" in str(exc_info.value)


def test_short_secret_key_raises_validation_error():
    """Verify that SECRET_KEY with fewer than 32 characters is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            SECRET_KEY="short-key",
        )
    assert "SECRET_KEY" in str(exc_info.value)
