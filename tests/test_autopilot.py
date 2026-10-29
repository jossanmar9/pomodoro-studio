import random
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base
from app.models import AutoRun, Project, YouTubePublication
from app.services import autopilot as auto
from app.services.autopilot_plan import (
    AUTO_THEMES, ENVIRONMENTS, MAX_DESCRIPTION_BYTES, build_credits, build_music_mix_command, build_playlist,
    build_texts, choose_ambience, find_backgrounds, prompt_spec,
)
from app.services.ambience_prompt import build_prompt
from app.services.renderer import AudioTrack, RenderSpec, build_ffmpeg_command, build_timer_filters
from app.services.encoding import EncodingOptions, select_encoding
from app.services.thumbnail import fitting_fontsize
from app.services.timer import build_chapters, build_timeline
from app.themes import THEMES


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


# --- Decisions pures ---------------------------------------------------------

def test_every_auto_theme_is_a_known_theme_and_builds_an_original_prompt():
    for theme in AUTO_THEMES:
        assert theme in THEMES
        for environment in ENVIRONMENTS:
            prompt = build_prompt(prompt_spec(theme, environment))
            assert prompt.positive and "no people" in prompt.positive


def test_backgrounds_are_matched_by_theme_name(tmp_path):
    touch(tmp_path / "biblioteca-medieval-01.png")
    touch(tmp_path / "biblioteca-medieval-pluja-20261029.png")
    touch(tmp_path / "bosc-01.png")
    touch(tmp_path / "biblioteca-medieval-notes.txt")
    found = [p.name for p in find_backgrounds(tmp_path, "Biblioteca medieval")]
    assert found == ["biblioteca-medieval-01.png", "biblioteca-medieval-pluja-20261029.png"]
    assert find_backgrounds(tmp_path / "missing", "Bosc") == []


def test_ambience_picks_one_sound_per_layer_with_primary_louder(tmp_path):
    for name in ("pluja-terrassa", "pluja-pedra", "foc-llar"):
        touch(tmp_path / f"{name}.mp3")
    layers = choose_ambience(tmp_path, "pluja-llar", random.Random(3))
    assert len(layers) == 2
    assert layers[0].path.stem.startswith("pluja")
    assert layers[1].path.stem == "foc-llar"
    assert layers[0].loudness > layers[1].loudness


def test_ambience_skips_missing_optional_layers_but_fails_when_nothing_matches(tmp_path):
    touch(tmp_path / "pluja-pedra.mp3")
    assert [l.path.stem for l in choose_ambience(tmp_path, "pluja-llar", random.Random(0))] == ["pluja-pedra"]
    with pytest.raises(ValueError, match="Falten els sons"):
        choose_ambience(tmp_path, "mar", random.Random(0))
    assert choose_ambience(tmp_path, "musica", random.Random(0)) == []


def test_playlist_does_not_repeat_and_stops_when_video_is_covered(tmp_path):
    names = [f"peca-{i}.mp3" for i in range(6)]
    for name in names:
        touch(tmp_path / name)
    catalog = {name: {"duration_seconds": 600} for name in names}
    playlist = build_playlist(tmp_path, 1500, random.Random(1), catalog)
    assert len(playlist) == 3
    assert len(set(playlist)) == 3
    assert len(build_playlist(tmp_path, 10 * 3600, random.Random(1), catalog)) == 6


def test_music_mix_chains_crossfades():
    paths = [Path(f"/m/{i}.mp3") for i in range(3)]
    command = build_music_mix_command(paths, Path("/out/mix.m4a"))
    graph = command[command.index("-filter_complex") + 1]
    assert graph.count("loudnorm") == 3
    assert graph.count("acrossfade") == 2
    assert command[-1] == "/out/mix.m4a"
    single = build_music_mix_command(paths[:1], Path("/out/mix.m4a"))
    assert "acrossfade" not in single[single.index("-filter_complex") + 1]


