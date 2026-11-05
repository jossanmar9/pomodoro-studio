from datetime import datetime, timedelta
import json
import sqlite3

from app.config import settings
from app.services import backup, encoding
from app.services.text_variants import COMMENTS, first_comment


def test_weekly_backup_copies_database_env_and_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    with sqlite3.connect(tmp_path / "data" / "pomodoro.db") as db:
        db.execute("create table t (x)")
        db.execute("insert into t values (1)")
    (tmp_path / ".env").write_text("INSTAGRAM_USER_ID=1\n")
    token = tmp_path / "data" / "youtube-token.json"
    token.write_text("{}")
    monkeypatch.setattr(settings, "database_url", "sqlite:///./data/pomodoro.db")
    monkeypatch.setattr(settings, "youtube_token_file", token)
    monkeypatch.setattr(settings, "backup_keep", 2)
    folder = tmp_path / "copies"
    now = datetime(2026, 11, 6, 10, 0)
    first = backup.backup_if_due(folder, now)
    assert first and (first / "pomodoro.db").is_file() and (first / "env.txt").is_file() and (first / "youtube-token.json").is_file()
    with sqlite3.connect(first / "pomodoro.db") as db:
        assert db.execute("select x from t").fetchone() == (1,)
    assert backup.backup_if_due(folder, now + timedelta(days=3)) is None
    backup.backup_if_due(folder, now + timedelta(days=8))
    backup.backup_if_due(folder, now + timedelta(days=16))
    assert len(backup.backups(folder)) == 2 and not first.exists()


def test_first_comment_varies_and_fits_each_format():
    for fmt in ("pomodoro", "dormir", "llegir", "ambient", "rol", "soroll", "respiracio"):
        texts = {first_comment(fmt, seed) for seed in range(8)}
        assert len(texts) == 8 and all(0 < len(t) < 300 for t in texts)
    assert all(len(group) == 8 for group in COMMENTS.values())


def test_shorts_fall_back_to_cpu_if_the_gpu_fails(monkeypatch):
    calls = []

    class Result:
        def __init__(self, code):
            self.returncode, self.stdout, self.stderr = code, "", ""

    def fake_run(command, **kw):
        calls.append(command)
        return Result(1 if "h264_nvenc" in command else 0)

    monkeypatch.setattr(encoding.subprocess, "run", fake_run)
    command = ["ffmpeg", "-i", "x", *encoding.NVENC_SHORT_ARGS, "-pix_fmt", "yuv420p", "out.mp4"]
    assert encoding.run_encode(command).returncode == 0
    assert "libx264" in calls[1] and "h264_nvenc" not in calls[1] and calls[1][-3:] == ["-pix_fmt", "yuv420p", "out.mp4"]


def test_comment_waits_until_the_video_is_public(monkeypatch):
    from app.models import AutoRun
    from app.services import autopilot
    monkeypatch.setattr(autopilot, "can_comment", lambda: True)
    now = datetime(2026, 11, 6, 12, 0)
    run = AutoRun(step="DONE", video_id="v1", format="pomodoro", reels_json=json.dumps({"comment_wanted": True}),
                  scheduled_for=now + timedelta(days=2), published_at=now)
    assert not autopilot.comment_due(run, now)
    assert autopilot.comment_due(run, now + timedelta(days=2, minutes=1))
    run.reels_json = json.dumps({"comment_wanted": True, "comment_id": "c1"})
    assert not autopilot.comment_due(run, now + timedelta(days=3))
    run.reels_json = None
    assert not autopilot.comment_due(run, now + timedelta(days=3))
