import random
import subprocess
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
from app.services.text_variants import SHORT_PHRASES
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
        url = entry["source_url"] if entry.get("manual") else entry["download_url"]  # les manuals es baixen a mà des de la seua pàgina
        assert entry["license"] in {"CC0 1.0", "CC BY 4.0"} and url.startswith("https://")


def test_level_and_listened_sample_are_reused(tmp_path):
    for name in ("pluja-terrassa", "pluja-pedra", "foc-llar", "foc-llar-04"):
        touch(tmp_path / f"{name}.mp3")
    for seed in range(5):
        layers = choose_ambience(tmp_path, "pluja-llar", random.Random(seed), level=-6, preferred=["pluja-pedra.mp3", "foc-llar-04.mp3"])
        assert [l.path.stem for l in layers] == ["pluja-pedra", "foc-llar-04"]
    assert layers[0].loudness == -46 and layers[1].loudness == -53
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
    for fmt, environment, noise in (("dormir", "pluja-llar", None), ("llegir", "llar", None), ("ambient", "platja-tempesta", None), ("rol", "taverna", None), ("soroll", "soroll", "marro")):
        texts = build_texts(public_theme="Enchanted Wizard Library", environment=environment, duration=480, focus=480, pause=0,
                            chapters=chapters, credits="", fmt=fmt, noise=noise, dim=fmt != "rol", music=False)
        assert len(texts.title) <= 100, texts.title
        assert "Pomodoro" not in texts.title and "pomodoro" not in texts.tags
        assert len(texts.description.encode("utf-8")) <= MAX_DESCRIPTION_BYTES
        assert "00:00:00 Hour 1" in texts.description and "The Amber Window" in texts.description
        assert "\n\n\n" not in texts.description
    assert "Brown Noise" in build_texts(public_theme="Rainy Cabin", environment="soroll", duration=480, focus=480, pause=0, chapters=chapters, credits="", fmt="soroll", noise="marro", dim=True).title
    assert "Dark Screen" in build_texts(public_theme="Rainy Cabin", environment="pluja", duration=480, focus=480, pause=0, chapters=chapters, credits="", fmt="dormir", dim=True).title
    assert "Reading" in build_texts(public_theme="Cozy Reading Nook", environment="pluja", duration=120, focus=120, pause=0, chapters=chapters, credits="", fmt="llegir").title
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
    monkeypatch.setattr(auto.settings, "overlays_dir", tmp_path / "overlays")
    monkeypatch.setattr(auto.settings, "audio_catalog", tmp_path / "missing-catalog.json")
    monkeypatch.setattr(auto, "probe_duration", lambda path: 300.0, raising=False)
    monkeypatch.setattr("app.services.autopilot_plan.probe_duration", lambda path: 300.0)
    monkeypatch.setattr(auto, "prepare_music", lambda playlist, folder, level=0: touch(folder / "music-mix.m4a"))
    monkeypatch.setattr(auto, "ensure_overlay", lambda style, **kw: touch(tmp_path / "overlays" / f"{style}.mp4"))
    monkeypatch.setattr(auto, "ensure_breath_clip", lambda pattern, **kw: touch(tmp_path / "overlays" / f"respiracio-{pattern}.mp4"))
    monkeypatch.setattr(auto, "ensure_breath_intro", lambda **kw: touch(tmp_path / "overlays" / "respiracio-intro.mp4"))
    monkeypatch.setattr(auto, "generate_thumbnail", lambda bg, out, text, size, font=None: touch(out))
    monkeypatch.setattr(auto, "make_thumbnail", lambda bg, out, title, subtitle="", **kw: touch(out))
    monkeypatch.setattr(auto, "can_manage_playlists", lambda: True)
    playlists = []
    monkeypatch.setattr(auto, "add_to_playlists", lambda video_id, wanted: playlists.append((video_id, wanted)) or [t for t, _ in wanted])
    monkeypatch.setattr(main, "can_manage_playlists", lambda: True)
    monkeypatch.setattr(main, "view_counts", lambda ids: {})
    monkeypatch.setattr(auto, "check_video", lambda video, seconds, **kw: [])
    monkeypatch.setattr(main, "refresh_views_in_background", lambda *a, **k: None)
    monkeypatch.setattr(main.autopilot, "submit_pending_reels", lambda: None)
    monkeypatch.setattr(main.settings, "youtube_stats_file", tmp_path / "stats.json")
    monkeypatch.setattr(auto, "youtube_connected", lambda: True)
    monkeypatch.setattr(main, "youtube_connected", lambda: True)
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
    return SimpleNamespace(session=session, rendered=rendered, uploads=uploads, tmp=tmp_path, playlists=playlists)


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
    assert spec.motion is False and spec.flicker is False and spec.overlay is None
    assert spec.background.name.startswith("soroll-marro-color") and spec.pulse is False and spec.intro_text is None
    assert spec.timeline.total_seconds == 7200 and project.break_minutes == 0
    upload = env.uploads[0]
    assert "Brown Noise" in upload.title and "Dark Screen" in upload.title
    assert upload.category_id == "22" and record.category_id == "22"


def test_noise_screen_can_be_black_or_breathe(env):
    run_id = make_run(env.session, theme="Soroll de color", format="soroll", environment="soroll", noise="rosa", noise_screen="negre", noise_pulse=1, duration_minutes=60)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        assert db.get(AutoRun, run_id).step == "DONE", db.get(AutoRun, run_id).error
    spec = env.rendered["spec"]
    assert spec.background.name.startswith("soroll-rosa-negre") and spec.pulse is False and spec.intro_text == "Pink Noise"
    assert "Black Screen" in env.uploads[-1].title and "black screen" in env.uploads[-1].tags
    run_id = make_run(env.session, theme="Soroll de color", format="soroll", environment="soroll", noise="blanc", noise_screen="color", noise_pulse=1, duration_minutes=60)
    auto.execute(run_id, rng=random.Random(0))
    assert env.rendered["spec"].pulse is True and env.rendered["spec"].intro_text is None


def test_noise_backgrounds_and_pulse_render(tmp_path):
    from PIL import Image
    from app.services.noise_screen import make_noise_background
    colour = make_noise_background("marro", "color", tmp_path / "c.png", width=64, height=36, text="Brown Noise")
    black = make_noise_background("marro", "negre", tmp_path / "n.png", width=64, height=36)
    assert Image.open(colour).getpixel((32, 4)) != (0, 0, 0) and Image.open(black).getextrema() == ((0, 0), (0, 0), (0, 0))
    with pytest.raises(ValueError):
        make_noise_background("verd", "color", tmp_path / "x.png", width=64, height=36)
    output = tmp_path / "out.mp4"
    spec = RenderSpec(colour, output, "64x36", build_timeline(1, 0, 1), fps=5, show_timer=False, noise="brown", pulse=True, intro_text="Brown Noise")
    command = build_ffmpeg_command(spec, plan=select_encoding(EncodingOptions("cpu"), has_nvenc=False))
    assert "eval=frame" in " ".join(command) and "Brown Noise" in " ".join(command)
    command[command.index("-t") + 1] = "3"
    subprocess.run(command, check=True, capture_output=True)
    assert output.stat().st_size > 0


def test_natural_overlay_replaces_camera_motion_and_can_be_turned_off(env):
    touch(auto.settings.assets_dir / "ambience" / "foc-llar.mp3")
    run_id = make_run(env.session)
    auto.execute(run_id, rng=random.Random(0))
    spec = env.rendered["spec"]
    assert spec.motion is False and spec.flicker is False and spec.overlay.name == "pols.mp4" and spec.overlay_opacity > 0
    run_id = make_run(env.session, environment="llar", motion=0)
    auto.execute(run_id, rng=random.Random(0))
    assert env.rendered["spec"].overlay is None


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
    run_id = make_run(env.session, theme="Observatori")
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
        project = db.get(Project, run.project_id)
    assert run.step == "FAILED"
    assert "observatori" in run.error and "Biblioteca de fons" in run.error
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
        assert client.post("/auto", data={"format": "soroll", "noise": "rosa", "noise_screen": "groc", "duration_minutes": "60"}).status_code == 400
        assert client.post("/auto", data={"format": "tik-tok", "theme": "Bosc", "environment": "bosc", "duration_minutes": "60"}).status_code == 400
        monkeypatch.chdir(env.tmp)  # les mostres es guarden en data/ de la carpeta de proves
        preview = client.post("/api/auto/preview", data={"format": "soroll", "noise": "marro"})
        assert preview.status_code == 200, preview.text
        assert preview.json()["files"] == [] and preview.json()["sounds"] == ["Soroll marró"]
        status = client.get("/api/auto").json()
    with env.session() as db:
        run = db.get(AutoRun, status["runs"][0]["id"])
    assert run.format == "soroll" and run.noise == "rosa" and run.dim == 1 and run.chime == 0 and run.environment == "soroll"
    assert run.theme == "Soroll de color" and run.background is None and run.noise_screen == "color" and run.noise_pulse == 0
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


def test_chosen_background_is_used(env, monkeypatch):
    monkeypatch.setattr(main.autopilot, "submit", lambda run_id: None)
    with TestClient(main.app) as client:
        assert "biblioteca-medieval-01.png" in client.get("/").text
        base = {"theme": "Biblioteca medieval", "environment": "pluja", "duration_minutes": "60", "publish": "1"}
        assert client.post("/auto", data=base | {"background": "../secret.png"}).status_code == 400
        assert client.post("/auto", data=base | {"background": "bosc-01.png"}).status_code == 400
        assert client.post("/auto", data=base | {"background": "biblioteca-medieval-01.png"}, follow_redirects=False).status_code == 303
    with env.session() as db:
        run_id = db.query(AutoRun).order_by(AutoRun.id.desc()).first().id
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
    assert run.step == "DONE" and run.background == "biblioteca-medieval-01.png" and "Fons triat a mà" in run.message


