import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application Configuration
    APP_NAME: str = "Automated Competitor Intelligence Engine"
    DEBUG: bool = False

    # Database Configuration
    DB_PATH: str = str(
        Path(__file__).resolve().parent.parent.parent / "analytics.duckdb"
    )

    # External APIs
    GEMINI_API_KEY: str = ""

    # Pipeline Settings
    BATCH_SIZE: int = 50
    MAX_RETRIES: int = 3

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()