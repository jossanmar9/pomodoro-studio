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
    # Privacitat per defecte en publicar des del mode automàtic.
    auto_default_privacy: str = "public"
    # Mode automàtic: si la casella «Afegir música» ix marcada (per defecte, només ambient).
    auto_music_default: bool = False
    # Dies que es conserva el vídeo publicat abans d'esborrar-lo (si s'ha demanat).
    keep_published_days: int = 3
    # Apagada en acabar: espera abans d'apagar (per poder cancel·lar-la) i ordre del sistema.
    shutdown_delay_seconds: int = 120
    shutdown_command: str = "systemctl poweroff"
    audio_catalog: Path = Path("./assets/audio-catalog.json")
    # Capes de moviment generades (pluja, neu, pols, guspires); es fan una vegada.
    overlays_dir: Path = Path("./data/overlays")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