def test_credits_include_author_license_and_source():
    catalog = {"song.mp3": {"title": "Calm", "author": "Ana", "license": "CC BY 4.0", "license_url": "https://cc/by", "source_url": "https://src"}}
    credits = build_credits([Path("song.mp3")], [Path("rain.mp3")], catalog)
    assert '"Calm" by Ana — CC BY 4.0 (https://cc/by) — https://src' in credits
    assert "Ambient sounds:" in credits and "rain" in credits
    compact = build_credits([Path("song.mp3")], [], catalog, compact=True)
    assert "(https://cc/by)" not in compact and "Licenses: CC BY 4.0 https://cc/by" in compact


def test_texts_fit_youtube_limits_even_for_eight_hours():
    chapters = build_chapters(build_timeline(25, 5, 480), "en")
    long_credits = "\n".join(f"• Track {i} by Someone — CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/) — https://example.org/{i}" for i in range(30))
    texts = build_texts(public_theme="Enchanted Wizard Library", environment="pluja-llar", duration=480, focus=25, pause=5,
                        chapters=chapters, credits=long_credits, compact_credits="Music: 30 tracks, CC BY 4.0")
    assert len(texts.title) <= 100
    assert "8 Hours" in texts.title and "Rain & Fireplace" in texts.title
    assert len(texts.description.encode("utf-8")) <= MAX_DESCRIPTION_BYTES
    assert "00:00:00 Focus session 1" in texts.description
    assert "The Amber Window" in texts.description
    assert fitting_fontsize(texts.thumbnail_text) < 68


def test_timer_labels_can_be_english_for_the_channel():
    timeline = build_timeline(1, 1, 3)
    english = build_timer_filters(timeline, "en")
    assert "FOCUS" in english and "BREAK" in english and "SESSION 1" in english
    assert "CONCENTRACI" not in english
    assert "CONCENTRACIÓ" in build_timer_filters(timeline)


def test_audio_tracks_can_be_loudness_normalised(tmp_path):
    spec = RenderSpec(touch(tmp_path / "bg.png"), tmp_path / "v.mp4", "1920x1080", build_timeline(1, 1, 2),
                      ambience=[AudioTrack(touch(tmp_path / "rain.mp3"), 1.0, -26)], music=AudioTrack(touch(tmp_path / "m.m4a"), 1.0))
    command = build_ffmpeg_command(spec, plan=select_encoding(EncodingOptions("cpu"), has_nvenc=False))
    graph = command[command.index("-filter_complex") + 1]
    assert graph.count("loudnorm=I=-26") == 1


# --- Procés complet amb tot simulat --------------------------------------------

@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    for module in (auto, main):
        monkeypatch.setattr(module, "SessionLocal", session)
    assets = tmp_path / "assets"
    touch(assets / "backgrounds" / "biblioteca-medieval-01.png")
    touch(assets / "ambience" / "pluja-terrassa.mp3")
    touch(assets / "music" / "calm.mp3")
    monkeypatch.setattr(auto.settings, "assets_dir", assets)
    monkeypatch.setattr(auto.settings, "output_dir", tmp_path / "output")
    monkeypatch.setattr(auto.settings, "audio_catalog", tmp_path / "missing-catalog.json")
    monkeypatch.setattr(auto, "forge_ready", lambda: False)
    monkeypatch.setattr(auto, "probe_duration", lambda path: 300.0, raising=False)
    monkeypatch.setattr("app.services.autopilot_plan.probe_duration", lambda path: 300.0)
    monkeypatch.setattr(auto, "prepare_music", lambda playlist, folder: touch(folder / "music-mix.m4a"))
    monkeypatch.setattr(auto, "generate_thumbnail", lambda bg, out, text, size: touch(out))
    monkeypatch.setattr(auto, "youtube_connected", lambda: True)
    monkeypatch.setattr(main, "youtube_connected", lambda: True)
    monkeypatch.setattr(main, "forge_ready", lambda: False)
    rendered = {}

    def fake_enqueue(project_id, spec):
        rendered["spec"] = spec
        touch(spec.output)
        with session() as db:
            db.get(Project, project_id).status = "COMPLETED"
            db.commit()
        auto.render_queue.jobs[project_id] = SimpleNamespace(status="COMPLETAT", error=None, progress=100.0, eta=0)

    monkeypatch.setattr(auto.render_queue, "enqueue", fake_enqueue)
    uploads = []
    monkeypatch.setattr(auto, "upload_video", lambda spec: uploads.append(spec) or "abc123")
    return SimpleNamespace(session=session, rendered=rendered, uploads=uploads, tmp=tmp_path)


