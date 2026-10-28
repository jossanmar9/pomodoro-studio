from pathlib import Path

from app.services import preflight


def _ok_ffmpeg(monkeypatch):
    monkeypatch.setattr(preflight, "ffmpeg_available", lambda: True)


def test_preflight_ok_with_ffmpeg_resources_and_space(tmp_path: Path, monkeypatch):
    _ok_ffmpeg(monkeypatch)
    resource = tmp_path / "background.jpg"
    resource.write_bytes(b"x")
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _: type("Usage", (), {"free": 10 * 1024**3})())
    result = preflight.check_render_preflight(
        tmp_path / "out",
        resources=(resource,),
        duration_seconds=60,
        resolution="1920x1080",
    )
    assert result.ok
    assert result.errors == ()


def test_preflight_reports_missing_ffmpeg(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(preflight, "ffmpeg_available", lambda: False)
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _: type("Usage", (), {"free": 10 * 1024**3})())
    result = preflight.check_render_preflight(tmp_path)
    assert not result.ok
    assert "FFmpeg" in result.errors[0]


def test_preflight_rejects_missing_resource(tmp_path: Path, monkeypatch):
    _ok_ffmpeg(monkeypatch)
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _: type("Usage", (), {"free": 10 * 1024**3})())
    result = preflight.check_render_preflight(tmp_path / "out", resources=(tmp_path / "missing.mp3",))
    assert not result.ok
    assert "Falten recursos" in result.errors[0]


def test_preflight_rejects_insufficient_space(tmp_path: Path, monkeypatch):
    _ok_ffmpeg(monkeypatch)
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _: type("Usage", (), {"free": 100 * 1024**2})())
    result = preflight.check_render_preflight(tmp_path, minimum_free_bytes=512 * 1024**2)
    assert not result.ok
    assert any("Espai lliure insuficient" in error for error in result.errors)


def test_estimate_required_bytes_scales_with_resolution():
    low = preflight.estimate_required_bytes(3600, "1920x1080")
    high = preflight.estimate_required_bytes(3600, "2560x1440")
    assert high > low > 0
