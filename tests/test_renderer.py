from pathlib import Path
import pytest
from app.services.renderer import AudioTrack, RenderSpec, build_ffmpeg_command, build_timer_filters
from app.services.timer import build_timeline

def test_timer_filters_use_timeline_segments():
    filters = build_timer_filters(build_timeline(1, 1, 3))
    assert "CONCENTRACIÓ" in filters and "DESCANS" in filters and "SESSIÓ 1" in filters

def test_image_background_uses_loop_progress_and_exact_duration():
    timeline = build_timeline(1, 1, 2)
    command = build_ffmpeg_command(RenderSpec(Path("assets/backgrounds/prova.jpg"), Path("output/prova.mp4"), "1920x1080", timeline))
    assert command[0] == "ffmpeg"
    assert "-loop" in command and "-progress" in command
    assert command[command.index("-t") + 1] == "120"
    assert command[-1] == "output/prova.mp4"

def test_video_background_uses_stream_loop_and_resolution():
    timeline = build_timeline(1, 0, 1)
    command = build_ffmpeg_command(RenderSpec(Path("assets/backgrounds/prova.mp4"), Path("output/prova.mp4"), "2560x1440", timeline))
    assert "-stream_loop" in command
    assert "2560:1440" in command[command.index("-filter_complex") + 1]

def test_audio_is_mixed():
    timeline = build_timeline(1, 0, 1)
    spec = RenderSpec(Path("fons.jpg"), Path("eixida.mp4"), "1920x1080", timeline, ambience=[AudioTrack(Path("pluja.ogg"), .3)], music=AudioTrack(Path("musica.mp3"), .1))
    command = build_ffmpeg_command(spec)
    graph = command[command.index("-filter_complex") + 1]
    assert "amix=inputs=2" in graph and "volume=0.3" in graph and "volume=0.1" in graph

def test_rejects_unsupported_background():
    with pytest.raises(ValueError):
        build_ffmpeg_command(RenderSpec(Path("fons.txt"), Path("eixida.mp4"), "1920x1080", build_timeline(1, 0, 1)))
