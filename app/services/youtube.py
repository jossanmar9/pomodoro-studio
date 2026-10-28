"""Integració opcional amb YouTube Data API v3."""
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

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
    return settings.youtube_client_secret.is_file()


def credentials():
    Request, Credentials, InstalledAppFlow, _, _ = google_libraries()
    token = settings.youtube_token
    creds = None
    if token.is_file():
        creds = Credentials.from_authorized_user_file(str(token), [YOUTUBE_UPLOAD_SCOPE])
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not settings.youtube_client_secret.is_file():
            raise YouTubeUnavailable("Falta youtube-client-secret.json")
        flow = InstalledAppFlow.from_client_secrets_file(str(settings.youtube_client_secret), [YOUTUBE_UPLOAD_SCOPE])
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload_video(spec: YouTubeUploadSpec) -> str:
    validate_upload(spec)
    _, _, _, build, MediaFileUpload = google_libraries()
    service = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    body = {
        "snippet": {
            "title": spec.title,
            "description": spec.description,
            "tags": spec.tags,
            "categoryId": spec.category_id,
            "defaultLanguage": spec.language,
        },
        "status": {"privacyStatus": spec.privacy},
    }
    media = MediaFileUpload(str(spec.video), mimetype="video/*", resumable=True, chunksize=8 * 1024 * 1024)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    video_id = response.get("id")
    if not video_id:
        raise YouTubeUnavailable("YouTube no ha retornat l'identificador del vídeo")
    if spec.thumbnail:
        thumb = MediaFileUpload(str(spec.thumbnail), mimetype="image/jpeg", resumable=False)
        service.thumbnails().set(videoId=video_id, media_body=thumb).execute()
    return video_id
