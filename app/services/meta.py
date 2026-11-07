"""Publicació dels Shorts com a reels a Instagram i a la pàgina de Facebook (API oficial de Meta).

Instagram (API amb inici de sessió d'Instagram):
  1. Es crea un contenidor de reel amb pujada «resumable».
  2. S'envia el fitxer a rupload.facebook.com.
  3. S'espera que Instagram el processe i es publica.
La clau d'Instagram caduca als 60 dies: es renova sola (una vegada al dia com a molt) i
la nova es guarda en data/instagram-token.json.

Facebook (pàgina): inici de la pujada, enviament del fitxer i publicació, amb una clau de
pàgina que no caduca (vegeu scripts/clau-facebook.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
import time
from typing import Callable
import urllib.error
import urllib.parse
import urllib.request

from app.config import settings

logger = logging.getLogger(__name__)

API_VERSION = "v23.0"
INSTAGRAM_GRAPH = f"https://graph.instagram.com/{API_VERSION}"
FACEBOOK_GRAPH = f"https://graph.facebook.com/{API_VERSION}"
INSTAGRAM_UPLOAD = f"https://rupload.facebook.com/ig-api-upload/{API_VERSION}"
FACEBOOK_UPLOAD = f"https://rupload.facebook.com/video-upload/{API_VERSION}"
PROCESS_TIMEOUT = 600  # segons màxims esperant que Instagram processe el vídeo
POLL_SECONDS = 5


class MetaError(RuntimeError):
    """Error en parlar amb Instagram o Facebook, amb un missatge entenedor."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    data: dict


# Funció que fa les peticions (es pot substituir en les proves).
Requester = Callable[[str, str, dict | None, dict | None, bytes | None], HttpResponse]


