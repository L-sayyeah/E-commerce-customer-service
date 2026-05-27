from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    app_name: str = "Custom Service Agent"
    debug: bool = True
    api_prefix: str = "/api/v1"

    database_url: str = Field(min_length=1)

    log_level: str = "INFO"
    log_file: str = "logs/app.log"

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
    )


settings = Settings()
