from pathlib import Path

from app.services import preflight


def test_estimate_required_bytes_grows_with_duration_and_resolution():
    short_hd = preflight.estimate_required_bytes(60, "1920x1080")
    long_hd = preflight.estimate_required_bytes(120, "1920x1080")
    short_qhd = preflight.estimate_required_bytes(60, "2560x1440")
    assert long_hd > short_hd
    assert short_qhd > short_hd


def test_preflight_reports_missing_resource(tmp_path: Path):
    result = preflight.check_render_preflight(
        tmp_path / "output",
        resources=(tmp_path / "missing.mp4",),
        duration_seconds=60,
        resolution="1920x1080",
        minimum_free_bytes=1,
        require_ffmpeg=False,
    )
    assert not result.ok
    assert any("Falten recursos" in error for error in result.errors)


def test_preflight_accepts_writable_output_and_existing_resources(tmp_path: Path):
    resource = tmp_path / "background.jpg"
    resource.write_bytes(b"image")
    result = preflight.check_render_preflight(
        tmp_path / "output",
        resources=(resource,),
        duration_seconds=1,
        resolution="1920x1080",
        minimum_free_bytes=1,
        require_ffmpeg=False,
    )
    assert result.ok
    assert result.free_bytes is not None
