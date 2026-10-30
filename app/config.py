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
    image_a1111_upscaler: str = "R-ESRGAN 4x+"
    # auto (pel nom del model carregat en Forge), flux-schnell, flux-dev o sdxl.
    image_model_profile: str = "auto"
    # Mode automàtic: escalat del fons generat (1 = sense hires fix).
    auto_hires_scale: float = 1.5
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