def _request(method: str, url: str, params: dict | None = None, headers: dict | None = None, body: bytes | None = None) -> HttpResponse:
    if params:
        encoded = urllib.parse.urlencode(params)
        if method == "GET" or body is not None:
            url = f"{url}?{encoded}"
        else:
            body = encoded.encode()
            headers = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            raw = response.read().decode("utf-8", "replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read().decode("utf-8", "replace"), exc.code
    except urllib.error.URLError as exc:
        raise MetaError(f"No hi ha connexió amb Meta: {exc.reason}") from exc
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {"raw": raw[:300]}
    return HttpResponse(status, data if isinstance(data, dict) else {"data": data})


def _check(response: HttpResponse, what: str) -> dict:
    if response.status >= 400 or "error" in response.data:
        error = response.data.get("error") or {}
        message = error.get("error_user_msg") or error.get("message") or response.data.get("raw") or f"HTTP {response.status}"
        raise MetaError(f"{what}: {message}"[:300])
    return response.data


# ---------------------------------------------------------------- configuració

def instagram_configured() -> bool:
    return bool(settings.instagram_user_id and _instagram_token())


def facebook_configured() -> bool:
    return bool(settings.facebook_page_id and settings.facebook_page_token)


def _token_file() -> dict:
    try:
        data = json.loads(settings.instagram_token_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _instagram_token() -> str:
    """La clau renovada (si n'hi ha) o la del fitxer .env."""
    saved = _token_file()
    if saved.get("token") and saved.get("source") == settings.instagram_access_token:
        return saved["token"]
    return settings.instagram_access_token


def _is_facebook_token(token: str) -> bool:
    """Les claus de Facebook (p. ex. d'usuari del sistema, que no caduquen) comencen per «EAA»; les d'Instagram, per «IG»."""
    return token.startswith("EAA")


def _instagram_graph(token: str) -> str:
    return FACEBOOK_GRAPH if _is_facebook_token(token) else INSTAGRAM_GRAPH


def refresh_instagram_token(request: Requester = _request, now: datetime | None = None) -> None:
    """Allarga 60 dies la clau d'Instagram (com a molt una vegada al dia). Les claus de Facebook no cal renovar-les."""
    if _is_facebook_token(_instagram_token()):
        return
    now = now or datetime.utcnow()
    saved = _token_file()
    if saved.get("source") == settings.instagram_access_token and saved.get("refreshed"):
        try:
            if now - datetime.fromisoformat(saved["refreshed"]) < timedelta(days=1):
                return
        except ValueError:
            pass
    response = request("GET", "https://graph.instagram.com/refresh_access_token",
                       {"grant_type": "ig_refresh_token", "access_token": _instagram_token()}, None, None)
    data = _check(response, "No s'ha pogut renovar la clau d'Instagram")
    if data.get("access_token"):
        settings.instagram_token_file.parent.mkdir(parents=True, exist_ok=True)
        settings.instagram_token_file.write_text(json.dumps({
            "token": data["access_token"], "source": settings.instagram_access_token, "refreshed": now.isoformat(timespec="seconds"),
        }), encoding="utf-8")


# ---------------------------------------------------------------- publicació

def publish_instagram_reel(video: Path, caption: str, *, request: Requester = _request, sleep: Callable[[float], None] = time.sleep) -> str:
    """Publica el vídeo com a reel a Instagram. Torna l'identificador de la publicació."""
    try:
        refresh_instagram_token(request)
    except MetaError as exc:  # la clau actual encara pot servir
        logger.warning("%s", exc)
    token, user = _instagram_token(), settings.instagram_user_id
    graph = _instagram_graph(token)
    container = _check(request("POST", f"{graph}/{user}/media", {
        "media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200], "share_to_feed": "true", "access_token": token,
    }, None, None), "Instagram no ha acceptat el reel")["id"]
    size = video.stat().st_size
    _check(request("POST", f"{INSTAGRAM_UPLOAD}/{container}", None,
                   {"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)}, video.read_bytes()),
           "No s'ha pogut pujar el vídeo a Instagram")
    waited = 0
    while True:
        status = _check(request("GET", f"{graph}/{container}", {"fields": "status_code,status", "access_token": token}, None, None),
                        "No s'ha pogut consultar el reel")
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code in {"ERROR", "EXPIRED"}:
            raise MetaError(f"Instagram no ha pogut processar el vídeo: {status.get('status') or code}"[:300])
        if waited >= PROCESS_TIMEOUT:
            raise MetaError("Instagram tarda massa a processar el vídeo")
        sleep(POLL_SECONDS)
        waited += POLL_SECONDS
    published = _check(request("POST", f"{graph}/{user}/media_publish", {"creation_id": container, "access_token": token}, None, None),
                       "Instagram no ha publicat el reel")
    return str(published["id"])


def publish_facebook_reel(video: Path, description: str, *, request: Requester = _request) -> str:
    """Publica el vídeo com a reel a la pàgina de Facebook. Torna l'identificador del vídeo."""
    page, token = settings.facebook_page_id, settings.facebook_page_token
    start = _check(request("POST", f"{FACEBOOK_GRAPH}/{page}/video_reels", {"upload_phase": "start", "access_token": token}, None, None),
                   "Facebook no ha acceptat el reel")
    video_id = str(start["video_id"])
    size = video.stat().st_size
    _check(request("POST", start.get("upload_url") or f"{FACEBOOK_UPLOAD}/{video_id}", None,
                   {"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size), "Content-Type": "application/octet-stream"},
                   video.read_bytes()), "No s'ha pogut pujar el vídeo a Facebook")
    _check(request("POST", f"{FACEBOOK_GRAPH}/{page}/video_reels", {
        "upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED", "description": description[:2200], "access_token": token,
    }, None, None), "Facebook no ha publicat el reel")
    return video_id


def _multipart(fields: dict, file_field: str, path: Path) -> tuple[bytes, str]:
    boundary = f"----amberwindow{int(time.time() * 1000)}"
    parts = []
    for key, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{path.name}\"\r\n"
                 f"Content-Type: image/jpeg\r\n\r\n".encode() + path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _public_image_url(image: Path, request: Requester) -> tuple[str, str]:
    """Instagram només agafa imatges d'una adreça pública: es pugen a la pàgina de Facebook sense publicar-les."""
    page, token = settings.facebook_page_id, settings.facebook_page_token
    body, content_type = _multipart({"published": "false", "access_token": token}, "source", image)
    photo = str(_check(request("POST", f"{FACEBOOK_GRAPH}/{page}/photos", None, {"Content-Type": content_type}, body),
                       "Facebook no ha acceptat la imatge")["id"])
    images = _check(request("GET", f"{FACEBOOK_GRAPH}/{photo}", {"fields": "images", "access_token": token}, None, None),
                    "No s'ha pogut llegir l'adreça de la imatge").get("images") or []
    if not images:
        raise MetaError("Facebook no ha tornat l'adreça de la imatge")
    best = max(images, key=lambda item: item.get("width", 0))
    return photo, best["source"]


def _wait_ready(graph: str, container: str, token: str, request: Requester, sleep: Callable[[float], None]) -> None:
    waited = 0
    while True:
        status = _check(request("GET", f"{graph}/{container}", {"fields": "status_code,status", "access_token": token}, None, None),
                        "No s'ha pogut consultar la publicació")
        code = status.get("status_code")
        if code in (None, "FINISHED"):
            return
        if code in {"ERROR", "EXPIRED"}:
            raise MetaError(f"Instagram no ha pogut preparar la imatge: {status.get('status') or code}"[:300])
        if waited >= PROCESS_TIMEOUT:
            raise MetaError("Instagram tarda massa a preparar la imatge")
        sleep(POLL_SECONDS)
        waited += POLL_SECONDS


def publish_instagram_images(images: list[Path], caption: str, *, request: Requester = _request,
                             sleep: Callable[[float], None] = time.sleep) -> str:
    """Publica una imatge o un carrusel (2-10 imatges) a Instagram. Torna l'identificador de la publicació.

    Cal la pàgina de Facebook configurada: les imatges hi passen sense publicar-se (vegeu _public_image_url).
    """
    if not images:
        raise MetaError("No hi ha imatges per publicar")
    if not facebook_configured():
        raise MetaError("Per a publicar imatges cal la pàgina de Facebook configurada (FACEBOOK_PAGE_ID i FACEBOOK_PAGE_TOKEN)")
    try:
        refresh_instagram_token(request)
    except MetaError as exc:
        logger.warning("%s", exc)
    token, user = _instagram_token(), settings.instagram_user_id
    graph = _instagram_graph(token)
    photos, urls = [], []
    for image in images:
        photo, url = _public_image_url(image, request)
        photos.append(photo)
        urls.append(url)
    try:
        if len(urls) == 1:
            container = _check(request("POST", f"{graph}/{user}/media", {"image_url": urls[0], "caption": caption[:2200], "access_token": token},
                                       None, None), "Instagram no ha acceptat la imatge")["id"]
        else:
            children = []
            for url in urls:
                child = _check(request("POST", f"{graph}/{user}/media", {"image_url": url, "is_carousel_item": "true", "access_token": token},
                                       None, None), "Instagram no ha acceptat una imatge del carrusel")["id"]
                _wait_ready(graph, child, token, request, sleep)
                children.append(str(child))
            container = _check(request("POST", f"{graph}/{user}/media", {
                "media_type": "CAROUSEL", "children": ",".join(children), "caption": caption[:2200], "access_token": token,
            }, None, None), "Instagram no ha acceptat el carrusel")["id"]
        _wait_ready(graph, container, token, request, sleep)
        published = _check(request("POST", f"{graph}/{user}/media_publish", {"creation_id": container, "access_token": token}, None, None),
                           "Instagram no ha publicat la imatge")
    finally:
        for photo in photos:  # les còpies de Facebook ja no calen (no s'havien publicat)
            try:
                request("DELETE", f"{FACEBOOK_GRAPH}/{photo}", {"access_token": settings.facebook_page_token}, None, None)
            except MetaError:
                pass
    return str(published["id"])


# ---------------------------------------------------------------- textos

def reel_caption(public_theme: str, subtitle: str, *, theme: str = "", fmt: str = "pomodoro", channel_url: str = "", facebook: bool = False,
                 seed: int = 0) -> str:
    """Text del reel (Instagram i Facebook, amb l'enllaç clicable en Facebook). Varia segons `seed`: vegeu captions.py."""
    from app.services.captions import reel_caption as varied
    return varied(public_theme, subtitle, theme=theme, fmt=fmt, channel_url=channel_url, facebook=facebook, seed=seed)
