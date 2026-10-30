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


def test_every_theme_has_free_font_files_with_licence():
    from app.services.fonts import THEME_FONTS, fonts_for_theme
    root = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    for theme in THEME_FONTS:
        assert theme in THEMES
        fonts = fonts_for_theme(theme, root=root)
        assert fonts.label and fonts.digits, theme
        for path in (fonts.label, fonts.digits):
            assert any((path.parent / name).is_file() for name in ("OFL.txt", "LICENSE.txt")), path
    assert fonts_for_theme("Personalitzada", root=root).label is None


def test_timer_uses_theme_fonts_and_fixed_colon():
    from app.services.fonts import ResolvedFonts
    fonts = ResolvedFonts(Path("/f/label.ttf"), Path("/f/digits.ttf"), uppercase_labels=False)
    filters = build_timer_filters(build_timeline(1, 1, 3), "en", fonts)
    assert "fontfile='/f/label.ttf'" in filters and "fontfile='/f/digits.ttf'" in filters
    assert "Focus" in filters and "FOCUS" not in filters
    assert filters.count("text='\\:'") == 1


def test_chimes_ring_at_every_change_but_not_at_the_end(tmp_path):
    from app.services.renderer import chime_times
    timeline = build_timeline(25, 5, 60)
    focus_end, break_end = chime_times(timeline)
    assert focus_end == [1_500_000, 3_300_000]
    assert break_end == [1_800_000]
    spec = RenderSpec(touch(tmp_path / "bg.png"), tmp_path / "v.mp4", "1920x1080", timeline,
                      ambience=[AudioTrack(touch(tmp_path / "rain.mp3"), 1.0, -30)], chime=True)
    command = build_ffmpeg_command(spec, plan=select_encoding(EncodingOptions("cpu"), has_nvenc=False))
    graph = command[command.index("-filter_complex") + 1]
    assert sum(1 for arg in command if arg.startswith("aevalsrc=")) == 2
    assert graph.count("adelay=") == 3 and "amix=inputs=4" in graph
    silent = RenderSpec(spec.background, spec.output, "1920x1080", build_timeline(1, 0, 1), chime=True)
    assert "-an" in build_ffmpeg_command(silent, plan=select_encoding(EncodingOptions("cpu"), has_nvenc=False))


def test_every_environment_sound_is_in_the_catalogue():
    from app.services.autopilot_plan import load_catalog
    catalog = load_catalog(Path(__file__).resolve().parent.parent / "assets" / "audio-catalog.json")
    stems = {Path(name).stem for name in catalog}
    for key, environment in ENVIRONMENTS.items():
        for layer in environment.layers:
            missing = [name for name in layer if name not in stems]
            assert not missing, (key, missing)
    for entry in catalog.values():
        assert entry["license"] in {"CC0 1.0", "CC BY 4.0"} and entry["download_url"].startswith("https://")


def test_level_and_listened_sample_are_reused(tmp_path):
    for name in ("pluja-terrassa", "pluja-pedra", "foc-llar", "foc-llar-04"):
        touch(tmp_path / f"{name}.mp3")
    for seed in range(5):
        layers = choose_ambience(tmp_path, "pluja-llar", random.Random(seed), level=-6, preferred=["pluja-pedra.mp3", "foc-llar-04.mp3"])
        assert [l.path.stem for l in layers] == ["pluja-pedra", "foc-llar-04"]
    assert layers[0].loudness == -36 and layers[1].loudness == -42
    with pytest.raises(ValueError):
        choose_ambience(tmp_path, "pluja", random.Random(0), level=99)


def test_preview_is_a_real_30_second_mp3(tmp_path):
    import subprocess
    from app.services.autopilot_plan import AmbienceLayer, build_preview_command
    rain = tmp_path / "rain.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "anoisesrc=d=5:c=pink:a=0.3", str(rain)], check=True)
    output = tmp_path / "preview.mp3"
    subprocess.run(build_preview_command([AmbienceLayer(rain, -30)], None, True, output), check=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(output)], capture_output=True, text=True, check=True)
    assert 29 <= float(probe.stdout) <= 31


