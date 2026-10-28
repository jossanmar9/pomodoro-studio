from pathlib import Path

import pytest

from app.services.renderer import RenderSpec, build_ffmpeg_command, build_timer_filters
from app.services.timer import build_timeline


def test_timer_filters_use_timeline_segments():
    timeline = build_timeline(1, 1, 3)
    filters = build_timer_filters(timeline)
    assert "CONCENTRACIÓ" in filters
    assert "DESCANS" in filters
    assert "SESSIÓ 1" in filters
    assert "between(t,0," in filters


def test_image_background_uses_loop_and_exact_duration():
    timeline = build_timeline(1, 1, 2)
    spec = RenderSpec(Path("assets/backgrounds/prova.jpg"), Path("output/prova.mp4"), "1920x1080", timeline)
    command = build_ffmpeg_command(spec)
    assert command[0] == "ffmpeg"
    assert "-loop" in command
    assert command[command.index("-t") + 1] == "120"
    assert command[-1] == "output/prova.mp4"


def test_video_background_uses_stream_loop():
    timeline = build_timeline(1, 0, 1)
    spec = RenderSpec(Path("assets/backgrounds/prova.mp4"), Path("output/prova.mp4"), "2560x1440", timeline)
    command = build_ffmpeg_command(spec)
    assert "-stream_loop" in command
    assert "2560:1440" in command[command.index("-vf") + 1]


def test_rejects_unsupported_background():
    timeline = build_timeline(1, 0, 1)
    with pytest.raises(ValueError):
        build_ffmpeg_command(RenderSpec(Path("fons.txt"), Path("eixida.mp4"), "1920x1080", timeline))
