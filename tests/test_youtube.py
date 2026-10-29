from pathlib import Path
import pytest

from app.services import youtube
from app.services.youtube import YouTubeUploadSpec, validate_upload


def make_spec(tmp_path: Path, **kwargs):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    data = {"video": video, "title": "Focus video", "description": "Description", "tags": ["pomodoro"], "category_id": "27", "language": "en", "privacy": "private"}
    data.update(kwargs)
    return YouTubeUploadSpec(**data)


def test_valid_upload(tmp_path):
    validate_upload(make_spec(tmp_path))


def test_invalid_privacy(tmp_path):
    with pytest.raises(ValueError):
        validate_upload(make_spec(tmp_path, privacy="friends"))


def test_missing_video(tmp_path):
    with pytest.raises(ValueError):
        validate_upload(make_spec(tmp_path, video=tmp_path / "missing.mp4"))


def test_title_limit(tmp_path):
    with pytest.raises(ValueError):
        validate_upload(make_spec(tmp_path, title="x" * 101))


def test_invalid_category(tmp_path):
    with pytest.raises(ValueError):
        validate_upload(make_spec(tmp_path, category_id="education"))


def test_existing_upload_marker_prevents_duplicate(tmp_path, monkeypatch):
    spec = make_spec(tmp_path)
    (tmp_path / youtube.UPLOAD_MARKER).write_text("abc123\n", encoding="utf-8")

    def should_not_load_google():
        raise AssertionError("No s'ha de contactar amb Google per a un vídeo ja publicat")

    monkeypatch.setattr(youtube, "google_libraries", should_not_load_google)
    assert youtube.upload_video(spec) == "abc123"


def test_marker_is_written_and_thumbnail_failure_does_not_duplicate(tmp_path, monkeypatch):
    spec = make_spec(tmp_path, thumbnail=tmp_path / "thumbnail.jpg")
    spec.thumbnail.write_bytes(b"jpg")

    class UploadRequest:
        def next_chunk(self):
            return None, {"id": "video42"}

    class Videos:
        def insert(self, **_kwargs):
            return UploadRequest()

    class ThumbnailRequest:
        def execute(self):
            raise RuntimeError("thumbnail error")

    class Thumbnails:
        def set(self, **_kwargs):
            return ThumbnailRequest()

    class Service:
        def videos(self):
            return Videos()
        def thumbnails(self):
            return Thumbnails()

    class Media:
        def __init__(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(youtube, "credentials", lambda: object())
    monkeypatch.setattr(youtube, "google_libraries", lambda: (None, None, None, lambda *_a, **_k: Service(), Media))

    assert youtube.upload_video(spec) == "video42"
    assert (tmp_path / youtube.UPLOAD_MARKER).read_text(encoding="utf-8").strip() == "video42"
    assert youtube.upload_video(spec) == "video42"



def test_scheduled_upload_requires_future_private_timestamp(tmp_path):
    from datetime import datetime, timedelta, timezone
    future = datetime.now(timezone.utc) + timedelta(days=1)
    validate_upload(make_spec(tmp_path, publish_at=future))
    for values in ({'publish_at':future,'privacy':'public'}, {'publish_at':datetime.now()},
                   {'publish_at':future-timedelta(days=2)}):
        with pytest.raises(ValueError):validate_upload(make_spec(tmp_path, **values))


def test_background_auth_does_not_start_browser(tmp_path, monkeypatch):
    class Credentials:
        pass
    class Flow:
        @staticmethod
        def from_client_secrets_file(*args):raise AssertionError('No interactive auth from worker')
    monkeypatch.setattr(youtube.settings, 'youtube_token_file', tmp_path / 'missing-token.json')
    monkeypatch.setattr(youtube, 'google_libraries', lambda: (None, Credentials, Flow, None, None))
    with pytest.raises(youtube.YouTubeUnavailable, match='autoritzar'):
        youtube.credentials(interactive=False)


def test_scheduled_request_sends_publish_at_and_explicit_private(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    calls = {}
    future = datetime.now(timezone.utc) + timedelta(days=2)
    spec = make_spec(tmp_path, publish_at=future, interactive_auth=False)
    class Request:
        def next_chunk(self):return None, {'id':'abcdefghijk'}
    class Videos:
        def insert(self, **kwargs):calls.update(kwargs);return Request()
    class Service:
        def videos(self):return Videos()
    class Media:
        def __init__(self, *a, **k):pass
    monkeypatch.setattr(youtube, 'google_libraries', lambda: (None, None, None, lambda *a, **k:Service(), Media))
    def auth(**kwargs):
        assert kwargs == {'interactive':False}
        return object()
    monkeypatch.setattr(youtube, 'credentials', auth)
    assert youtube.upload_video(spec) == 'abcdefghijk'
    assert calls['body']['status'] == {'privacyStatus':'private','publishAt':future.isoformat()}


def test_cross_process_upload_lock_blocks_duplicate(tmp_path):
    spec = make_spec(tmp_path)
    (tmp_path / '.youtube-upload.lock').write_text('active')
    with pytest.raises(youtube.YouTubeUnavailable, match='activa'):
        youtube.upload_video(spec)


def test_uncertain_upload_cannot_be_repeated(tmp_path):
    spec = make_spec(tmp_path)
    (tmp_path / '.youtube-upload-uncertain').write_text('unknown')
    with pytest.raises(youtube.YouTubeUnavailable, match='confirmada'):
        youtube.upload_video(spec)
    assert not (tmp_path / '.youtube-upload.lock').exists()
