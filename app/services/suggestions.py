"""Suggeriments del que toca fer: època de l'any, el que fa temps que no es fa i el que més funciona."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
import logging
from pathlib import Path
import threading

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Suggestion:
    text: str
    theme: str | None = None
    environment: str | None = None
    format: str | None = None


def easter(year: int) -> date:
    """Diumenge de Pasqua (calendari gregorià)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


# Temporades: (tema, primer dia, últim dia, motiu). Es comença abans perquè la gent ho busca amb antelació.
def _windows(year: int) -> list[tuple[str, date, date, str]]:
    pasqua = easter(year)
    return [
        ("Nadal", date(year, 11, 1), date(year, 12, 31), "la gent ja busca ambients de Nadal"),
        ("Nadal", date(year, 1, 1), date(year, 1, 6), "encara és temps de Nadal"),
        ("Halloween", date(year, 9, 20), date(year, 10, 31), "s'acosta Halloween"),
        ("Pasqua", pasqua - timedelta(days=28), pasqua + timedelta(days=7), "s'acosta Pasqua"),
        ("Hivern", date(year, 12, 1), date(year, 12, 31), "comença l'hivern"),
        ("Hivern", date(year, 1, 1), date(year, 2, 28), "és ple hivern"),
        ("Tardor", date(year, 9, 10), date(year, 11, 30), "és tardor"),
        ("Primavera", date(year, 3, 1), date(year, 5, 31), "és primavera"),
        ("Estiu", date(year, 6, 1), date(year, 8, 31), "és estiu"),
    ]


def seasonal_themes(today: date) -> list[tuple[str, str]]:
    """Temes de temporada que toquen ara, el més urgent primer."""
    found: list[tuple[str, str]] = []
    for theme, first, last, reason in _windows(today.year):
        if first <= today <= last and theme not in [t for t, _ in found]:
            found.append((theme, reason))
    return found


# Grups d'entorns per a dir «fa temps que no fas pluja».
SOUND_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "pluja": ("pluja", ("pluja", "pluja-finestra", "pluja-llar", "pluja-bosc", "pluja-ciutat", "tempesta", "llar-tempesta", "bosc-tempesta")),
    "llar de foc": ("llar", ("llar", "pluja-llar", "llar-tempesta", "hivern", "rellotge")),
    "cafeteria": ("cafeteria", ("cafeteria", "cafeteria-carrer")),
    "mar": ("mar", ("mar", "platja-tempesta", "tempesta-mar", "port")),
    "bosc": ("bosc", ("bosc", "pluja-bosc", "bosc-tempesta", "rierol", "riu")),
}


def _days_ago(when: datetime | None, today: date) -> int | None:
    return (today - when.date()).days if when else None


def build_suggestions(today: date, history: list[tuple[str, str, str, datetime | None, str | None]],
                      views: dict[str, int], theme_names: dict[str, str], available: set[str]) -> list[Suggestion]:
    """`history`: (tema, entorn, format, data de publicació, id de YouTube) dels vídeos publicats.

    `available`: temes que tenen algun fons (no se suggerix el que no es pot fer).
    """
    result: list[Suggestion] = []
    last_theme: dict[str, datetime] = {}
    last_env: dict[str, datetime] = {}
    for theme, env, _, when, _ in history:
        if when:
            last_theme[theme] = max(when, last_theme.get(theme, when))
            last_env[env] = max(when, last_env.get(env, when))

    for theme, reason in seasonal_themes(today):
        if theme not in available:
            continue
        ago = _days_ago(last_theme.get(theme), today)
        if ago is None or ago >= 5:
            when = "encara no n'has fet cap" if ago is None else f"l'últim va ser fa {ago} dies"
            result.append(Suggestion(f"Ara toca {theme}: {reason} ({when}).", theme=theme))
            break

    stale: list[tuple[int, str, str]] = []
    for label, (env_key, envs) in SOUND_GROUPS.items():
        dates = [last_env[e] for e in envs if e in last_env]
        ago = _days_ago(max(dates), today) if dates else None
        if ago is None or ago >= 14:
            stale.append((ago if ago is not None else 10_000, label, env_key))
    if stale:
        ago, label, env_key = max(stale)
        text = f"Encara no has fet cap vídeo de {label}." if ago == 10_000 else f"Fa {ago} dies que no fas cap vídeo de {label}."
        result.append(Suggestion(text, environment=env_key))

    totals: dict[str, list[int]] = {}
    for theme, _, _, _, video_id in history:
        if video_id and video_id in views:
            totals.setdefault(theme, []).append(views[video_id])
    ranked = sorted(((sum(v) / len(v), t) for t, v in totals.items() if len(v) >= 2), reverse=True)
    if ranked and ranked[0][0] > 0:
        average, theme = ranked[0]
        result.append(Suggestion(f"{theme} és el que més funciona: una mitjana de {round(average)} visualitzacions per vídeo.",
                                 theme=theme if theme in available else None))
    return result[:3]


# ---------------------------------------------------------------- visualitzacions guardades

_refreshing = threading.Lock()


def cached_views(path: Path) -> dict[str, int]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: int(v) for k, v in (data.get("views") or {}).items()}
    except (OSError, ValueError, AttributeError):
        return {}


def refresh_views_in_background(path: Path, video_ids: list[str], fetch, max_age_hours: int = 12) -> None:
    """Actualitza les visualitzacions en segon pla com a molt cada 12 hores (no fa esperar la pàgina)."""
    try:
        fetched = datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["fetched"])
        if datetime.utcnow() - fetched < timedelta(hours=max_age_hours):
            return
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if not video_ids or not _refreshing.acquire(blocking=False):
        return

    def work() -> None:
        try:
            views = fetch(video_ids)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"fetched": datetime.utcnow().isoformat(timespec="seconds"), "views": views}), encoding="utf-8")
        except Exception:
            logger.exception("No s'han pogut llegir les visualitzacions de YouTube")
        finally:
            _refreshing.release()

    threading.Thread(target=work, daemon=True).start()
