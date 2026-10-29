from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import automation as auto
from app import main as web
from app.database import Base
from app.models import Project

UTC = timezone.utc
NOW = datetime(2026, 10, 29, 10, tzinfo=UTC)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    assets = tmp_path / 'assets'; (assets / 'backgrounds').mkdir(parents=True)
    (assets / 'backgrounds/room.png').write_bytes(b'background')
    (assets / 'backgrounds/room.png.json').write_text('{"provider":"a1111"}')
    monkeypatch.setattr(auto.settings, 'assets_dir', assets)
    monkeypatch.setattr(auto.settings, 'output_dir', tmp_path / 'output')
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(auto, 'SessionLocal', sessions)
    monkeypatch.setattr(web, 'SessionLocal', sessions)
    monkeypatch.setattr(auto, 'channel', lambda **kw: ('UCexpected', 'The Amber Window'))
    monkeypatch.setattr(web, 'generate_thumbnail', lambda bg, target, title: target.write_bytes(b'jpg'))
    def render(pid, spec):
        spec.output.write_bytes(b'video')
        with sessions() as db:
            p = db.get(Project, pid); p.status = 'COMPLETED'; db.commit()
    monkeypatch.setattr(web.render_queue, 'enqueue', render)
    uploads = []
    def upload(spec):
        uploads.append(spec)
        (spec.video.parent / auto.UPLOAD_MARKER).write_text('abcdefghijk')
        return 'abcdefghijk'
    monkeypatch.setattr(auto, 'upload_video', upload)
    config = auto.Config(scenes=[auto.Scene(theme='Cabana amb pluja', title='Rainy Reading Room', background='room.png')],
                         expected_channel_id='UCexpected')
    with auto.locked_state(tmp_path / 'state') as db:
        with TestClient(web.app, follow_redirects=False) as client:
            yield config, db, client, uploads
    engine.dispose()


def complete_trial(config, db, client):
    for expected in ['PREPARED', 'RENDERING', 'RENDERED', 'UPLOADED: abcdefghijk']:
        assert auto.tick(config, db, client, test=True, now=NOW) == expected


def approve(db):
    db.execute('INSERT INTO approvals VALUES (?)', ('abcdefghijk',)); db.commit()


def test_private_trial_integrates_with_project_api_once(setup):
    cfg, db, client, uploads = setup
    complete_trial(cfg, db, client)
    assert len(uploads) == 1
    assert uploads[0].privacy == 'private' and uploads[0].publish_at is None
    assert uploads[0].interactive_auth is False
    assert 'The Amber Window' in uploads[0].description
    assert 'Crèdits' not in uploads[0].description  # public copy stays English
    auto.tick(cfg, db, client, test=True, now=NOW)
    assert len(uploads) == 1
    with auto.SessionLocal() as projects:
        p = projects.query(Project).one()
        assert p.duration_minutes == 120 and p.status == 'COMPLETED'


def test_public_schedule_requires_approved_trial(setup):
    cfg, db, client, uploads = setup
    assert auto.tick(cfg, db, client, now=NOW).startswith('Desactivat')
    cfg.enabled = True
    with pytest.raises(ValueError, match='aprova'):
        auto.tick(cfg, db, client, now=NOW)
    assert not uploads


def test_scheduled_upload_uses_future_publish_at_and_saved_snapshot(setup):
    cfg, db, client, uploads = setup
    complete_trial(cfg, db, client); approve(db); cfg.enabled = True
    assert auto.tick(cfg, db, client, now=NOW) == 'PREPARED'
    cfg.scenes[0].title = 'Edited after planning'
    assert auto.tick(cfg, db, client, now=NOW) == 'RENDERING'
    assert auto.tick(cfg, db, client, now=NOW) == 'RENDERED'
    assert auto.tick(cfg, db, client, now=NOW).startswith('UPLOADED')
    spec = uploads[-1]
    assert spec.publish_at == datetime(2026, 10, 30, 17, tzinfo=UTC)  # 18:00 Madrid
    assert 'Edited after planning' not in spec.title
    assert spec.privacy == 'private'
    assert len(uploads) == 2
    auto.tick(cfg, db, client, now=NOW)
    assert len(uploads) == 2


