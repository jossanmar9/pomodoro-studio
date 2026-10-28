from pathlib import Path

from app.services import preflight


def test_preflight_ok_with_ffmpeg_and_space(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _: type("Usage", (), {"free": 10 * 1024**3})())
    result = preflight.check_render_preflight(tmp_path)
    assert result.ok
    assert result.errors == ()
    assert result.warnings == ()


def test_preflight_reports_missing_ffmpeg(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda _: None)
    result = preflight.check_render_preflight(tmp_path, minimum_free_bytes=0)
    assert not result.ok
    assert "FFmpeg" in result.errors[0]


def test_preflight_warns_when_disk_space_is_low(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _: type("Usage", (), {"free": 100 * 1024**2})())
    result = preflight.check_render_preflight(tmp_path)
    assert result.ok
    assert result.warnings