def test_texts_for_every_format_fit_youtube():
    from app.services.autopilot_plan import NOISE_COLORS, plain_chapters
    chapters = plain_chapters(8 * 3600, 1800)
    for fmt, environment, noise in (("dormir", "pluja-llar", None), ("llegir", "llar", None), ("rol", "taverna", None), ("soroll", "soroll", "marro")):
        texts = build_texts(public_theme="Enchanted Wizard Library", environment=environment, duration=480, focus=480, pause=0,
                            chapters=chapters, credits="", fmt=fmt, noise=noise, dim=fmt != "rol", music=False)
        assert len(texts.title) <= 100, texts.title
        assert "Pomodoro" not in texts.title and "pomodoro" not in texts.tags
        assert len(texts.description.encode("utf-8")) <= MAX_DESCRIPTION_BYTES
        assert "00:00:00 Hour 1" in texts.description and "The Amber Window" in texts.description
        assert "\n\n\n" not in texts.description
    assert "Brown Noise" in build_texts(public_theme="Rainy Cabin", environment="soroll", duration=480, focus=480, pause=0, chapters=chapters, credits="", fmt="soroll", noise="marro", dim=True).title
    assert "Dark Screen" in build_texts(public_theme="Rainy Cabin", environment="pluja", duration=480, focus=480, pause=0, chapters=chapters, credits="", fmt="dormir", dim=True).title
    assert "Reading Ambience" in build_texts(public_theme="Cozy Reading Nook", environment="pluja", duration=120, focus=120, pause=0, chapters=chapters, credits="", fmt="llegir").title
    assert "Tabletop RPG" in build_texts(public_theme="Ancient Dungeon", environment="masmorra", duration=180, focus=180, pause=0, chapters=chapters, credits="", fmt="rol").title
    with pytest.raises(ValueError):
        build_texts(public_theme="x", environment="soroll", duration=60, focus=60, pause=0, chapters=chapters, credits="", fmt="soroll", noise="verd")


def test_plain_chapters_every_hour_with_dark_screen_mark():
    from app.services.autopilot_plan import plain_chapters
    assert plain_chapters(3 * 3600) == "00:00:00 Hour 1\n01:00:00 Hour 2\n02:00:00 Hour 3"
    assert plain_chapters(3600, 1800) == "00:00:00 Part 1\n00:15:00 Part 2\n00:30:00 Dark screen\n00:45:00 Part 4"


def test_render_without_timer_with_noise_and_dark_screen(tmp_path):
    spec = RenderSpec(touch(tmp_path / "bg.png"), tmp_path / "v.mp4", "1920x1080", build_timeline(120, 0, 120),
                      show_timer=False, dim_after=1800, noise="brown", noise_loudness=-26)
    command = build_ffmpeg_command(spec, plan=select_encoding(EncodingOptions("cpu"), has_nvenc=False))
    graph = command[command.index("-filter_complex") + 1]
    assert "drawtext" not in graph
    assert "fade=t=out:st=1800" in graph
    assert any(arg.startswith("anoisesrc=c=brown") for arg in command)
    assert "loudnorm=I=-26" in graph and "-an" not in command
    with pytest.raises(ValueError):
        build_ffmpeg_command(RenderSpec(spec.background, spec.output, "1920x1080", spec.timeline, noise="green"))