def test_music_style_follows_format_and_environment(tmp_path):
    from app.services.autopilot_plan import MUSIC_STYLES, load_catalog, music_style, music_tracks, track_style
    assert music_style("pomodoro", "pluja") == "calma"
    assert music_style("pomodoro", "cafeteria") == "jazz" and music_style("llegir", "japo-carrer") == "jazz"
    assert music_style("pomodoro", "taverna") == "medieval" and music_style("rol", "bosc") == "medieval"
    assert music_style("rol", "masmorra") == "fosca" and music_style("rol", "tempesta") == "fosca"
    assert music_style("dormir", "taverna") == "calma"
    assert music_style("pomodoro", "llar", "Nadal") == "nadal" and music_style("dormir", "hivern", "Nadal") == "nadal"
    assert music_style("rol", "taverna", "Nadal") == "medieval"
    for name in ("healing.mp3", "jazz-lobby-time.mp3", "medieval-folk-round.mp3", "fosca-moorland.mp3"):
        touch(tmp_path / name)
    assert [p.name for p in music_tracks(tmp_path, "jazz")] == ["jazz-lobby-time.mp3"]
    assert [p.name for p in music_tracks(tmp_path, "calma")] == ["healing.mp3"]
    assert track_style(tmp_path / "x.mp3", {"x.mp3": {"style": "medieval"}}) == "medieval"
    catalog = load_catalog(Path(__file__).resolve().parent.parent / "assets" / "audio-catalog.json")
    music = [e for e in catalog.values() if e["kind"] == "music"]
    for style in MUSIC_STYLES:
        assert sum(e.get("style") == style for e in music) >= 7, style  # lo-fi: 9 peces CC0 de HoliznaCC0
    texts = build_texts(public_theme="Medieval Tavern", environment="taverna", duration=120, focus=120, pause=0, chapters="00:00:00 Hour 1", credits="", fmt="rol", music=True, style="medieval")
    assert "medieval folk music" in texts.description


def test_run_uses_the_style_of_the_environment_or_falls_back(env):
    touch(env.tmp / "assets" / "music" / "jazz-lobby-time.mp3")
    for name in ("cafeteria-capucins", "restaurant-brunch-02", "foc-llar"):
        touch(env.tmp / "assets" / "ambience" / f"{name}.mp3")
    run_id = make_run(env.session, music=1, environment="cafeteria")
    auto.execute(run_id, rng=random.Random(0))
    assert "soft jazz" in env.uploads[-1].description and '"calm"' not in env.uploads[-1].description
    run_id = make_run(env.session, music=1, environment="taverna")
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
    assert run.step == "DONE" and "Encara no tens música medieval" in run.message


def test_new_environments_have_their_own_sounds():
    assert "pluja-lona" not in [n for layer in ENVIRONMENTS["pluja"].layers for n in layer]
    for key in ("pluja-bosc", "pluja-finestra", "cova", "hivern", "temporal", "tren", "rellotge"):
        assert ENVIRONMENTS[key].layers, key
    assert any(n.startswith("foc-foguera") for layer in ENVIRONMENTS["campament"].layers for n in layer)
    assert any(n.startswith("cova-") for layer in ENVIRONMENTS["masmorra"].layers for n in layer)
    assert "restaurant-pizzeria" not in [n for layer in ENVIRONMENTS["taverna"].layers for n in layer]


def test_overlay_style_depends_on_theme_and_environment():
    from app.services.overlays import overlay_style
    assert overlay_style("Parc a la ciutat", "pluja-ciutat") == "pluja"
    assert overlay_style("Bosc", "tempesta") == "pluja-forta"
    assert overlay_style("Campament d'aventurers", "campament") == "guspires"
    assert overlay_style("Bosc", "hivern") == "neu"
    assert overlay_style("Biblioteca medieval", "pluja") == "pols"  # dins no plou
    assert overlay_style("Avió", "nit") is None


def test_overlay_loops_seamlessly_and_renders(tmp_path):
    from app.services import overlays
    for style in overlays.STYLES:
        particles = overlays._particles(style, 96, 54, random.Random(1))
        first = overlays.render_frame(style, particles, 96, 54, 0.0).tobytes()
        assert first == overlays.render_frame(style, particles, 96, 54, 1.0).tobytes(), style
        assert first != overlays.render_frame(style, particles, 96, 54, 0.5).tobytes(), style
    custom = touch(tmp_path / "custom" / "neu-pexels.mp4")
    assert overlays.ensure_overlay("neu", cache_dir=tmp_path / "cache", custom_dir=tmp_path / "custom", width=64, height=36, fps=5) == custom
    path = overlays.ensure_overlay("pluja", cache_dir=tmp_path / "cache", custom_dir=tmp_path / "custom", width=64, height=36, fps=5)
    assert path.is_file() and path.stat().st_size > 0
    background = tmp_path / "bg.png"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x334455:s=64x36", "-frames:v", "1", str(background)], check=True)
    output = tmp_path / "out.mp4"
    spec = RenderSpec(background, output, "64x36", build_timeline(1, 0, 1), fps=5, show_timer=False, overlay=path, overlay_opacity=0.7)
    command = build_ffmpeg_command(spec, plan=select_encoding(EncodingOptions("cpu"), has_nvenc=False))
    command[command.index("-t") + 1] = "2"
    subprocess.run(command, check=True, capture_output=True)
    assert output.is_file() and output.stat().st_size > 0


def test_ambient_runs_have_no_music_and_the_plane_uses_generated_noise(env):
    touch(env.tmp / "assets" / "backgrounds" / "avio-01.png")
    run_id = make_run(env.session, theme="Avió", environment="avio", format="ambient", music=1, chime=1)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        assert db.get(AutoRun, run_id).step == "DONE", db.get(AutoRun, run_id).error
    spec = env.rendered["spec"]
    assert spec.noise == "brown" and spec.music is None and spec.show_timer is False and spec.chime is False and spec.overlay is None
    upload = env.uploads[-1]
    assert "Airplane Cabin" in upload.title and "No Music" in upload.title and upload.category_id == "22"
    run_id = make_run(env.session, format="ambient", environment="pluja", music=1)
    auto.execute(run_id, rng=random.Random(0))
    assert env.rendered["spec"].music is None and env.rendered["spec"].noise is None


def test_new_ambient_themes_are_ready():
    from app.services.fonts import THEME_FONTS
    from app.services.overlays import overlay_style
    for theme in ("Avió", "Tren", "Platja", "Riu", "Hivernacle", "Port", "Hivern"):
        assert theme in AUTO_THEMES and theme in THEMES and theme in THEME_FONTS
    for key in ("bosc-tempesta", "platja-tempesta", "riu", "llar-tempesta", "biblioteca", "port", "avio"):
        assert key in ENVIRONMENTS
    assert overlay_style("Platja", "platja-tempesta") == "pluja-forta" and overlay_style("Avió", "avio") is None


def test_breathing_cycle_loops_and_follows_the_pattern():
    from app.services import breathing
    assert breathing.cycle_seconds("quadrada") == 16 and breathing.cycle_seconds("478") == 19
    assert breathing.state("quadrada", 0)[:2] == ("inhale", 0.0)
    assert breathing.state("quadrada", 5) == ("hold", 1.0, 3)
    assert breathing.state("478", 12)[0] == "exhale" and breathing.state("478", 18.9)[1] < 0.01
    first = breathing.render_frame("coherent", 0, 96, 54).tobytes()
    assert first == breathing.render_frame("coherent", 10, 96, 54).tobytes()
    assert first != breathing.render_frame("coherent", 5, 96, 54).tobytes()


def test_breathing_run_uses_the_circle_and_its_own_durations(env, monkeypatch):
    run_id = make_run(env.session, format="respiracio", breath="478", duration_minutes=10, environment="pluja")
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        assert db.get(AutoRun, run_id).step == "DONE", db.get(AutoRun, run_id).error
    spec = env.rendered["spec"]
    assert spec.overlay.name == "respiracio-478.mp4" and spec.overlay_intro.name == "respiracio-intro.mp4"
    assert spec.darken > 0 and spec.show_timer is False
    assert spec.timeline.total_seconds == 600
    upload = env.uploads[-1]
    assert "10 Minute 4-7-8 Breathing" in upload.title and upload.category_id == "26"
    monkeypatch.setattr(main.autopilot, "submit", lambda run_id: None)
    with TestClient(main.app) as client:
        assert "Respiració guiada" in client.get("/").text
        base = {"theme": "Bosc", "environment": "bosc", "format": "respiracio"}
        assert client.post("/auto", data=base | {"breath": "quadrada", "duration_minutes": "120"}).status_code == 400
        assert client.post("/auto", data=base | {"breath": "inventada", "duration_minutes": "10"}).status_code == 400
        assert client.post("/auto", data=base | {"breath": "quadrada", "duration_minutes": "10", "publish": "1", "shorts": "1"}, follow_redirects=False).status_code == 303
    with env.session() as db:
        saved = db.query(AutoRun).order_by(AutoRun.id.desc()).first()
    assert saved.breath == "quadrada" and saved.duration_minutes == 10 and saved.shorts == 1


def test_short_is_published_after_the_video(env, monkeypatch):
    touch(env.tmp / "assets" / "backgrounds" / "biblioteca-medieval-01.png")
    monkeypatch.setattr(auto, "build_short_command", lambda bg, video, output, **kw: ["bash", "-c", f"touch '{output}'"])
    run_id = make_run(env.session, shorts=1)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
    assert run.step == "DONE" and run.short_video_id == "abc123"
    main_upload, short_upload = env.uploads[-2:]
    assert short_upload.title.endswith("#shorts") and "https://youtu.be/abc123" in short_upload.description
    assert short_upload.video.name == "short.mp4" and short_upload.privacy == main_upload.privacy


def test_short_failure_does_not_undo_the_published_video(env, monkeypatch):
    monkeypatch.setattr(auto, "build_short_command", lambda bg, video, output, **kw: ["bash", "-c", "exit 1"])
    run_id = make_run(env.session, shorts=1)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
    assert run.step == "DONE" and run.video_id == "abc123" and run.short_video_id is None and "Short no fet" in run.message


def test_short_command_renders_a_vertical_clip(tmp_path):
    from app.services.shorts import build_short_command
    background = tmp_path / "bg.png"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x445566:s=320x180", "-frames:v", "1", str(background)], check=True)
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "anoisesrc=d=8", "-f", "lavfi", "-i", "color=black:s=64x36:d=8", "-shortest", str(video)], check=True)
    output = tmp_path / "short.mp4"
    subprocess.run(build_short_command(background, video, output, title="Christmas Library", subtitle="2 Hours · Rain", start=1, seconds=4), check=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(output)], capture_output=True, text=True, check=True)
    assert probe.stdout.strip() == "1080,1920"


