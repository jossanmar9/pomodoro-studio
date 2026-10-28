from pathlib import Path

import pytest

from app.services.youtube import YouTubeUploadSpec, validate_upload


def test_youtube_upload_validation(tmp_path: Path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    spec = YouTubeUploadSpec(video=video, title="Focus", description="Study", tags=["pomodoro"], privacy="private")
    validate_upload(spec)


def test_youtube_upload_rejects_invalid_privacy(tmp_path: Path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    spec = YouTubeUploadSpec(video=video, title="Focus", description="", tags=[], privacy="friends")
    with pytest.raises(ValueError, match="Privacitat"):
        validate_upload(spec)


def test_youtube_upload_requires_video(tmp_path: Path):
    spec = YouTubeUploadSpec(video=tmp_path / "missing.mp4", title="Focus", description="", tags=[])
    with pytest.raises(ValueError, match="vídeo"):
        validate_upload(spec)
