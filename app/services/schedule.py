"""Calendari de publicació: un vídeo al dia a l'hora triada, en el primer dia lliure.

Les hores es guarden en UTC (sense zona) i es mostren en l'hora local.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

DAYS = ["dl", "dt", "dc", "dj", "dv", "ds", "dg"]
MARGIN = timedelta(minutes=15)  # si queda menys d'açò, es publica directament


def to_local(when_utc: datetime, zone: str) -> datetime:
    return when_utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(zone))


def to_utc(local: datetime) -> datetime:
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def next_slot(now_utc: datetime, taken_utc: list[datetime], *, hour: int, zone: str, min_hours_ahead: int = 6) -> datetime:
    """Primer dia sense cap vídeo programat, a l'hora triada, amb temps per a renderitzar."""
    tz = ZoneInfo(zone)
    now_local = to_local(now_utc, zone)
    busy: set[date] = {to_local(t, zone).date() for t in taken_utc}
    day = now_local.date()
    while True:
        candidate = datetime.combine(day, time(hour), tz)
        if candidate - now_local >= timedelta(hours=min_hours_ahead) and day not in busy:
            return to_utc(candidate)
        day += timedelta(days=1)


def publish_at(scheduled_utc: datetime | None, now_utc: datetime) -> str | None:
    """Valor de publishAt per a YouTube, o None si l'hora ja ha passat (es publica de seguida)."""
    if not scheduled_utc or scheduled_utc - now_utc < MARGIN:
        return None
    return scheduled_utc.replace(microsecond=0).isoformat() + "Z"


def label(when_utc: datetime, zone: str) -> str:
    local = to_local(when_utc, zone)
    return f"{DAYS[local.weekday()]} {local.day}/{local.month} a les {local:%H:%M}"


def from_local(day: str, clock: str, zone: str) -> datetime:
    """«2026-11-09» i «18:00» en hora local → UTC (sense zona)."""
    local = datetime.combine(date.fromisoformat(day), time.fromisoformat(clock), ZoneInfo(zone))
    return to_utc(local)


def local_day(when_utc: datetime, zone: str) -> str:
    return to_local(when_utc, zone).date().isoformat()