def test_christmas_themes_are_ready():
    from app.services.fonts import THEME_FONTS
    from app.services.overlays import overlay_style
    assert "Nadal" in AUTO_THEMES and "Nadal" in THEMES and "Nadal" in THEME_FONTS and "Christmas" in THEMES["Nadal"]
    assert overlay_style("Nadal", "nit", Path("poble-nevat-nit-temporada.png")) == "neu"
    assert overlay_style("Nadal", "llar", Path("cabana-de-nadal-llar-temporada.png")) == "pols"


def test_channel_short_is_made_alone_and_links_to_the_channel(env, monkeypatch):
    monkeypatch.setattr(auto, "build_preview_command", lambda ambience, track, chime, output, **kw: ["bash", "-c", f"touch '{output}'"])
    monkeypatch.setattr(auto, "build_short_command", lambda bg, audio, output, **kw: ["bash", "-c", f"touch '{output}'"] if kw.get("footer") != "Full video on the channel" else pytest.fail("footer"))
    run_id = make_run(env.session, format="short", duration_minutes=1)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
    assert run.step == "DONE", run.error
    assert "spec" not in env.rendered  # no hi ha vídeo llarg
    upload = env.uploads[-1]
    assert upload.video.name == "short.mp4" and upload.title.endswith("#shorts")
    assert "https://www.youtube.com/@TheAmberWindow" in upload.description and "youtu.be" not in upload.description
    assert run.video_id == run.short_video_id == "abc123"
    monkeypatch.setattr(main.autopilot, "submit", lambda run_id: None)
    with TestClient(main.app) as client:
        assert "Només un Short" in client.get("/").text
        response = client.post("/auto", data={"format": "short", "theme": "Bosc", "environment": "bosc", "duration_minutes": "120", "shorts": "1", "publish": "1"}, follow_redirects=False)
        assert response.status_code == 303
    with env.session() as db:
        saved = db.query(AutoRun).order_by(AutoRun.id.desc()).first()
    assert saved.format == "short" and saved.duration_minutes == 1 and saved.shorts == 0


def test_queued_and_running_videos_can_be_cancelled(env, monkeypatch):
    queued = make_run(env.session)
    runner = auto.AutopilotRunner()
    runner._queue = [("run", queued)]
    assert runner.cancel(queued) is True and runner._queue == []
    with env.session() as db:
        assert db.get(AutoRun, queued).step == "CANCELLED"
    assert runner.cancel(queued) is False  # ja no està actiu

    running = make_run(env.session)
    runner._current = running
    monkeypatch.setattr(auto.render_queue, "cancel", lambda project_id: True)
    assert runner.cancel(running) is True and auto.is_cancelled(running)
    auto.execute(running, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, running)
    assert run.step == "CANCELLED" and run.error is None and "Cancel·lat" in run.message
    assert not auto.is_cancelled(running) and env.uploads == []


def test_cancel_endpoint(env, monkeypatch):
    done = make_run(env.session, step="DONE", video_id="x")
    waiting = make_run(env.session)
    monkeypatch.setattr(main.autopilot, "submit", lambda run_id: None)
    with TestClient(main.app) as client:
        assert client.post(f"/auto/{done}/cancel").status_code == 409
        assert client.post(f"/auto/{waiting}/cancel").json() == {"cancelled": True}
        assert client.get("/api/auto").json()["runs"][0]["step_label"] == "Cancel·lat"


def test_deep_work_rhythms_and_ten_hours():
    from app.services.autopilot_plan import DURATION_CHOICES, POMODORO_CHOICES
    assert 600 in DURATION_CHOICES and POMODORO_CHOICES["52/17"] == (52, 17) and POMODORO_CHOICES["90/15"] == (90, 15)
    chapters = build_chapters(build_timeline(90, 15, 600), language="en")
    texts = build_texts(public_theme="Rainy Library", environment="pluja", duration=600, focus=90, pause=15, chapters=chapters, credits="")
    assert "10 Hours Deep Work 90/15" in texts.title and texts.title.startswith("Cozy Rainy Library Ambience") and "deep work" in texts.tags
    assert len(texts.description.encode("utf-8")) <= MAX_DESCRIPTION_BYTES
    sleep = build_texts(public_theme="Rainy Cabin", environment="pluja", duration=600, focus=600, pause=0,
                        chapters=__import__("app.services.autopilot_plan", fromlist=["x"]).plain_chapters(36000, 1800), credits="", fmt="dormir", dim=True)
    assert "10 Hours" in sleep.title and "Hour 10" in sleep.description
    classic = build_texts(public_theme="Rainy Library", environment="pluja", duration=120, focus=25, pause=5, chapters="", credits="")
    assert "Pomodoro 25/5" in classic.title and "deep work" not in classic.tags


def test_environments_are_listed_alphabetically():
    from app.services.autopilot_plan import environments_by_label, sort_key
    labels = [env.label for _, env in environments_by_label()]
    assert labels == sorted(labels, key=sort_key) and len(labels) == len(ENVIRONMENTS)
    assert labels.index("Cabina d'avió") < labels.index("Cafeteria plena") < labels.index("Cova amb goteig")


def test_missing_short_can_be_made_afterwards(env, monkeypatch):
    touch(env.tmp / "assets" / "backgrounds" / "biblioteca-medieval-01.png")
    monkeypatch.setattr(auto, "build_short_command", lambda bg, video, output, **kw: ["bash", "-c", f"touch '{output}'"])
    run_id = make_run(env.session, shorts=0)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
        run.shorts, run.short_video_id = 1, run.video_id  # com quedava abans de la correcció
        db.commit()
        assert auto.short_missing(run)
    ids = iter(["short999"])
    monkeypatch.setattr(auto, "upload_video", lambda spec: env.uploads.append(spec) or next(ids))
    auto._make_missing_short(run_id)
    with env.session() as db:
        run = db.get(AutoRun, run_id)
        assert run.short_video_id == "short999" and not auto.short_missing(run) and "Short publicat" in run.message
    assert env.uploads[-1].video.name == "short.mp4"


def test_breathing_starts_with_a_preparation_and_countdown(tmp_path):
    from app.services import breathing
    assert breathing.INTRO_SECONDS == 15
    settle = breathing.render_intro_frame(2, 96, 54).tobytes()
    assert settle != breathing.render_intro_frame(12, 96, 54).tobytes()
    assert breathing.render_intro_frame(11.2, 96, 54).tobytes() != breathing.render_intro_frame(12.2, 96, 54).tobytes()  # 4 → 3
    intro = breathing.ensure_breath_intro(cache_dir=tmp_path, width=64, height=36, fps=5)
    loop = breathing.ensure_breath_clip("coherent", cache_dir=tmp_path, width=64, height=36, fps=5)
    background = tmp_path / "bg.png"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x445566:s=64x36", "-frames:v", "1", str(background)], check=True)
    output = tmp_path / "out.mp4"
    spec = RenderSpec(background, output, "64x36", build_timeline(1, 0, 1), fps=5, show_timer=False, overlay=loop, overlay_intro=intro, overlay_opacity=0.9, darken=0.2)
    command = build_ffmpeg_command(spec, plan=select_encoding(EncodingOptions("cpu"), has_nvenc=False))
    assert "concat=n=2:v=1:a=0" in " ".join(command)
    command[command.index("-t") + 1] = "30"
    subprocess.run(command, check=True, capture_output=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(output)], capture_output=True, text=True, check=True)
    assert float(probe.stdout) >= 29


def test_titles_lead_with_cozy_ambience_for_search():
    from app.services.autopilot_plan import cozy_name
    assert cozy_name("Rainy Library") == "Cozy Rainy Library" and cozy_name("Cozy Reading Nook") == "Cozy Reading Nook"
    chapters = "00:00:00 Hour 1"
    for fmt in ("pomodoro", "dormir", "llegir", "ambient"):
        texts = build_texts(public_theme="Christmas Library", environment="llar", duration=120, focus=25, pause=5, chapters=chapters, credits="", fmt=fmt)
        assert texts.title.startswith("Cozy Christmas Library"), texts.title
        assert texts.description.startswith("Cozy Christmas Library"), texts.description[:80]
        assert "cozy ambience" in texts.tags and "#cozyambience" in texts.description


def test_reading_title_does_not_repeat_reading():
    texts = build_texts(public_theme="Cozy Reading Nook", environment="pluja", duration=120, focus=120, pause=0, chapters="", credits="", fmt="llegir")
    assert texts.title.startswith("Cozy Reading Nook Ambience |") and "Reading Ambience" not in texts.title.split("|")[0].replace("Nook Ambience", "")


def test_seasonal_themes_have_their_effects_music_and_sounds():
    from app.services.autopilot_plan import music_advice, music_style
    from app.services.fonts import THEME_FONTS
    from app.services.overlays import overlay_mode, overlay_style
    for theme in ("Estiu", "Tardor", "Primavera", "Hivern", "Nadal", "Halloween", "Pasqua"):
        assert theme in AUTO_THEMES and theme in THEMES and theme in THEME_FONTS, theme
    for removed in ("Nau espacial", "Cabana de Nadal", "Porxo d'estiu", "Bosc de tardor"):
        assert removed not in AUTO_THEMES
    assert overlay_style("Tardor", "tardor", Path("bosc-de-tardor-tardor-temporada.png")) == "fulles" and overlay_mode("fulles") == "key"
    assert overlay_style("Primavera", "jardi", Path("jardi-de-primavera-jardi-temporada.png")) == "petals"
    assert overlay_style("Primavera", "pluja", Path("jardi-de-primavera-pluja-temporada.png")) == "pluja"
    assert overlay_style("Primavera", "pluja", Path("cafeteria-de-primavera-cafeteria-temporada.png")) == "pols"  # dins no plou
    assert overlay_style("Estiu", "nit-estiu", Path("nit-d-estiu-nit-estiu-temporada.png")) == "cuques" and overlay_mode("cuques") == "screen"
    assert overlay_style("Halloween", "nit-halloween", Path("cabana-de-halloween-nit-halloween-temporada.png")) == "boira"
    assert overlay_style("Halloween", "nit-halloween") == "boira" and overlay_style("Estiu", "mar") == "pols"
    assert music_style("pomodoro", "nit-halloween", "Halloween") == "fosca"
    assert music_style("llegir", "nit-estiu", "Estiu") == "jazz" and music_style("dormir", "nit-estiu", "Estiu") == "calma"
    for key in ("nit-halloween", "nit-estiu", "jardi", "tardor"):
        assert ENVIRONMENTS[key].layers
    assert music_advice("dormir", "pluja", "Bosc")["recommended"] is False
    assert music_advice("pomodoro", "cafeteria", "Cafeteria moderna")["recommended"] is False
    assert music_advice("pomodoro", "pluja", "Biblioteca medieval")["recommended"] is True
    assert music_advice("llegir", "llar", "Nadal") == {"recommended": True, "reason": "La música nadalenca encaixa amb el tema.", "style": "Nadal"}
    assert music_advice("ambient", "pluja", "Bosc")["recommended"] is None


