"""Example optional typed configuration using Pydantic Settings."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationSettings(BaseSettings):
    """Validate application-specific environment variables with Pydantic."""

    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env")
    debug: bool = False
    database_url: str
    api_key: SecretStr | None = None


SETTINGS = ApplicationSettings()