def test_unknown_upload_result_is_never_blindly_retried(setup, monkeypatch):
    cfg, db, client, uploads = setup
    for _ in range(3): auto.tick(cfg, db, client, test=True, now=NOW)
    calls = []
    def uncertain(spec):
        calls.append(spec); raise TimeoutError('response lost')
    monkeypatch.setattr(auto, 'upload_video', uncertain)
    with pytest.raises(TimeoutError): auto.tick(cfg, db, client, test=True, now=NOW)
    assert db.execute('SELECT status FROM runs').fetchone()[0] == 'UNCERTAIN'
    auto.tick(cfg, db, client, test=True, now=NOW)
    assert len(calls) == 1


def test_crash_after_upload_recovers_marker_without_new_insert(setup):
    cfg, db, client, uploads = setup
    complete_trial(cfg, db, client)
    row = db.execute('SELECT payload FROM runs').fetchone()
    auto.save(db, 'private-test', 'UPLOADING', json.loads(row[0]))
    assert auto.tick(cfg, db, client, test=True, now=NOW).startswith('UPLOADED')
    assert len(uploads) == 1


def test_late_render_is_not_published_immediately(setup):
    cfg, db, client, uploads = setup
    complete_trial(cfg, db, client); approve(db); cfg.enabled = True
    auto.tick(cfg, db, client, now=NOW)
    assert auto.tick(cfg, db, client, now=datetime(2026, 10, 30, 17, tzinfo=UTC)) == 'MISSED'
    assert len(uploads) == 1


def test_changed_assets_block_upload(setup):
    cfg, db, client, uploads = setup
    for _ in range(3):auto.tick(cfg, db, client, test=True, now=NOW)
    (auto.settings.assets_dir / 'backgrounds/room.png').write_bytes(b'changed')
    assert auto.tick(cfg, db, client, test=True, now=NOW) == 'ERROR'
    assert not uploads


def test_channel_mismatch_blocks_before_project_creation(setup, monkeypatch):
    cfg, db, client, uploads = setup
    monkeypatch.setattr(auto, 'channel', lambda **kw: ('UCwrong', 'Wrong channel'))
    with pytest.raises(ValueError, match='no coincidix'):
        auto.tick(cfg, db, client, test=True, now=NOW)
    assert db.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 0


def test_old_approval_cannot_authorize_a_different_channel(setup):
    cfg, db, client, uploads = setup
    complete_trial(cfg, db, client); approve(db)
    cfg.enabled = True; cfg.expected_channel_id = 'UCanother'
    with pytest.raises(ValueError, match='aprova'):
        auto.tick(cfg, db, client, now=NOW)


def test_slot_calendar_handles_dst_and_weekdays():
    cfg = auto.Config(scenes=[auto.Scene(theme='Bosc', title='Forest', background='x.png')], lead_hours=168)
    before = auto.slots(cfg, datetime(2026, 10, 23, 0, tzinfo=UTC))
    assert datetime(2026, 10, 23, 16, tzinfo=UTC) in before
    assert datetime(2026, 10, 26, 17, tzinfo=UTC) in before
    assert all(s.astimezone(auto.ZoneInfo('Europe/Madrid')).weekday() in [0, 2, 4] for s in before)
    assert len(before) == len(set(before))


def test_duplicate_worker_lock_rejected(tmp_path):
    with auto.locked_state(tmp_path) as db:
        with pytest.raises(RuntimeError, match='execució'):
            with auto.locked_state(tmp_path):pass