def test_key_overlay_renders(tmp_path):
    from app.services import overlays
    path = overlays.ensure_overlay("fulles", cache_dir=tmp_path / "cache", custom_dir=tmp_path / "none", width=64, height=36, fps=5)
    background = tmp_path / "bg.png"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x445566:s=64x36", "-frames:v", "1", str(background)], check=True)
    output = tmp_path / "out.mp4"
    spec = RenderSpec(background, output, "64x36", build_timeline(1, 0, 1), fps=5, show_timer=False, overlay=path, overlay_opacity=1.0, overlay_mode="key")
    command = build_ffmpeg_command(spec, plan=select_encoding(EncodingOptions("cpu"), has_nvenc=False))
    assert "colorkey" in " ".join(command)
    command[command.index("-t") + 1] = "2"
    subprocess.run(command, check=True, capture_output=True)
    assert output.stat().st_size > 0


def test_music_advice_endpoint(env):
    with TestClient(main.app) as client:
        result = client.get("/api/auto/music-advice", params={"format": "dormir", "environment": "pluja", "theme": "Bosc"}).json()
    assert result["recommended"] is False and "dormir" in result["reason"]


def test_themes_are_grouped_in_tiles(env, monkeypatch):
    from app.services.autopilot_plan import THEME_GROUPS, group_themes, grouped_themes
    listed = [t for _, _, themes in grouped_themes() for t in themes]
    assert sorted(listed) == sorted(AUTO_THEMES) and len(listed) == len(set(listed))
    assert list(THEME_GROUPS)[-7:] == ["Estiu", "Tardor", "Primavera", "Hivern", "Nadal", "Halloween", "Pasqua"]
    assert group_themes("grup:Hivern") == ["Hivern"] and group_themes("Bosc") is None
    assert all(THEME_GROUPS[g][1] == (g,) for g in ("Estiu", "Tardor", "Primavera", "Hivern", "Nadal", "Halloween", "Pasqua"))
    for removed in ("Sant Valentí", "Cap d'Any", "Pluja de tardor a la ciutat", "Nau espacial"):
        assert removed not in AUTO_THEMES
    monkeypatch.setattr(main.autopilot, "submit", lambda run_id: None)
    with TestClient(main.app) as client:
        page = client.get("/").text
        assert page.count('class="group-tile"') + page.count('class="group-tile direct"') == len(THEME_GROUPS)
        assert page.count('class="group-tile direct"') == 7 and 'name="theme" value="Hivern"' in page
        assert client.post("/auto", data={"theme": "grup:Inventat", "environment": "bosc", "duration_minutes": "60"}).status_code == 400
        assert client.post("/auto", data={"theme": "grup:Natura", "environment": "bosc", "duration_minutes": "60"}, follow_redirects=False).status_code == 303
        assert client.get("/api/auto/music-advice", params={"format": "llegir", "environment": "llar", "theme": "grup:Nadal"}).json()["style"] == "Nadal"
    with env.session() as db:
        saved = db.query(AutoRun).order_by(AutoRun.id.desc()).first()
    assert saved.theme in THEME_GROUPS["Natura"][1] and saved.background is None


def test_background_belongs_to_the_most_specific_theme(tmp_path):
    for name in ("bosc-bosc-pomodoro.png", "bosc-nevat-hivern-temporada.png", "bosc-de-tardor-tardor-temporada.png",
                 "cafeteria-d-hivern-hivern-temporada.png", "cafeteria-cafeteria-pomodoro.png", "tren-d-hivern-tren-temporada.png",
                 "tren-tren-ambient.png", "hivern-llar-temporada.png"):
        touch(tmp_path / name)
    assert [p.name for p in find_backgrounds(tmp_path, "Bosc")] == ["bosc-bosc-pomodoro.png"]
    assert [p.name for p in find_backgrounds(tmp_path, "Tren")] == ["tren-tren-ambient.png"]
    assert sorted(p.name for p in find_backgrounds(tmp_path, "Hivern")) == [
        "bosc-nevat-hivern-temporada.png", "cafeteria-d-hivern-hivern-temporada.png", "hivern-llar-temporada.png", "tren-d-hivern-tren-temporada.png"]
    assert [p.name for p in find_backgrounds(tmp_path, "Tardor")] == ["bosc-de-tardor-tardor-temporada.png"]


def test_scenes_belong_to_one_season():
    from app.services.scenes import SCENES, SEASONS, scene_for, season_slugs
    assert all(season in SEASONS for season, _, _ in SCENES.values())
    assert scene_for("bosc-de-primavera-riu-temporada") == "Bosc de primavera" and scene_for("bosc-bosc-pomodoro") is None
    assert scene_for("cafeteria-de-halloween-cafeteria-temporada") == "Cafeteria de Halloween"
    assert "poble-nevat" in season_slugs("Nadal") and season_slugs("Bosc") == []


def test_music_level_is_saved_and_changes_the_mix(env, monkeypatch):
    from app.services.autopilot_plan import MUSIC_LEVELS, build_music_mix_command
    low = " ".join(build_music_mix_command([Path("a.mp3")], Path("out.m4a"), level=-8))
    assert "I=-30" in low and set(MUSIC_LEVELS) == {-8, -4, 0, 3}
    monkeypatch.setattr(main.autopilot, "submit", lambda run_id: None)
    with TestClient(main.app) as client:
        page = client.get("/").text
        assert 'name="music_level"' in page and "Escoltar mostra" in page
        assert client.post("/auto", data={"theme": "Bosc", "environment": "bosc", "duration_minutes": "60", "music": "1", "music_level": "7"}).status_code == 400
        assert client.post("/auto", data={"theme": "Nadal", "environment": "llar", "duration_minutes": "60", "music": "1", "music_level": "-4"}, follow_redirects=False).status_code == 303
    with env.session() as db:
        saved = db.query(AutoRun).order_by(AutoRun.id.desc()).first()
    assert saved.theme == "Nadal" and saved.music_level == -4


def test_preview_takes_music_from_inside_the_track():
    from app.services.autopilot_plan import build_preview_command
    command = build_preview_command([], Path("m.mp3"), False, Path("o.mp3"), music_level=-4, music_start=40)
    assert command[command.index("-i") - 2:command.index("-i")] == ["-ss", "40"] and "I=-26" in " ".join(command)
    assert "-ss" not in build_preview_command([], Path("m.mp3"), False, Path("o.mp3"))
    assert main._music_start(None) == 0


def test_music_controls_sit_next_to_the_preview(env):
    with TestClient(main.app) as client:
        page = client.get("/").text
    block = page[page.index('class="sound-check"'):page.index('id="preview"')]
    assert 'name="music"' in block and 'name="music_level"' in block and 'name="music_style"' in block


def test_instagram_reel_is_uploaded_processed_and_published(tmp_path, monkeypatch):
    from app.services import meta
    monkeypatch.setattr(meta.settings, "instagram_user_id", "1784")
    monkeypatch.setattr(meta.settings, "instagram_access_token", "clau-env")
    monkeypatch.setattr(meta.settings, "instagram_token_file", tmp_path / "ig.json")
    video = tmp_path / "short.mp4"
    video.write_bytes(b"0123456789")
    calls, states = [], iter(["IN_PROGRESS", "FINISHED"])

    def fake(method, url, params, headers, body):
        calls.append((method, url, params, headers, body))
        if "refresh_access_token" in url:
            return meta.HttpResponse(200, {"access_token": "clau-nova"})
        if url.endswith("/1784/media"):
            return meta.HttpResponse(200, {"id": "C1"})
        if "rupload" in url:
            return meta.HttpResponse(200, {"success": True})
        if url.endswith("/C1"):
            return meta.HttpResponse(200, {"status_code": next(states)})
        return meta.HttpResponse(200, {"id": "M9"})

    assert meta.instagram_configured()
    assert meta.publish_instagram_reel(video, "hola", request=fake, sleep=lambda s: None) == "M9"
    upload = next(c for c in calls if "rupload" in c[1])
    assert upload[3]["Authorization"] == "OAuth clau-nova" and upload[3]["file_size"] == "10" and upload[4] == b"0123456789"
    assert calls[1][2]["media_type"] == "REELS" and calls[1][2]["upload_type"] == "resumable"
    assert meta._instagram_token() == "clau-nova"
    meta.refresh_instagram_token(request=lambda *a: pytest.fail("no cal renovar dues vegades el mateix dia"))


def test_instagram_errors_are_explained(tmp_path, monkeypatch):
    from app.services import meta
    monkeypatch.setattr(meta.settings, "instagram_user_id", "1784")
    monkeypatch.setattr(meta.settings, "instagram_access_token", "x")
    monkeypatch.setattr(meta.settings, "instagram_token_file", tmp_path / "ig.json")
    video = tmp_path / "short.mp4"
    video.write_bytes(b"1")
    fake = lambda method, url, *a: meta.HttpResponse(400, {"error": {"message": "Invalid OAuth access token"}})
    with pytest.raises(meta.MetaError, match="Invalid OAuth"):
        meta.publish_instagram_reel(video, "hola", request=fake, sleep=lambda s: None)


def test_facebook_reel_goes_through_start_upload_and_finish(tmp_path, monkeypatch):
    from app.services import meta
    monkeypatch.setattr(meta.settings, "facebook_page_id", "P1")
    monkeypatch.setattr(meta.settings, "facebook_page_token", "pagina")
    video = tmp_path / "short.mp4"
    video.write_bytes(b"abc")
    calls = []

    def fake(method, url, params, headers, body):
        calls.append((url, params, headers))
        if params and params.get("upload_phase") == "start":
            return meta.HttpResponse(200, {"video_id": "V7", "upload_url": "https://rupload.facebook.com/video-upload/v23.0/V7"})
        return meta.HttpResponse(200, {"success": True})

    assert meta.facebook_configured() and meta.publish_facebook_reel(video, "text", request=fake) == "V7"
    assert calls[1][2]["file_size"] == "3" and calls[2][1]["upload_phase"] == "finish" and calls[2][1]["video_state"] == "PUBLISHED"


