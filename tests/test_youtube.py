from pathlib import Path
import pytest
from app.services.youtube import YouTubeUploadSpec, validate_upload

def make_spec(tmp_path:Path,**kwargs):
    video=tmp_path/"video.mp4"; video.write_bytes(b"video")
    data={"video":video,"title":"Focus video","description":"Description","tags":["pomodoro"],"category_id":"27","language":"en","privacy":"private"}; data.update(kwargs); return YouTubeUploadSpec(**data)
def test_valid_upload(tmp_path): validate_upload(make_spec(tmp_path))
def test_invalid_privacy(tmp_path):
    with pytest.raises(ValueError): validate_upload(make_spec(tmp_path,privacy="friends"))
def test_missing_video(tmp_path):
    with pytest.raises(ValueError): validate_upload(make_spec(tmp_path,video=tmp_path/"missing.mp4"))
def test_title_limit(tmp_path):
    with pytest.raises(ValueError): validate_upload(make_spec(tmp_path,title="x"*101))
def test_invalid_category(tmp_path):
    with pytest.raises(ValueError): validate_upload(make_spec(tmp_path,category_id="education"))