def test_credits_are_added_only_for_matching_catalog_audio(setup, monkeypatch):
    cfg, _, _, _ = setup
    path = auto.settings.assets_dir / 'music'; path.mkdir()
    audio = path / 'track.mp3'; audio.write_bytes(b'original')
    cfg.scenes[0].music = 'track.mp3'
    real_loads = json.loads
    def load(text, *args, **kwargs):
        result = real_loads(text, *args, **kwargs)
        if isinstance(result, list) and result and isinstance(result[0], dict) and 'download_url' in result[0]:
            return [{'file':'assets/music/track.mp3','sha256':auto.fingerprint(audio), 'title':'Track',
                     'author':'Author','license':'CC BY 4.0','source_url':'https://example.com/track','license_url':'https://creativecommons.org/licenses/by/4.0/'}]
        return result
    monkeypatch.setattr(auto.json, 'loads', load)
    draft, _ = auto.publication(cfg, cfg.scenes[0])
    assert 'Track — Author' in draft.description
    assert 'looped' in draft.description and 'fades applied' in draft.description


def test_unknown_audio_requires_manual_credits(setup):
    cfg, _, _, _ = setup
    (auto.settings.assets_dir / 'music').mkdir()
    (auto.settings.assets_dir / 'music/unknown.mp3').write_bytes(b'x')
    cfg.scenes[0].music = 'unknown.mp3'
    with pytest.raises(ValueError, match='crèdits'):
        auto.publication(cfg, cfg.scenes[0])


def test_path_traversal_is_rejected(setup):
    cfg, _, _, _ = setup
    cfg.scenes[0].background = '../room.png'
    with pytest.raises(ValueError):auto.publication(cfg, cfg.scenes[0])


def test_timer_installer_only_writes_user_units(tmp_path):
    import os
    import shutil
    import subprocess
    project = tmp_path / 'project with spaces'
    (project / 'scripts').mkdir(parents=True)
    (project / '.venv/bin').mkdir(parents=True)
    (project / 'data').mkdir()
    (project / 'data/automation.json').write_text('{}')
    python = project / '.venv/bin/python'; python.touch(); python.chmod(0o700)
    source = Path(__file__).resolve().parents[1] / 'scripts/install-automation-timer.sh'
    installer = project / 'scripts/install-automation-timer.sh'; shutil.copy2(source, installer)
    mock_bin = tmp_path / 'bin'; mock_bin.mkdir()
    command = mock_bin / 'systemctl'; command.write_text('#!/bin/sh\nexit 0\n'); command.chmod(0o700)
    config_home = tmp_path / 'config'
    env = dict(os.environ, PATH=str(mock_bin)+os.pathsep+os.environ['PATH'], XDG_CONFIG_HOME=str(config_home))
    result = subprocess.run(['bash', str(installer)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    service = (config_home / 'systemd/user/pomodoro-automation.service').read_text()
    assert f'WorkingDirectory="{project}"' in service
    assert f'ExecStart="{python}" -m app.automation tick' in service
    assert 'UMask=0077' in service
    timer = (config_home / 'systemd/user/pomodoro-automation.timer').read_text()
    assert 'OnUnitInactiveSec=5min' in timer


def test_long_upload_eligibility_is_checked(monkeypatch):
    class Call:
        def execute(self):return {'items':[{'id':'UCtest','snippet':{'title':'Test'},'status':{'longUploadsStatus':'eligible'}}]}
    class Channels:
        def list(self, **kwargs):
            assert kwargs == {'part':'id,snippet,status','mine':True}
            return Call()
    class Service:
        def channels(self):return Channels()
    monkeypatch.setattr(auto, 'credentials', lambda **kw: object())
    monkeypatch.setattr(auto, 'google_libraries', lambda: (None,None,None,lambda *a,**k:Service(),None))
    with pytest.raises(ValueError, match='15 minuts'):
        auto.channel(require_long_uploads=True)


def test_edited_day_list_is_validated():
    scene = auto.Scene(theme='Bosc', title='Forest', background='x.png')
    with pytest.raises(ValueError):auto.Config(scenes=[scene], weekdays=[0,0]).checked()
    with pytest.raises(ValueError):auto.Config(scenes=[scene], weekdays=[8]).checked()