def test_reel_caption_has_link_and_five_hashtags():
    from app.services.meta import reel_caption
    ig = reel_caption("Snowy Christmas Village", "4 Hours · Winter Wind & Fireplace", theme="Nadal", fmt="dormir")
    fb = reel_caption("Snowy Christmas Village", "4 Hours · Winter Wind & Fireplace", theme="Nadal", channel_url="https://www.youtube.com/@TheAmberWindow", facebook=True)
    assert ig.startswith("Cozy Snowy Christmas Village") and "link in bio" in ig and "#christmasambience" in ig
    assert "https://www.youtube.com/@TheAmberWindow" in fb and "link in bio" not in fb
    hashtags = ig.splitlines()[-1].split()
    assert len(hashtags) == 5 and len(set(hashtags)) == 5 and "#fireplacesounds" in hashtags


def test_short_is_also_shared_as_reels(env, monkeypatch):
    from app.services import meta
    touch(env.tmp / "assets" / "backgrounds" / "biblioteca-medieval-01.png")
    monkeypatch.setattr(auto, "build_short_command", lambda bg, video, output, **kw: ["bash", "-c", f"touch '{output}'"])
    monkeypatch.setattr(auto, "instagram_configured", lambda: True)
    monkeypatch.setattr(auto, "facebook_configured", lambda: True)
    shared = []
    monkeypatch.setattr(auto, "publish_instagram_reel", lambda video, caption: shared.append(("ig", video.name, caption)) or "IG1")
    monkeypatch.setattr(auto, "publish_facebook_reel", lambda video, caption: (_ for _ in ()).throw(meta.MetaError("pàgina sense permís")))
    ids = iter(["video1", "short1"])
    monkeypatch.setattr(auto, "upload_video", lambda spec: env.uploads.append(spec) or next(ids))
    run_id = make_run(env.session, shorts=1, instagram=1, facebook=1)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
    assert run.step == "DONE" and run.short_video_id == "short1" and run.instagram_media_id == "IG1" and run.facebook_video_id is None
    assert shared[0][1] == "short.mp4" and "link in bio" in shared[0][2]
    assert "Reel publicat a Instagram" in run.message and "Facebook ha fallat" in run.message
    # El que ha fallat es pot tornar a fer amb el botó «Fer el reel».
    with env.session() as db:
        assert auto.reel_missing(db.get(AutoRun, run_id))
    monkeypatch.setattr(auto, "publish_facebook_reel", lambda video, caption: "FB1")
    auto._make_missing_reel(run_id)
    with env.session() as db:
        run = db.get(AutoRun, run_id)
    assert run.facebook_video_id == "FB1" and not auto.reel_missing(run) and len(shared) == 1


def test_reel_checkboxes_only_when_configured(env, monkeypatch):
    monkeypatch.setattr(main.autopilot, "submit", lambda run_id: None)
    with TestClient(main.app) as client:
        assert 'name="instagram"' not in client.get("/").text
        monkeypatch.setattr(main, "instagram_configured", lambda: True)
        assert 'name="instagram"' in client.get("/").text and 'name="facebook"' not in client.get("/").text
        client.post("/auto", data={"theme": "Bosc", "environment": "bosc", "duration_minutes": "60", "publish": "1", "shorts": "1", "instagram": "1", "facebook": "1"}, follow_redirects=False)
    with env.session() as db:
        saved = db.query(AutoRun).order_by(AutoRun.id.desc()).first()
    assert saved.instagram == 1 and saved.facebook == 0


def test_videos_get_translations_and_playlists(env, monkeypatch):
    touch(env.tmp / "assets" / "backgrounds" / "biblioteca-medieval-01.png")
    monkeypatch.setattr(auto, "build_short_command", lambda bg, video, output, **kw: ["bash", "-c", f"touch '{output}'"])
    ids = iter(["video1", "short1"])
    monkeypatch.setattr(auto, "upload_video", lambda spec: env.uploads.append(spec) or next(ids))
    run_id = make_run(env.session, format="dormir", environment="pluja", shorts=1, duration_minutes=180)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
    assert run.step == "DONE", run.error
    main_upload, short_upload = env.uploads
    assert set(main_upload.localizations) == {"es", "pt", "de", "fr"}
    es = main_upload.localizations["es"]
    assert "Biblioteca medieval" in es["title"] and "3 horas" in es["title"] and "para dormir" in es["title"] and len(es["title"]) <= 100
    assert es["description"].startswith("Biblioteca medieval con lluvia suave") and "The Amber Window" in es["description"]
    assert short_upload.localizations["de"]["title"].endswith("#shorts") and "https://youtu.be/video1" in short_upload.localizations["de"]["description"]
    assert env.playlists == [("video1", [("Sleep Ambience", ANY_TEXT), ("Rain & Thunderstorm Ambience", ANY_TEXT)])]
    assert "Afegit a les llistes: Sleep Ambience, Rain & Thunderstorm Ambience" in run.message


class _AnyText(str):
    def __eq__(self, other):
        return isinstance(other, str) and bool(other)


ANY_TEXT = _AnyText("")


def test_old_youtube_connection_asks_to_reconnect_for_playlists(env, monkeypatch):
    monkeypatch.setattr(auto, "can_manage_playlists", lambda: False)
    run_id = make_run(env.session)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
    assert run.step == "DONE" and env.playlists == [] and "torna a connectar YouTube" in run.message
    monkeypatch.setattr(main, "can_manage_playlists", lambda: False)
    with TestClient(main.app) as client:
        assert "/youtube/reconnect" in client.get("/").text


def test_playlists_follow_format_season_and_sound():
    from app.services.autopilot_plan import playlists_for
    assert [t for t, _ in playlists_for("pomodoro", "Nadal", "llar")] == ["Pomodoro Study Sessions", "Christmas Ambience", "Fireplace Ambience"]
    assert [t for t, _ in playlists_for("soroll", "Soroll de color", "soroll")] == ["Brown, Pink & White Noise"]
    assert [t for t, _ in playlists_for("llegir", "Cafeteria a París", "cafeteria")] == ["Reading Ambience", "Coffee Shop Ambience"]


def test_translated_titles_fit_and_cover_every_theme_and_sound():
    from app.services.translations import LANGUAGES, SOUND_NAMES, THEME_NAMES, localized_texts
    from app.themes import THEMES
    for public in THEMES.values():
        assert public in THEME_NAMES, public
    for env in ENVIRONMENTS.values():
        assert env.public_label in SOUND_NAMES, env.public_label
    for fmt, noise, breath in (("pomodoro", None, None), ("dormir", None, None), ("soroll", "Brown", None), ("respiracio", None, "Box Breathing"), ("rol", None, None)):
        texts = localized_texts(fmt=fmt, public_theme="Enchanted Wizard Library", sound="Winter Wind & Fireplace", duration_minutes=600,
                                english_description="Intro.\n\nChapters:\n00:00:00 Hour 1", focus=90, pause=15, noise=noise, breath=breath, dim=True)
        for lang in LANGUAGES:
            assert 0 < len(texts[lang]["title"]) <= 100 and "00:00:00 Hour 1" in texts[lang]["description"], (fmt, lang)
    assert "Trabajo profundo 90/15" in localized_texts(fmt="pomodoro", public_theme="Rainy Cabin", sound="Gentle Rain", duration_minutes=120,
                                                      english_description="x", focus=90, pause=15)["es"]["title"]


def test_new_thumbnail_has_big_title_over_the_image(tmp_path):
    from PIL import Image
    from app.services.thumbnail import make_thumbnail
    background = tmp_path / "bg.png"
    Image.new("RGB", (1920, 1080), (90, 120, 160)).save(background)
    out = make_thumbnail(background, tmp_path / "t.jpg", "Victorian Library", "3 Hours · Howling Wind")
    image = Image.open(out)
    assert image.size == (1280, 720)
    top, bottom = image.getpixel((640, 40)), image.getpixel((1200, 700))
    assert sum(bottom) < sum(top)  # degradat fosc baix, la part de dalt queda viva


def test_never_expiring_facebook_token_publishes_through_facebook_graph(tmp_path, monkeypatch):
    from app.services import meta
    monkeypatch.setattr(meta.settings, "instagram_user_id", "1784")
    monkeypatch.setattr(meta.settings, "instagram_access_token", "EAAsistema")
    monkeypatch.setattr(meta.settings, "instagram_token_file", tmp_path / "ig.json")
    video = tmp_path / "short.mp4"
    video.write_bytes(b"12")
    urls = []

    def fake(method, url, params, headers, body):
        urls.append(url)
        assert "refresh_access_token" not in url
        if url.endswith("/1784/media"):
            return meta.HttpResponse(200, {"id": "C1"})
        if url.endswith("/C1"):
            return meta.HttpResponse(200, {"status_code": "FINISHED"})
        return meta.HttpResponse(200, {"id": "M1", "success": True})

    assert meta.publish_instagram_reel(video, "hola", request=fake, sleep=lambda s: None) == "M1"
    assert urls[0].startswith("https://graph.facebook.com/") and any("rupload.facebook.com/ig-api-upload" in u for u in urls)


def test_three_shorts_are_made_and_the_last_two_scheduled(env, monkeypatch):
    touch(env.tmp / "assets" / "backgrounds" / "biblioteca-medieval-01.png")
    commands = []
    monkeypatch.setattr(auto, "build_short_command", lambda bg, video, output, **kw: commands.append(kw) or ["bash", "-c", f"touch '{output}'"])
    ids = iter(["video1", "short1", "short2", "short3"])
    monkeypatch.setattr(auto, "upload_video", lambda spec: env.uploads.append(spec) or next(ids))
    run_id = make_run(env.session, shorts=3, duration_minutes=180)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
    assert run.step == "DONE" and run.short_video_id == "short1" and run.extra_short_ids == "short2,short3"
    _, first, second, third = env.uploads
    assert first.publish_at is None and second.publish_at and third.publish_at and second.publish_at < third.publish_at
    assert [u.video.name for u in (first, second, third)] == ["short.mp4", "short-2.mp4", "short-3.mp4"]
    assert len({u.title for u in (first, second, third)}) == 3 and all(u.title.endswith("#shorts") for u in (first, second, third))
    starts = [kw["start"] for kw in commands]
    assert len(set(starts)) == 3 and commands[1]["subtitle"] != commands[2]["subtitle"] and commands[1]["subtitle"] in SHORT_PHRASES
    assert "2 Shorts més programats" in run.message


