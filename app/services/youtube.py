"""Integració opcional amb YouTube Data API v3."""
from dataclasses import dataclass
import logging
import os
from pathlib import Path
from time import sleep

from app.config import settings

logger = logging.getLogger(__name__)
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
VALID_PRIVACY = {"private", "unlisted", "public"}
TRANSIENT_HTTP_STATUS = {429, 500, 502, 503, 504}
UPLOAD_MARKER = ".youtube-video-id"


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
    if len(spec.title) > 100:
        raise ValueError("El títol supera els 100 caràcters")
    if len(spec.description.encode("utf-8")) > 5000:
        raise ValueError("La descripció supera el límit de YouTube")
    if not spec.category_id.isdigit():
        raise ValueError("La categoria de YouTube no és vàlida")
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
        raise YouTubeUnavailable("Instal·la requirements-youtube.txt per activar YouTube") from exc
    return Request, Credentials, InstalledAppFlow, build, MediaFileUpload


def youtube_configured() -> bool:
    return settings.youtube_client_secrets.is_file()


def credentials():
    Request, Credentials, InstalledAppFlow, _, _ = google_libraries()
    token = settings.youtube_token_file
    creds = Credentials.from_authorized_user_file(str(token), [YOUTUBE_UPLOAD_SCOPE]) if token.is_file() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not settings.youtube_client_secrets.is_file():
            raise YouTubeUnavailable("Falta data/youtube-client-secret.json")
        flow = InstalledAppFlow.from_client_secrets_file(str(settings.youtube_client_secrets), [YOUTUBE_UPLOAD_SCOPE])
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    try:
        os.chmod(token, 0o600)
    except OSError:
        logger.warning("No s'han pogut restringir els permisos del token OAuth")
    return creds


def _marker_for(spec: YouTubeUploadSpec) -> Path:
    return spec.video.parent / UPLOAD_MARKER


def _existing_upload(spec: YouTubeUploadSpec) -> str | None:
    marker = _marker_for(spec)
    if not marker.is_file():
        return None
    video_id = marker.read_text(encoding="utf-8").strip()
    return video_id or None


def _remember_upload(spec: YouTubeUploadSpec, video_id: str) -> None:
    _marker_for(spec).write_text(video_id + "\n", encoding="utf-8")


def _http_status(exc: Exception) -> int | None:
    response = getattr(exc, "resp", None)
    return getattr(response, "status", None)


def upload_video(spec: YouTubeUploadSpec, *, max_retries: int = 3) -> str:
    """Publica una vegada i reutilitza l'ID local si el vídeo ja es va pujar."""
    validate_upload(spec)
    existing = _existing_upload(spec)
    if existing:
        logger.info("S'evita una pujada duplicada a YouTube: %s", existing)
        return existing

    _, _, _, build, MediaFileUpload = google_libraries()
    service = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    body = {
        "snippet": {
            "title": spec.title.strip(),
            "description": spec.description,
            "tags": spec.tags,
            "categoryId": spec.category_id,
            "defaultLanguage": spec.language,
        },
        "status": {"privacyStatus": spec.privacy},
    }
    media = MediaFileUpload(str(spec.video), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    retries = 0
    while response is None:
        try:
            _, response = request.next_chunk()
            retries = 0
        except Exception as exc:
            status = _http_status(exc)
            if status not in TRANSIENT_HTTP_STATUS or retries >= max_retries:
                raise
            retries += 1
            delay = min(2**retries, 8)
            logger.warning("Error temporal de YouTube (%s); reintent en %s s", status, delay)
            sleep(delay)

    video_id = response.get("id")
    if not video_id:
        raise YouTubeUnavailable("YouTube no ha retornat l'identificador del vídeo")

    # El marcador s'escriu abans de la miniatura: una fallada posterior no pot
    # provocar que el mateix vídeo es torne a pujar.
    _remember_upload(spec, video_id)
    if spec.thumbnail:
        try:
            service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(spec.thumbnail), mimetype="image/jpeg", resumable=False),
            ).execute()
        except Exception:
            logger.exception("El vídeo %s s'ha publicat, però la miniatura ha fallat", video_id)

    return video_id
