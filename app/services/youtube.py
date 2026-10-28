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
    if spec.privacy not in VALID_PRIVACY: raise ValueError("Privacitat de YouTube no vàlida")
    if not spec.video.is_file(): raise ValueError("El vídeo final no existeix")
    if not spec.title.strip(): raise ValueError("El títol és obligatori")
    if spec.thumbnail is not None and not spec.thumbnail.is_file(): raise ValueError("La miniatura no existeix")

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

def load_credentials(client_secrets: Path, token_file: Path):
    Request, Credentials, InstalledAppFlow, _, _ = google_libraries()
    if not client_secrets.is_file(): raise YouTubeUnavailable("No s'ha configurat el fitxer OAuth de YouTube")
    credentials = Credentials.from_authorized_user_file(str(token_file), [YOUTUBE_UPLOAD_SCOPE]) if token_file.is_file() else None
    if credentials and credentials.expired and credentials.refresh_token: credentials.refresh(Request())
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), [YOUTUBE_UPLOAD_SCOPE])
        credentials = flow.run_local_server(host="127.0.0.1", port=0, open_browser=True)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json(), encoding="utf-8")
    return credentials

def build_service(client_secrets: Path, token_file: Path):
    _, _, _, build, _ = google_libraries()
    return build("youtube", "v3", credentials=load_credentials(client_secrets, token_file), cache_discovery=False)

def upload_video(spec: YouTubeUploadSpec, service) -> str:
    validate_upload(spec)
    _, _, _, _, MediaFileUpload = google_libraries()
    body = {"snippet": {"title": spec.title.strip(), "description": spec.description, "tags": spec.tags, "categoryId": spec.category_id, "defaultLanguage": spec.language}, "status": {"privacyStatus": spec.privacy}}
    media = MediaFileUpload(str(spec.video), mimetype="video/*", resumable=True, chunksize=8 * 1024 * 1024)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    video_id = response.get("id")
    if not video_id: raise RuntimeError("YouTube no ha retornat l'identificador del vídeo")
    if spec.thumbnail:
        thumbnail = MediaFileUpload(str(spec.thumbnail), mimetype="image/jpeg", resumable=False)
        service.thumbnails().set(videoId=video_id, media_body=thumbnail).execute()
    return video_id