def test_scheduled_upload_is_private_until_publish_time(tmp_path, monkeypatch):
    from app.services import youtube
    video = tmp_path / "short-2.mp4"
    video.write_bytes(b"x")
    bodies = []

    class Request:
        def next_chunk(self):
            return None, {"id": "S2"}

    class Videos:
        def insert(self, **kwargs):
            bodies.append(kwargs["body"])
            return Request()

    class Service:
        def videos(self):
            return Videos()

    monkeypatch.setattr(youtube, "google_libraries", lambda: (None, None, None, lambda *a, **k: Service(), lambda *a, **k: None))
    monkeypatch.setattr(youtube, "credentials", lambda: None)
    spec = youtube.YouTubeUploadSpec(video, "t #shorts", "d", [], "22", "en", "public", None, {}, "2026-11-07T10:00:00Z")
    assert youtube.upload_video(spec) == "S2"
    assert bodies[0]["status"]["privacyStatus"] == "private" and bodies[0]["status"]["publishAt"] == "2026-11-07T10:00:00Z"


def test_suggestions_follow_the_season_history_and_views():
    from datetime import date, datetime
    from app.services.suggestions import build_suggestions, easter, seasonal_themes
    assert easter(2027) == date(2027, 3, 28)
    assert seasonal_themes(date(2026, 11, 5))[0][0] == "Nadal"
    assert "Halloween" in [t for t, _ in seasonal_themes(date(2026, 10, 10))]
    history = [
        ("Biblioteca victoriana", "pluja", "pomodoro", datetime(2026, 11, 3), "a"),
        ("Biblioteca victoriana", "pluja-finestra", "dormir", datetime(2026, 11, 1), "b"),
        ("Bosc", "bosc", "ambient", datetime(2026, 10, 1), "c"),
    ]
    tips = build_suggestions(date(2026, 11, 5), history, {"a": 120, "b": 80, "c": 5}, {}, {"Nadal", "Biblioteca victoriana", "Bosc"})
    assert tips[0].theme == "Nadal" and "encara no n'has fet cap" in tips[0].text
    assert tips[1].environment and "Encara no has fet cap vídeo de" in tips[1].text
    assert tips[2].theme == "Biblioteca victoriana" and "100 visualitzacions" in tips[2].text
    assert build_suggestions(date(2026, 11, 5), history, {}, {}, set())[0].theme is None  # sense fons de Nadal no es suggerix


def test_home_shows_suggestions_and_shorts_choice(env, monkeypatch):
    with TestClient(main.app) as client:
        page = client.get("/").text
    assert 'name="shorts"' in page and '<option value="3" selected>' in page
    assert "Suggeriments" in page and "data-suggest-environment" in page


def test_video_list_has_pager_and_thumbnails(env, monkeypatch):
    for _ in range(8):
        make_run(env.session, step="DONE", video_id="v")
    with TestClient(main.app) as client:
        page = client.get("/").text
        runs = client.get("/api/auto").json()["runs"]
    assert 'id="pager"' in page and len(runs) == 8 and "thumbnail_url" in runs[0]


def test_text_backdrops_darken_only_where_the_text_goes(tmp_path):
    from PIL import Image
    from app.services.backdrops import short_backdrop, timer_backdrop
    background = tmp_path / "bg.png"
    Image.new("RGB", (1920, 1080), (200, 200, 200)).save(background)
    timer = Image.open(timer_backdrop(background, tmp_path / "t.png"))
    assert sum(timer.getpixel((960, 500))) < sum(timer.getpixel((60, 60))) == 600
    short = Image.open(short_backdrop(background, tmp_path / "s.png"))
    assert short.size == (1080, 1920)
    assert sum(short.getpixel((540, 40))) < sum(short.getpixel((540, 960))) > sum(short.getpixel((540, 1900)))
    video = tmp_path / "v.mp4"
    assert timer_backdrop(video, tmp_path / "x.png") == video  # els fons en vídeo no es toquen


def test_new_cozy_themes_replace_the_bunker():
    from app.services.fonts import THEME_FONTS
    from app.services.translations import THEME_NAMES
    assert "Búnquer postapocalíptic" not in AUTO_THEMES
    for theme in ("Llibreria acollidora", "Golfa amb pluja", "Far en la tempesta", "Casa de te japonesa"):
        assert theme in AUTO_THEMES and theme in THEME_FONTS and THEMES[theme] in THEME_NAMES, theme


def test_video_check_finds_silence_black_and_wrong_length(tmp_path):
    from app.services.quality import check_video
    good, bad = tmp_path / "g.mp4", tmp_path / "b.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x556677:s=64x36:d=40", "-f", "lavfi", "-i", "anoisesrc=d=40:a=0.05", "-shortest", str(good)], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x36:d=40", "-f", "lavfi", "-i", "anullsrc", "-t", "40", str(bad)], check=True)
    assert check_video(good, 40) == []
    problems = check_video(bad, 120)
    assert any("dura" in p for p in problems) and any("sense so" in p for p in problems) and any("negra" in p for p in problems)
    assert not any("negra" in p for p in check_video(bad, 40, black_screen=True))


def test_failed_check_stops_upload_and_can_publish_anyway(env, monkeypatch):
    monkeypatch.setattr(auto, "check_video", lambda video, seconds, **kw: ["hi ha 1 tros sense so (el més llarg, de 60 s)"])
    run_id = make_run(env.session)
    auto.execute(run_id, rng=random.Random(0))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
    assert run.step == "FAILED" and run.error.startswith("Comprovació:") and env.uploads == []
    auto._publish_existing(run_id)
    with env.session() as db:
        assert db.get(AutoRun, run_id).step == "DONE" and len(env.uploads) == 1


def test_calendar_slots_one_video_per_day():
    from datetime import datetime
    from app.services.schedule import label, next_slot, publish_at
    now = datetime(2026, 11, 5, 14, 0)  # 15:00 a València
    first = next_slot(now, [], hour=18, zone="Europe/Madrid")
    second = next_slot(now, [first], hour=18, zone="Europe/Madrid")
    assert label(first, "Europe/Madrid") == "dv 6/11 a les 18:00" and label(second, "Europe/Madrid") == "ds 7/11 a les 18:00"
    assert publish_at(first, now) == "2026-11-06T17:00:00Z" and publish_at(first, first) is None


def test_scheduled_video_is_uploaded_with_publish_time_and_reels_wait(env, monkeypatch):
    from datetime import datetime, timedelta
    touch(env.tmp / "assets" / "backgrounds" / "biblioteca-medieval-01.png")
    monkeypatch.setattr(auto, "build_short_command", lambda bg, video, output, **kw: ["bash", "-c", f"touch '{output}'"])
    monkeypatch.setattr(auto, "instagram_configured", lambda: True)
    shared = []
    monkeypatch.setattr(auto, "publish_instagram_reel", lambda video, caption: shared.append(video.name) or "IG1")
    ids = iter(["video1", "short1", "short2", "short3"])
    monkeypatch.setattr(auto, "upload_video", lambda spec: env.uploads.append(spec) or next(ids))
    when = datetime.utcnow().replace(microsecond=0) + timedelta(days=1)
    run_id = make_run(env.session, shorts=3, instagram=1, scheduled_for=when)
    auto.execute(run_id, rng=random.Random(0))
    main_upload, first_short, second_short, _ = env.uploads
    assert main_upload.publish_at == when.isoformat() + "Z" and first_short.publish_at == main_upload.publish_at
    assert second_short.publish_at == (when + timedelta(days=1)).isoformat() + "Z"
    with env.session() as db:
        run = db.get(AutoRun, run_id)
        assert shared == [] and run_summary_label(run).startswith("Programat")
        assert auto.pending_reels(run) == {} and auto.runs_with_pending_reels() == []
        assert auto.pending_reels(run, when + timedelta(minutes=1)) == {"short.mp4": {"ig"}}
        assert set(auto.pending_reels(run, when + timedelta(days=1, minutes=1))) == {"short.mp4", "short-2.mp4"}
        db.get(AutoRun, run_id).scheduled_for = datetime.utcnow() - timedelta(minutes=1)  # ja és l'hora
        db.commit()
    assert auto.runs_with_pending_reels() == [run_id]
    auto._make_missing_reel(run_id)
    with env.session() as db:
        run = db.get(AutoRun, run_id)
    assert shared == ["short.mp4"] and run.instagram_media_id == "IG1" and auto.pending_reels(run) == {}


def run_summary_label(run):
    return auto.run_summary(run)["step_label"]


def test_form_schedules_and_stats_page(env, monkeypatch):
    monkeypatch.setattr(main.autopilot, "submit", lambda run_id: None)
    with TestClient(main.app) as client:
        page = client.get("/").text
        assert 'name="schedule"' in page and "pròxim dia lliure" in page
        for _ in range(2):
            client.post("/auto", data={"theme": "Bosc", "environment": "bosc", "duration_minutes": "60", "publish": "1", "privacy": "public", "schedule": "1"}, follow_redirects=False)
        assert "Calendari" in client.get("/").text
        with env.session() as db:
            first, second = [r.scheduled_for for r in db.query(AutoRun).order_by(AutoRun.id).all()[-2:]]
        assert first and second and (second - first).days == 1
        make_run(env.session, step="DONE", video_id="vid1", theme="Bosc")
        main.settings.youtube_stats_file.write_text('{"fetched": "2026-11-05T12:00:00", "views": {"vid1": 42}}')
        stats = client.get("/estadistiques").text
        assert "Per tema" in stats and "42" in stats
        monkeypatch.setattr(main, "view_counts", lambda ids: {i: 7 for i in ids})
        assert client.post("/estadistiques/actualitzar", follow_redirects=False).status_code == 303
        assert '"vid1": 7' in main.settings.youtube_stats_file.read_text()