def make_run(session, **overrides):
    data = dict(theme="Biblioteca medieval", environment="pluja", duration_minutes=60, focus_minutes=25, break_minutes=5, privacy="public", publish=1)
    data.update(overrides)
    with session() as db:
        run = AutoRun(**data)
        db.add(run)
        db.commit()
        return run.id


def test_full_run_renders_in_english_and_publishes(env):
    run_id = make_run(env.session)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
        assert run.step == "DONE", run.error
        assert run.video_id == "abc123"
        record = db.query(YouTubePublication).filter_by(project_id=run.project_id).one()
        assert record.status == "PUBLISHED" and record.privacy == "public"
    spec = env.rendered["spec"]
    assert spec.timer_language == "en"
    assert spec.ambience[0].loudness is not None and spec.music is not None
    upload = env.uploads[0]
    assert upload.privacy == "public"
    assert upload.description.count("00:00:00 Focus session 1") == 1
    assert "The Amber Window" in upload.description
    assert not (Path(spec.output).parent / "music-mix.m4a").exists()


def test_run_without_youtube_finishes_locally(env, monkeypatch):
    monkeypatch.setattr(auto, "youtube_connected", lambda: False)
    run_id = make_run(env.session)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
    assert run.step == "DONE_LOCAL" and "YouTube no està connectat" in run.message
    assert env.uploads == []


def test_run_fails_clearly_without_background(env):
    run_id = make_run(env.session, theme="Nau espacial")
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
        project = db.get(Project, run.project_id)
    assert run.step == "FAILED"
    assert "nau-espacial" in run.error and "Forge" in run.error
    assert project.status == "FAILED"


def test_home_page_and_form_create_a_run(env, monkeypatch):
    submitted = []
    monkeypatch.setattr(main.autopilot, "submit", submitted.append)
    with TestClient(main.app) as client:
        page = client.get("/")
        assert page.status_code == 200 and "Generar i publicar" in page.text
        assert client.get("/estudi").status_code == 200
        response = client.post("/auto", data={"theme": "Bosc", "environment": "bosc", "duration_minutes": "180", "pomodoro": "50/10", "privacy": "unlisted", "publish": "1"}, follow_redirects=False)
        assert response.status_code == 303
        assert client.post("/auto", data={"theme": "Personalitzada", "environment": "bosc", "duration_minutes": "60"}).status_code == 400
        status = client.get("/api/auto").json()
    assert len(submitted) == 1
    run = status["runs"][0]
    assert run["theme"] == "Bosc" and run["pomodoro"] == "50/10" and run["privacy"] == "unlisted" and run["step"] == "QUEUED"


def test_published_video_can_be_uploaded_again(env, monkeypatch):
    run_id = make_run(env.session)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
        folder = Path(db.get(Project, run.project_id).output_path)
    (folder / ".youtube-video-id").write_text("abc123\n", encoding="utf-8")
    submitted = []
    monkeypatch.setattr(main.autopilot, "submit_publish", submitted.append)
    with TestClient(main.app) as client:
        assert client.post(f"/auto/{run_id}/publish").status_code == 409
        response = client.post(f"/auto/{run_id}/publish", data={"again": "1"}, follow_redirects=False)
    assert response.status_code == 303
    assert submitted == [run_id]
    assert not (folder / ".youtube-video-id").exists()
    with env.session() as db:
        assert db.get(AutoRun, run_id).video_id is None
