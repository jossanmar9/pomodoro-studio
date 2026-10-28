from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    app_name: str = "Pomodoro Studio"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = "sqlite:///./data/pomodoro.db"
    output_dir: Path = Path("./output")
    assets_dir: Path = Path("./assets")
    log_level: str = "INFO"
    youtube_client_secrets: Path = Path("./data/youtube-client-secret.json")
    youtube_token_file: Path = Path("./data/youtube-token.json")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