def test_channel_intro_renders_and_blends_with_the_start(tmp_path):
    from app.services.channel_intro import SECONDS, ensure_channel_intro, render_frame, _sparks, _title_layers
    import random as _random
    gold, glow = _title_layers(96, 54, None)
    sparks = _sparks(96, 54, _random.Random(1), 10)
    assert render_frame(0, 96, 54, gold, glow, sparks).tobytes() != render_frame(2, 96, 54, gold, glow, sparks).tobytes()
    clip = ensure_channel_intro(cache_dir=tmp_path, width=64, height=36, fps=5)
    background = tmp_path / "bg.png"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x556677:s=64x36", "-frames:v", "1", str(background)], check=True)
    output = tmp_path / "out.mp4"
    spec = RenderSpec(background, output, "64x36", build_timeline(1, 0, 1), fps=5, show_timer=True, channel_intro=clip)
    command = build_ffmpeg_command(spec, plan=select_encoding(EncodingOptions("cpu"), has_nvenc=False))
    joined = " ".join(command)
    assert "blend=all_mode=screen" in joined and "concat=n=2" in joined and "alpha=" in joined
    command[command.index("-t") + 1] = str(SECONDS + 3)
    subprocess.run(command, check=True, capture_output=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(output)], capture_output=True, text=True, check=True)
    assert float(probe.stdout) >= SECONDS + 2


def test_intro_is_requested_from_the_form(env, monkeypatch):
    monkeypatch.setattr(main.autopilot, "submit", lambda run_id: None)
    monkeypatch.setattr(auto, "ensure_channel_intro", lambda **kw: touch(env.tmp / "overlays" / "intro.mp4"))
    with TestClient(main.app) as client:
        assert 'name="intro"' in client.get("/").text
        client.post("/auto", data={"theme": "Biblioteca medieval", "environment": "pluja", "duration_minutes": "60", "intro": "1"}, follow_redirects=False)
    with env.session() as db:
        run_id = db.query(AutoRun).order_by(AutoRun.id.desc()).first().id
        assert db.get(AutoRun, run_id).intro == 1
    auto.execute(run_id, rng=random.Random(0))
    assert env.rendered["spec"].channel_intro.name == "intro.mp4"


def test_week_batch_makes_varied_videos_one_per_day(env, monkeypatch):
    from datetime import datetime, timedelta
    groups = [{"theme": t, "items": [{"name": f"{t}-{f}.png", "url": "", "format": f, "environment": e} for f, e in (("pomodoro", "pluja"), ("dormir", "llar"), ("llegir", "pluja-finestra"))]}
              for t in ("Biblioteca victoriana", "Cabana amb pluja", "Golfa amb pluja", "Llibreria acollidora", "Far en la tempesta", "Bosc", "Riu", "Port")]
    monkeypatch.setattr(main, "background_library", lambda: groups)
    submitted = []
    monkeypatch.setattr(main.autopilot, "submit", submitted.append)
    day = (datetime.utcnow() + timedelta(days=3)).date().isoformat()
    with TestClient(main.app) as client:
        assert "Preparar la setmana" in client.get("/").text
        assert client.post("/auto/setmana", data={"count": "7", "first_day": day, "publish_time": "18:00"}, follow_redirects=False).status_code == 303
        assert client.post("/auto/setmana", data={"count": "9", "first_day": day}).status_code == 400
        assert client.post("/auto/setmana", data={"count": "3", "first_day": "2020-01-01"}).status_code == 400
    with env.session() as db:
        runs = db.query(AutoRun).filter(AutoRun.id.in_(submitted)).order_by(AutoRun.id).all()
    assert len(runs) == 7 and len({r.theme for r in runs}) == 7
    assert [(b.scheduled_for - a.scheduled_for).days for a, b in zip(runs, runs[1:])] == [1] * 6
    assert {r.format for r in runs} >= {"pomodoro", "dormir", "llegir"} and all(r.publish and r.privacy == "public" and r.shorts == 3 for r in runs)
    assert all(r.background.startswith(r.theme) for r in runs) and runs[1].duration_minutes == 480 and runs[1].dim == 1


def test_video_can_be_scheduled_for_a_chosen_day(env, monkeypatch):
    from datetime import datetime, timedelta
    monkeypatch.setattr(main.autopilot, "submit", lambda run_id: None)
    day = (datetime.utcnow() + timedelta(days=4)).date().isoformat()
    with TestClient(main.app) as client:
        base = {"theme": "Bosc", "environment": "bosc", "duration_minutes": "60", "publish": "1", "privacy": "public"}
        assert client.post("/auto", data=base | {"schedule": "date", "publish_date": day, "publish_time": "09:30"}, follow_redirects=False).status_code == 303
        assert client.post("/auto", data=base | {"schedule": "date", "publish_date": "2020-01-01"}).status_code == 400
    with env.session() as db:
        run = db.query(AutoRun).order_by(AutoRun.id.desc()).first()
    from app.services.schedule import to_local
    local = to_local(run.scheduled_for, "Europe/Madrid")
    assert local.date().isoformat() == day and (local.hour, local.minute) == (9, 30)


def test_week_batch_uses_the_chosen_volumes_and_music(env, monkeypatch):
    from datetime import datetime, timedelta
    groups = [{"theme": t, "items": [{"name": f"{t}-p.png", "url": "", "format": "pomodoro", "environment": "pluja"}]} for t in ("Bosc", "Riu", "Port")]
    monkeypatch.setattr(main, "background_library", lambda: groups)
    submitted = []
    monkeypatch.setattr(main.autopilot, "submit", submitted.append)
    day = (datetime.utcnow() + timedelta(days=2)).date().isoformat()
    with TestClient(main.app) as client:
        page = client.get("/").text
        assert 'name="music_mode"' in page
        client.post("/auto/setmana", data={"count": "3", "first_day": day, "ambience_level": "-6", "music_mode": "no", "music_level": "-8"}, follow_redirects=False)
        assert client.post("/auto/setmana", data={"count": "3", "first_day": day, "music_level": "9"}).status_code == 400
    with env.session() as db:
        runs = db.query(AutoRun).filter(AutoRun.id.in_(submitted)).all()
    assert len(runs) == 3 and all(r.ambience_level == -6 and r.music == 0 and r.music_level == -8 for r in runs)


def test_week_batch_can_stick_to_one_theme(env, monkeypatch):
    from datetime import datetime, timedelta
    nadal = [{"name": n, "url": "", "format": "", "environment": ""} for n in (
        "cabana-de-nadal-llar-nadal.png", "sala-de-nadal-llar-nadal.png", "poble-nevat-hivern-nadal.png", "mercat-de-nadal-cafeteria-carrer-nadal.png")]
    groups = [{"theme": "Nadal", "items": nadal}, {"theme": "Bosc", "items": [{"name": "bosc-bosc-pomodoro.png", "url": "", "format": "pomodoro", "environment": "bosc"}]}]
    monkeypatch.setattr(main, "background_library", lambda: groups)
    submitted = []
    monkeypatch.setattr(main.autopilot, "submit", submitted.append)
    day = (datetime.utcnow() + timedelta(days=2)).date().isoformat()
    with TestClient(main.app) as client:
        assert 'value="grup:Nadal"' in client.get("/").text
        client.post("/auto/setmana", data={"count": "6", "first_day": day, "theme": "grup:Nadal"}, follow_redirects=False)
        assert client.post("/auto/setmana", data={"count": "2", "first_day": day, "theme": "grup:Inventat"}).status_code == 400
    with env.session() as db:
        runs = db.query(AutoRun).filter(AutoRun.id.in_(submitted)).order_by(AutoRun.id).all()
    assert len(runs) == 6 and {r.theme for r in runs} == {"Nadal"}
    assert len({r.background for r in runs[:4]}) == 4  # primer tots els fons diferents
    assert {r.environment for r in runs} <= {"llar", "hivern", "cafeteria-carrer"} and len({r.format for r in runs}) >= 3


def test_every_scene_belongs_only_to_its_season(tmp_path):
    from app.services.scenes import SCENES, slugify
    for scene in SCENES:
        touch(tmp_path / f"{slugify(scene)}-llar-temporada.png")
    owners = {}
    for theme in AUTO_THEMES:
        for path in find_backgrounds(tmp_path, theme):
            owners.setdefault(path.name, []).append(theme)
    for scene, (season, _, _) in SCENES.items():
        assert owners.get(f"{slugify(scene)}-llar-temporada.png") == [season], scene


def test_continents_are_themes_with_scenes_and_world_sounds():
    from app.services.autopilot_plan import THEME_GROUPS, playlists_for
    from app.services.overlays import overlay_style
    from app.services.scenes import SCENES, SEASONS
    import json as _json
    continents = ("Àfrica", "Àsia", "Sud-amèrica", "Europa", "Nord-amèrica")
    assert THEME_GROUPS["Món"][1] == continents
    for theme in continents:
        assert theme in SEASONS and sum(season == theme for season, _, _ in SCENES.values()) >= 5
    assert overlay_style("Àfrica", "desert", Path("campament-al-desert-desert-temporada.png")) == "guspires"
    assert overlay_style("Àsia", "selva-pluja", Path("temple-a-la-jungla-selva-pluja-temporada.png")) == "pluja"
    assert overlay_style("Nord-amèrica", "hivern", Path("cabana-a-alaska-hivern-temporada.png")) == "neu"
    assert "Around the World Ambience" in [t for t, _ in playlists_for("dormir", "Àsia", "selva-nit")]
    catalog = _json.loads((Path(__file__).resolve().parent.parent / "assets" / "audio-catalog.json").read_text())
    files = {Path(e["file"]).stem: e for e in catalog}
    for key in ("selva", "selva-nit", "selva-pluja", "riu-selva", "sabana-nit", "desert", "monso"):
        for layer in ENVIRONMENTS[key].layers:
            for name in layer:
                entry = files[name]
                assert entry["license"].startswith("CC0") or "freesound_page" not in entry, name


