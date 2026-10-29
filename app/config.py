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
    image_a1111_url: str = ""
    image_a1111_model: str = ""
    image_generation_dir: Path = Path("./data/generated-images")
    image_a1111_upscaler: str = "Latent"
    # Mode automàtic: escalat del fons generat (1 = sense hires fix).
    auto_hires_scale: float = 1.5
    # Privacitat per defecte en publicar des del mode automàtic.
    auto_default_privacy: str = "public"
    audio_catalog: Path = Path("./assets/audio-catalog.json")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
