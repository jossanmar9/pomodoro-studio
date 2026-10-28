"""Integració opcional amb YouTube Data API v3."""
from dataclasses import dataclass
from pathlib import Path

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
VALID_PRIVACY = {"private", "unlisted", "public"}


class YouTubeUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class YouTubeUploadSpec:
    video: Path
    title: str
    description: str
    tags: list[str]
    category_id: str = "27"
    language: str = "en"
    privacy: str = "private"
    thumbnail: Path | None = None


def validate_upload(spec: YouTubeUploadSpec) -> None:
    if spec.privacy not in VALID_PRIVACY:
        raise ValueError("Privacitat de YouTube no vàlida")
    if not spec.video.is_file():
        raise ValueError("El vídeo final no existeix")
    if not spec.title.strip():
        raise ValueError("El títol és obligatori")
    if spec.thumbnail is not None and not spec.thumbnail.is_file():
        raise ValueError("La miniatura no existeix")


def google_libraries():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise YouTubeUnavailable("Falten les dependències opcionals de Google/YouTube") from exc
    return Request, Credentials, InstalledAppFlow, build, MediaFileUpload