def test_freesound_preview_is_found_in_the_page():
    import importlib.util
    spec = importlib.util.spec_from_file_location("descarregar", Path(__file__).resolve().parent.parent / "scripts" / "descarregar-sons.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    html = '<div data-mp3="https://cdn.freesound.org/previews/676/676675_98765-lq.mp3"></div>'
    module.urllib.request.urlopen = lambda request, timeout=60: __import__("io").BytesIO(html.encode())
    class _Ctx(__import__("io").BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    module.urllib.request.urlopen = lambda request, timeout=60: _Ctx(html.encode())
    assert module.freesound_url("https://freesound.org/x") == "https://cdn.freesound.org/previews/676/676675_98765-hq.mp3"


def test_every_short_gets_its_reel_on_its_day_and_failures_are_retried(env, monkeypatch):
    from datetime import datetime, timedelta
    from app.services import meta
    touch(env.tmp / "assets" / "backgrounds" / "biblioteca-medieval-01.png")
    monkeypatch.setattr(auto, "build_short_command", lambda bg, video, output, **kw: ["bash", "-c", f"touch '{output}'"])
    monkeypatch.setattr(auto, "instagram_configured", lambda: True)
    ids = iter(["video1", "short1", "short2", "short3"])
    monkeypatch.setattr(auto, "upload_video", lambda spec: env.uploads.append(spec) or next(ids))
    calls = []
    def flaky(video, caption):
        calls.append(video.name)
        if video.name == "short-2.mp4":
            raise meta.MetaError("temps d'espera")
        return f"IG-{video.name}"
    monkeypatch.setattr(auto, "publish_instagram_reel", flaky)
    run_id = make_run(env.session, shorts=3, instagram=1)
    auto.execute(run_id, rng=random.Random(0))
    assert calls == ["short.mp4"]
    later = datetime.utcnow() + timedelta(days=2, minutes=1)
    with env.session() as db:
        run = db.get(AutoRun, run_id)
        assert set(auto.pending_reels(run, later)) == {"short-2.mp4", "short-3.mp4"}
        run.published_at -= timedelta(days=2, minutes=2)  # han passat dos dies
        db.commit()
    for _ in range(4):
        auto._make_missing_reel(run_id)
    assert calls.count("short-3.mp4") == 1 and calls.count("short-2.mp4") == 3  # com a molt 3 intents
    with env.session() as db:
        run = db.get(AutoRun, run_id)
        assert auto.pending_reels(run) == {}
        assert '"short-3.mp4": {"ig": "IG-short-3.mp4"}' in run.reels_json


def test_unticked_reels_are_never_posted(env, monkeypatch):
    monkeypatch.setattr(main.autopilot, "submit", lambda run_id: None)
    monkeypatch.setattr(main, "instagram_configured", lambda: True)
    with TestClient(main.app) as client:
        client.post("/auto", data={"theme": "Bosc", "environment": "bosc", "duration_minutes": "60", "publish": "1", "shorts": "1"}, follow_redirects=False)
    with env.session() as db:
        run = db.query(AutoRun).order_by(AutoRun.id.desc()).first()
        assert run.instagram == 0 and '"skip_ig": true' in run.reels_json
        run.step, run.video_id, run.short_video_id, run.published_at = "DONE", "v", "s", __import__("datetime").datetime.utcnow()
        db.commit()
        monkeypatch.setattr(auto, "instagram_configured", lambda: True)
        assert auto.pending_reels(db.get(AutoRun, run.id)) == {}


def test_videos_are_kept_until_the_last_short_is_public(env):
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    run_id = make_run(env.session, step="DONE", video_id="v", delete_after=1, shorts=3, published_at=now - timedelta(days=4), scheduled_for=now + timedelta(days=1))
    with env.session() as db:
        run = db.get(AutoRun, run_id)
        assert auto._delete_on(run) == (now + timedelta(days=1 + 2 + 3)).date().isoformat()


def test_texts_vary_between_videos_but_keep_search_words():
    from app.services.autopilot_plan import NOISE_COLORS
    from app.services.text_variants import SHORT_PHRASES, short_phrase
    chapters = "00:00:00 Hour 1"
    for fmt in ("pomodoro", "dormir", "llegir", "ambient", "rol"):
        seen = set()
        for seed in range(8):
            texts = build_texts(public_theme="Christmas Library", environment="llar", duration=480, focus=25, pause=5, chapters=chapters,
                                credits="", fmt=fmt, seed=seed)
            assert len(texts.title) <= 100 and "8 Hours" in texts.title and "The Amber Window" in texts.description
            if fmt != "rol":
                assert texts.title.startswith("Cozy Christmas Library") and texts.description.startswith("Cozy Christmas Library")
            seen.add(texts.description.split("\n\n")[0])
        assert len(seen) == 8, fmt
        first, second = (build_texts(public_theme="Christmas Library", environment="llar", duration=120, focus=25, pause=5,
                                     chapters=chapters, credits="", fmt=fmt, seed=s).description for s in (5, 6))
        assert first.split("\n\n")[:2] != second.split("\n\n")[:2]
    for noise in NOISE_COLORS:
        for seed in range(8):
            texts = build_texts(public_theme="x", environment="soroll", duration=600, focus=600, pause=0, chapters=chapters, credits="",
                                fmt="soroll", noise=noise, seed=seed)
            assert len(texts.title) <= 100 and "Noise" in texts.title
    phrases = [short_phrase(seed, part) for seed in range(15) for part in (2, 3)]
    assert len(set(phrases)) == len(SHORT_PHRASES) == 30
    assert all("," not in p and "'" not in p for p in SHORT_PHRASES)


def test_title_says_no_music_when_there_is_none():
    from app.services.translations import localized_texts
    for fmt in ("pomodoro", "dormir", "llegir", "rol"):
        silent = build_texts(public_theme="Rainy Library", environment="pluja", duration=180, focus=25, pause=5, chapters="", credits="",
                             fmt=fmt, music=False, seed=1)
        assert silent.title.endswith("(No Music)") and len(silent.title) <= 100, silent.title
        assert "(No Music)" not in build_texts(public_theme="Rainy Library", environment="pluja", duration=180, focus=25, pause=5,
                                               chapters="", credits="", fmt=fmt, music=True, seed=1).title
    ambient = build_texts(public_theme="Rainy Library", environment="pluja", duration=180, focus=180, pause=0, chapters="", credits="",
                          fmt="ambient", music=False, seed=1)
    assert "(No Music)" not in ambient.title and "No Music" in ambient.title
    es = localized_texts(fmt="dormir", public_theme="Rainy Library", sound="Rain", duration_minutes=180, english_description="x", music=False)
    assert es["es"]["title"].endswith("(Sin música)") and es["de"]["title"].endswith("(Ohne Musik)")


def test_anime_backgrounds_are_chosen_by_style_and_titled(env):
    from app.services.autopilot_plan import anime_title, background_style, playlists_for
    folder = env.tmp / "assets" / "backgrounds"
    touch(folder / "biblioteca-medieval-llar-pomodoro.png")
    touch(folder / "biblioteca-medieval-llar-pomodoro-anime.png")
    assert background_style(folder / "biblioteca-medieval-llar-pomodoro-anime.png") == "anime"
    assert background_style(folder / "biblioteca-medieval-llar-pomodoro.png") == "realista"
    rng = random.Random(1)
    for _ in range(5):
        assert auto.choose_background("Biblioteca medieval", "llar", rng, visual_style="anime")[0].name.endswith("-anime.png")
        assert not auto.choose_background("Biblioteca medieval", "llar", rng, visual_style="realista")[0].name.endswith("-anime.png")
    touch(folder / "masmorra-masmorra-pomodoro.png")
    path, note = auto.choose_background("Masmorra", "masmorra", rng, visual_style="anime")
    assert path.name == "masmorra-masmorra-pomodoro.png" and "anime" in note
    title = anime_title("Cozy Rainy Library Ambience | 3 Hours Pomodoro 25/5 Study With Me | Rain Sounds")
    assert title.startswith("Cozy Rainy Library Anime Ambience |") and len(title) <= 100
    assert len(anime_title("Cozy " + "Very Long Name " * 5 + "Ambience | 10 Hours Deep Work 90/15 Study With Me | Rain & Fireplace Sounds")) <= 100
    texts = build_texts(public_theme="Rainy Library", environment="pluja", duration=120, focus=25, pause=5, chapters="", credits="", anime=True, seed=1)
    assert "Anime Ambience" in texts.title and texts.tags.startswith("anime ambience") and "#animeambience" in texts.description
    assert playlists_for("pomodoro", "Nadal", "llar", anime=True)[0][0] == "Cozy Anime Ambience"


def test_anime_videos_use_rounded_font_and_lofi():
    from app.services.autopilot_plan import ENVIRONMENTS, LOFI_FORMATS, MUSIC_STYLES, track_style
    from app.services.fonts import fonts_for_theme
    root = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    anime = fonts_for_theme("Biblioteca medieval", root=root, anime=True)
    assert anime.label and anime.label.name.startswith("ZenMaruGothic") and anime.digits.name.startswith("ZenMaruGothic")
    assert fonts_for_theme("Biblioteca medieval", root=root).label.name.startswith("IMFe")
    assert "lofi" in MUSIC_STYLES and {"pomodoro", "llegir"} <= LOFI_FORMATS
    assert track_style(Path("lofi-winter-blues.mp3")) == "lofi"
    assert ENVIRONMENTS["pluja-vinil"].layers[1] == ("vinil",) and ENVIRONMENTS["estiu-japo"].layers == (("cigales",), ("campanetes-vent",))


def test_import_script_names_and_describes_backgrounds(tmp_path):
    import importlib.util, struct, zlib
    spec = importlib.util.spec_from_file_location("importar_fons", Path(__file__).resolve().parent.parent / "scripts" / "importar-fons.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    png = tmp_path / "Pomodoro + Habitació amb kotatsu + Vent d'hivern i llar.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 2304, 1296) + b"\x08\x02\x00\x00\x00")
    name, meta = module.plan(png, anime=True)
    assert name == "habitacio-amb-kotatsu-hivern-pomodoro-anime.png"
    assert meta["generation"]["style"] == "anime" and meta["generation"]["width"] == 2304 and meta["generation"]["format"] == "pomodoro"
    seasonal = tmp_path / "Nadal + Poble del Pol Nord + Nit tranquil·la.png"
    seasonal.write_bytes(png.read_bytes())
    assert module.plan(seasonal, anime=False)[0] == "poble-del-pol-nord-nit-temporada.png"
    assert "no conec" in module.plan(tmp_path / "Pomodoro + Tema inventat + Vent.png", anime=True)


def test_progress_bar_and_session_dots_follow_the_timeline():
    from app.services.renderer import progress_bar_parts, session_dot_filters
    from app.services.timer import build_timeline
    timeline = build_timeline(25, 5, 180)
    parts = progress_bar_parts("[v]", "vbar", timeline, 1920, 1080, 30)
    assert parts[-1].startswith("[v][p") and parts[-1].endswith("[vbar]") and any("0xF3C47A" in p for p in parts) and any("0x9CC7A4" in p for p in parts)
    dots = session_dot_filters(timeline)
    assert len({d.split("x=w/2+(")[1].split(")")[0] for d in dots}) == 4 and all("●" in d for d in dots)
    assert session_dot_filters(build_timeline(50, 10, 60)) == []
