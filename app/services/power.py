"""Apagada automàtica de l'ordinador quan acaba l'últim vídeo.

L'apagada sempre s'anuncia amb un compte enrere que es pot cancel·lar des de
la pàgina. L'ordre no passa per cap shell.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import shlex
import subprocess
import threading

from app.config import settings

logger = logging.getLogger(__name__)


def run_shutdown_command(command: str) -> None:
    subprocess.run(shlex.split(command), check=True, capture_output=True, text=True, timeout=30)


class PowerManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._at: datetime | None = None
        self._reason: str | None = None
        self.last_error: str | None = None

    def schedule(self, reason: str, delay: int | None = None) -> None:
        delay = settings.shutdown_delay_seconds if delay is None else delay
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            self._reason = reason
            self.last_error = None
            self._timer = threading.Timer(delay, self._fire)
            self._timer.daemon = True
            self._timer.start()
        logger.warning("Apagada programada d'ací %s s: %s", delay, reason)

    def cancel(self) -> bool:
        with self._lock:
            if not self._timer:
                return False
            self._timer.cancel()
            self._timer = None
            self._at = None
            self._reason = None
        logger.info("Apagada cancel·lada")
        return True

    def status(self) -> dict:
        with self._lock:
            if not self._at:
                return {"scheduled": False, "error": self.last_error}
            left = max(0, round((self._at - datetime.now(timezone.utc)).total_seconds()))
            return {"scheduled": True, "seconds_left": left, "reason": self._reason, "error": None}

    def _fire(self) -> None:
        with self._lock:
            if not self._timer:
                return
            self._timer = None
            self._at = None
        try:
            run_shutdown_command(settings.shutdown_command)
        except Exception as exc:  # p. ex. sense permisos o dins de Docker
            logger.exception("No s'ha pogut apagar l'ordinador")
            stderr = getattr(exc, "stderr", "") or ""
            self.last_error = f"No s'ha pogut apagar l'ordinador: {stderr.strip() or exc}"[:500]


power = PowerManager()
