"""Integració opcional amb YouTube Data API v3."""
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
from time import sleep

from app.config import settings

logger = logging.getLogger(__name__)
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
# Permís complet del canal: cal per a crear llistes de reproducció i afegir-hi vídeos.
YOUTUBE_MANAGE_SCOPE = "https://www.googleapis.com/auth/youtube"
# Permís per a escriure comentaris (el primer comentari de cada vídeo).
YOUTUBE_COMMENT_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
SCOPES = [YOUTUBE_UPLOAD_SCOPE, YOUTUBE_MANAGE_SCOPE, YOUTUBE_COMMENT_SCOPE]
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
    # Títol i descripció en altres idiomes: {"es": {"title": ..., "description": ...}, ...}
    localizations: dict[str, dict[str, str]] = field(default_factory=dict)
    # Publicació programada (ISO 8601 en UTC). YouTube el deixa privat fins a eixa hora i llavors el fa públic.
    publish_at: str | None = None


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
    # Es llig amb els permisos que es van donar (els tokens antics només tenen el de pujar vídeos).
    creds = Credentials.from_authorized_user_file(str(token)) if token.is_file() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not settings.youtube_client_secrets.is_file():
            raise YouTubeUnavailable("Falta data/youtube-client-secret.json")
        flow = InstalledAppFlow.from_client_secrets_file(str(settings.youtube_client_secrets), SCOPES)
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    try:
        os.chmod(token, 0o600)
    except OSError:
        logger.warning("No s'han pogut restringir els permisos del token OAuth")
    return creds


def granted_scopes() -> set[str]:
    try:
        data = json.loads(settings.youtube_token_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    scopes = data.get("scopes") or []
    return set(scopes.split() if isinstance(scopes, str) else scopes)


def can_manage_playlists() -> bool:
    """El canal està connectat amb el permís per a gestionar llistes (cal tornar a connectar els tokens antics)."""
    return YOUTUBE_MANAGE_SCOPE in granted_scopes()


def can_comment() -> bool:
    """El canal està connectat amb el permís per a comentar (cal tornar a connectar els tokens d'abans)."""
    return YOUTUBE_COMMENT_SCOPE in granted_scopes()


def has_all_permissions() -> bool:
    return can_manage_playlists() and can_comment()


def reconnect() -> None:
    """Esborra el token per a demanar els permisos nous (s'obri el navegador)."""
    settings.youtube_token_file.unlink(missing_ok=True)
    credentials()


def marker_path(video: Path) -> Path:
    """Marca de «ja pujat» d'un fitxer concret: video.mp4 i short.mp4 de la mateixa carpeta en tenen una cadascun."""
    return video.parent / (UPLOAD_MARKER if video.name == "video.mp4" else f"{UPLOAD_MARKER}.{video.stem}")


def _marker_for(spec: YouTubeUploadSpec) -> Path:
    return marker_path(spec.video)


def _existing_upload(spec: YouTubeUploadSpec) -> str | None:
    marker = _marker_for(spec)
    if not marker.is_file():
        return None
    video_id = marker.read_text(encoding="utf-8").strip()
    return video_id or None


def forget_upload(video: Path) -> None:
    """Permet tornar a pujar un vídeo que YouTube ha eliminat (per exemple, per massa llarg)."""
    marker_path(video).unlink(missing_ok=True)


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
        # No fet per a nens (COPPA). Sense restricció d'edat: és l'opció per defecte de YouTube.
        "status": {"privacyStatus": spec.privacy, "selfDeclaredMadeForKids": False},
    }
    if spec.publish_at:
        body["status"].update(privacyStatus="private", publishAt=spec.publish_at)
    parts = "snippet,status"
    if spec.localizations:
        body["localizations"] = spec.localizations
        parts += ",localizations"
    media = MediaFileUpload(str(spec.video), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    request = service.videos().insert(part=parts, body=body, media_body=media)
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


# ---------------------------------------------------------------- llistes de reproducció

def _playlist_cache() -> dict[str, str]:
    try:
        data = json.loads(settings.youtube_playlists_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _find_or_create_playlist(service, title: str, description: str, cache: dict[str, str]) -> str:
    if title in cache:
        return cache[title]
    page_token = None
    while True:
        response = service.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=page_token).execute()
        for item in response.get("items", []):
            cache.setdefault(item["snippet"]["title"], item["id"])
        page_token = response.get("nextPageToken")
        if title in cache or not page_token:
            break
    if title not in cache:
        created = service.playlists().insert(part="snippet,status", body={
            "snippet": {"title": title, "description": description, "defaultLanguage": "en"},
            "status": {"privacyStatus": "public"},
        }).execute()
        cache[title] = created["id"]
    return cache[title]


def add_to_playlists(video_id: str, playlists: list[tuple[str, str]], service=None) -> list[str]:
    """Afig el vídeo a les llistes (es creen si no existixen). Torna els títols de les llistes on s'ha afegit."""
    if not playlists:
        return []
    if service is None:
        _, _, _, build, _ = google_libraries()
        service = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    cache = _playlist_cache()
    added = []
    try:
        for title, description in playlists:
            playlist_id = _find_or_create_playlist(service, title, description, cache)
            service.playlistItems().insert(part="snippet", body={
                "snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}},
            }).execute()
            added.append(title)
    finally:
        settings.youtube_playlists_file.parent.mkdir(parents=True, exist_ok=True)
        settings.youtube_playlists_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return added


# ---------------------------------------------------------------- estadístiques

def view_counts(video_ids: list[str], service=None) -> dict[str, int]:
    """Visualitzacions de cada vídeo (de 50 en 50, com deixa YouTube)."""
    if not video_ids:
        return {}
    if service is None:
        _, _, _, build, _ = google_libraries()
        service = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    counts: dict[str, int] = {}
    for start in range(0, len(video_ids), 50):
        response = service.videos().list(part="statistics", id=",".join(video_ids[start:start + 50]), maxResults=50).execute()
        for item in response.get("items", []):
            counts[item["id"]] = int(item.get("statistics", {}).get("viewCount", 0))
    return counts


# ---------------------------------------------------------------- comentaris

def post_comment(video_id: str, text: str, service=None) -> str:
    """Escriu un comentari del canal en el vídeo. Torna l'identificador del comentari.

    L'API de YouTube no permet fixar-lo: si es vol fixat, cal fer-ho a mà des de YouTube Studio.
    """
    if service is None:
        _, _, _, build, _ = google_libraries()
        service = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    response = service.commentThreads().insert(part="snippet", body={
        "snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text}}},
    }).execute()
    return str(response["id"])