def test_real_noise_render_fades_to_black(tmp_path):
    import subprocess
    background = tmp_path / "bg.png"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0xc08040:s=320x180", "-frames:v", "1", str(background)], check=True)
    output = tmp_path / "noise.mp4"
    spec = RenderSpec(background, output, "320x180", build_timeline(1, 0, 1), show_timer=False, dim_after=5, noise="pink")
    command = build_ffmpeg_command(spec, plan=select_encoding(EncodingOptions("cpu", "fast"), has_nvenc=False))
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(output)], capture_output=True, text=True, check=True)
    assert 59 <= float(probe.stdout) <= 61
    def brightness(second):
        frame = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(second), "-i", str(output), "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
        return frame[0]
    assert brightness(1) > 60 and brightness(59.5) < 10
    volume = subprocess.run(["ffmpeg", "-nostats", "-ss", "10", "-t", "10", "-i", str(output), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
    assert "mean_volume" in volume and "-inf" not in volume.split("mean_volume")[1][:20]


def test_rpg_environments_and_themes_are_ready():
    from app.services.fonts import THEME_FONTS
    for key in ("masmorra", "campament", "tempesta-mar", "taverna"):
        assert key in ENVIRONMENTS
    for theme in ("Masmorra", "Campament d'aventurers", "Cova del drac"):
        assert theme in AUTO_THEMES and theme in THEMES and theme in THEME_FONTS
        assert "no people" in build_prompt(prompt_spec(theme, "soroll", "dormir")).positive


def test_motion_and_flicker_filters(tmp_path):
    from app.services.autopilot_plan import AmbienceLayer, has_fire
    spec = RenderSpec(touch(tmp_path / "bg.png"), tmp_path / "v.mp4", "1920x1080", build_timeline(25, 5, 60), motion=True, flicker=True)
    graph = build_ffmpeg_command(spec, plan=select_encoding(EncodingOptions("cpu"), has_nvenc=False))
    graph = graph[graph.index("-filter_complex") + 1]
    assert "scale=2034:1144" in graph and "crop=1920:1080:x=" in graph and "sin(2*PI*t/97)" in graph
    assert "eq=brightness=" in graph
    assert graph.index("crop=1920:1080:x=") < graph.index("drawtext")  # el comptador no es mou
    still = build_ffmpeg_command(RenderSpec(spec.background, spec.output, "1920x1080", spec.timeline))
    assert "sin(2*PI*t/97)" not in still[still.index("-filter_complex") + 1]
    video = RenderSpec(touch(tmp_path / "bg.mp4"), spec.output, "1920x1080", spec.timeline, motion=True)
    assert "sin(2*PI*t/97)" not in build_ffmpeg_command(video)[build_ffmpeg_command(video).index("-filter_complex") + 1]
    assert has_fire([AmbienceLayer(Path("pluja-pedra.mp3"), -30), AmbienceLayer(Path("foc-llar.mp3"), -36)])
    assert not has_fire([AmbienceLayer(Path("pluja-pedra.mp3"), -30)])


def test_real_render_with_motion_moves_the_picture(tmp_path):
    import subprocess
    background = tmp_path / "bg.png"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360", "-frames:v", "1", str(background)], check=True)
    output = tmp_path / "motion.mp4"
    spec = RenderSpec(background, output, "320x180", build_timeline(1, 0, 1), show_timer=False, motion=True, flicker=True, noise="pink")
    subprocess.run(build_ffmpeg_command(spec, plan=select_encoding(EncodingOptions("cpu", "fast"), has_nvenc=False)), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def frame(second):
        return subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(second), "-i", str(output), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    first, later = frame(1), frame(40)
    assert len(first) == len(later) == 320 * 180
    changed = sum(1 for a, b in zip(first, later) if abs(a - b) > 20)
    assert changed > len(first) * 0.05


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
    monkeypatch.setattr(auto, "generate_thumbnail", lambda bg, out, text, size, font=None: touch(out))
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
        assert run.published_at is not None
        record = db.query(YouTubePublication).filter_by(project_id=run.project_id).one()
        assert record.status == "PUBLISHED" and record.privacy == "public"
    spec = env.rendered["spec"]
    assert spec.timer_language == "en"
    assert spec.ambience[0].loudness is not None
    assert spec.music is None and spec.chime is True
    upload = env.uploads[0]
    assert upload.privacy == "public"
    assert upload.description.count("00:00:00 Focus session 1") == 1
    assert "The Amber Window" in upload.description
    assert "no music" in upload.description and "soft chime" in upload.description
    assert "Music:" not in upload.description


def test_noise_run_has_no_timer_no_ambience_and_dims(env):
    run_id = make_run(env.session, format="soroll", environment="soroll", noise="marro", dim=1, chime=1, duration_minutes=120)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
        assert run.step == "DONE", run.error
        project = db.get(Project, run.project_id)
        record = db.query(YouTubePublication).filter_by(project_id=run.project_id).one()
    spec = env.rendered["spec"]
    assert spec.noise == "brown" and spec.ambience == [] and spec.music is None
    assert spec.show_timer is False and spec.chime is False and spec.dim_after == 1800
    assert spec.motion is True and spec.flicker is False
    assert spec.timeline.total_seconds == 7200 and project.break_minutes == 0
    upload = env.uploads[0]
    assert "Brown Noise" in upload.title and "Dark Screen" in upload.title
    assert upload.category_id == "22" and record.category_id == "22"


def test_fire_scene_flickers_and_motion_can_be_turned_off(env):
    touch(auto.settings.assets_dir / "ambience" / "foc-llar.mp3")
    run_id = make_run(env.session, environment="llar")
    auto.execute(run_id, rng=random.Random(0))
    assert env.rendered["spec"].motion is True and env.rendered["spec"].flicker is True
    run_id = make_run(env.session, environment="llar", motion=0)
    auto.execute(run_id, rng=random.Random(0))
    assert env.rendered["spec"].motion is False and env.rendered["spec"].flicker is False


def test_sleep_and_rpg_runs_use_ambience_without_timer(env):
    for fmt, category in (("dormir", "22"), ("llegir", "22"), ("rol", "20")):
        run_id = make_run(env.session, format=fmt, environment="pluja", dim=1)
        auto.execute(run_id, rng=random.Random(0))
        with env.session() as db:
            assert db.get(AutoRun, run_id).step == "DONE"
        spec = env.rendered["spec"]
        assert spec.show_timer is False and spec.chime is False and spec.ambience and spec.noise is None
        assert (spec.dim_after == 1800) is (fmt == "dormir")
        assert env.uploads[-1].category_id == category


def test_run_with_music_mixes_a_playlist(env):
    run_id = make_run(env.session, music=1, chime=0)
    auto.execute(run_id, rng=random.Random(0))
    spec = env.rendered["spec"]
    assert spec.music is not None and spec.chime is False
    assert not (Path(spec.output).parent / "music-mix.m4a").exists()
    assert "Music:" in env.uploads[0].description


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


def test_preview_endpoint_returns_playable_audio(env, monkeypatch):
    import subprocess
    rain = auto.settings.assets_dir / "ambience" / "pluja-terrassa.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anoisesrc=d=5:c=pink:a=0.3", str(rain)], check=True)
    monkeypatch.chdir(env.tmp)
    with TestClient(main.app) as client:
        response = client.post("/api/auto/preview", data={"environment": "pluja", "ambience_level": "0", "chime": "1"})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["files"] == ["pluja-terrassa.mp3"]
        audio = client.get(data["url"])
        assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg"
        assert client.get("/api/auto/preview/../../etc/passwd").status_code == 404
        assert client.post("/api/auto/preview", data={"environment": "mar"}).status_code == 409


def test_noise_form_and_preview(env, monkeypatch):
    submitted = []
    monkeypatch.setattr(main.autopilot, "submit", submitted.append)
    with TestClient(main.app) as client:
        assert "Soroll de color" in client.get("/").text
        response = client.post("/auto", data={"format": "soroll", "theme": "Bosc", "noise": "rosa", "duration_minutes": "480", "dim": "1", "chime": "1"}, follow_redirects=False)
        assert response.status_code == 303
        assert client.post("/auto", data={"format": "soroll", "theme": "Bosc", "noise": "verd", "duration_minutes": "60"}).status_code == 400
        assert client.post("/auto", data={"format": "tik-tok", "theme": "Bosc", "environment": "bosc", "duration_minutes": "60"}).status_code == 400
        monkeypatch.chdir(env.tmp)  # les mostres es guarden en data/ de la carpeta de proves
        preview = client.post("/api/auto/preview", data={"format": "soroll", "noise": "marro"})
        assert preview.status_code == 200, preview.text
        assert preview.json()["files"] == [] and preview.json()["sounds"] == ["Soroll marró"]
        status = client.get("/api/auto").json()
    with env.session() as db:
        run = db.get(AutoRun, status["runs"][0]["id"])
    assert run.format == "soroll" and run.noise == "rosa" and run.dim == 1 and run.chime == 0 and run.environment == "soroll"
    assert run.motion == 0  # la casella no s'ha enviat
    assert status["runs"][0]["environment_label"] == "Soroll rosa"


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
    with env.session() as db:
        saved = db.get(AutoRun, run["id"])
    assert saved.music == 0 and saved.chime == 0


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
