import json
import random
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base
from app.models import AutoRun
from app.services import autopilot as auto
from app.services import background_library as lib


def png(path: Path, size=(64, 36)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (120, 80, 40)).save(path)
    return path


def jpeg_bytes(size) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (90, 60, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(lib.settings, "assets_dir", tmp_path / "assets")
    monkeypatch.setattr(lib.settings, "image_generation_dir", tmp_path / "generated")
    calls = []

    def fake_generate_one(theme, environment, fmt, output_dir):
        calls.append((theme, environment, fmt))
        path = png(output_dir / f"generated-{len(calls)}.png")
        return path, {"prompt": f"{theme} scene", "negative_prompt": "", "provider": "a1111", "model": "FLUX.1 schnell",
                      "license": "Generat localment amb Forge", "source_notes": "seed 1", "generation": {"profile": "flux-schnell"}}

    monkeypatch.setattr(lib, "generate_one", fake_generate_one)
    return SimpleNamespace(root=tmp_path, calls=calls)


def test_generated_candidates_can_be_kept_or_discarded(dirs):
    job = lib.candidate_generator.submit("Masmorra", "masmorra", "rol", 3)
    lib.candidate_generator._worker.join(timeout=10)
    assert job.finished and job.done == 3 and job.error is None
    candidates = lib.list_candidates()
    assert len(candidates) == 3 and {c["theme"] for c in candidates} == {"Masmorra"}
    kept = lib.approve_candidate(candidates[0]["id"])
    assert kept.parent == lib.library_dir().resolve() and kept.name.startswith("masmorra-masmorra-")
    meta = json.loads(kept.with_suffix(".png.json").read_text())
    assert meta["model"] == "FLUX.1 schnell" and meta["prompt"] == "Masmorra scene"
    lib.discard_candidate(candidates[1]["id"])
    assert [c["id"] for c in lib.list_candidates()] == [candidates[2]["id"]]
    assert len([g for g in lib.library() if g["theme"] == "Masmorra"][0]["items"]) == 1
    with pytest.raises(ValueError):
        lib.approve_candidate("../../etc")
    with pytest.raises(ValueError):
        lib.candidate_generator.submit("Masmorra", "masmorra", "rol", 40)


def test_import_checks_size_orientation_and_source(dirs):
    with pytest.raises(ValueError, match="massa xicoteta"):
        lib.import_uploaded(jpeg_bytes((1280, 720)), "a.jpg", "Bosc", "pexels", "https://pexels.com/p/1", "")
    with pytest.raises(ValueError, match="horitzontal"):
        lib.import_uploaded(jpeg_bytes((1080, 1920)), "a.jpg", "Bosc", "pexels", "https://pexels.com/p/1", "")
    with pytest.raises(ValueError, match="enllaç"):
        lib.import_uploaded(jpeg_bytes((1920, 1080)), "a.jpg", "Bosc", "unsplash", "", "")
    with pytest.raises(ValueError, match="imatge vàlida"):
        lib.import_uploaded(b"not an image", "a.jpg", "Bosc", "propia", "", "")
    path = lib.import_uploaded(jpeg_bytes((2400, 1350)), "forest.jpg", "Bosc", "pexels", "https://www.pexels.com/photo/123", "Ana")
    assert path.name.startswith("bosc-importat-") and path.suffix == ".jpg"
    meta = json.loads(path.with_suffix(".jpg.json").read_text())
    assert meta["license"] == "Pexels License" and "pexels.com/photo/123" in meta["source_notes"] and "Ana" in meta["source_notes"]
    lib.delete_background(path.name)
    assert not path.exists() and not path.with_suffix(".jpg.json").exists()
    with pytest.raises(ValueError):
        lib.delete_background("../secret.png")


def test_automatic_mode_prefers_library_and_avoids_recent(dirs, monkeypatch):
    root = lib.library_dir()
    for n in range(3):
        png(root / f"bosc-0{n}.png")
    monkeypatch.setattr(auto, "forge_ready", lambda: True)
    monkeypatch.setattr(auto, "_generate_background", lambda *a: pytest.fail("no s'havia de generar"))
    picks = {auto.choose_background("Bosc", "bosc", random.Random(seed), recent={"bosc-00.png", "bosc-01.png"})[0].name for seed in range(10)}
    assert picks == {"bosc-02.png"}
    generated = []
    monkeypatch.setattr(auto, "_generate_background", lambda *a: generated.append(a) or png(root / "bosc-nou.png"))
    path, note = auto.choose_background("Bosc", "bosc", random.Random(0), force_new=True)
    assert path.name == "bosc-nou.png" and "sense revisar" in note and generated


def test_library_page_and_api(dirs, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(lib, "forge_ready", lambda: False)
    with TestClient(main.app) as client:
        page = client.get("/fons")
        assert page.status_code == 200 and "Biblioteca de fons" in page.text and "Forge no està obert" in page.text
        assert client.post("/api/fons/generar", data={"theme": "Bosc", "environment": "bosc"}).status_code == 409
        monkeypatch.setattr(lib, "forge_ready", lambda: True)
        monkeypatch.setattr("app.services.library_web.forge_profile", lambda: None)
        assert client.post("/api/fons/generar", data={"theme": "Inventat", "environment": "bosc"}).status_code == 400
        assert client.post("/api/fons/generar", data={"theme": "Bosc", "environment": "bosc", "count": "2"}).status_code == 202
        lib.candidate_generator._worker.join(timeout=10)
        status = client.get("/api/fons").json()
        assert len(status["candidates"]) == 2
        first = status["candidates"][0]
        assert client.get(first["image_url"]).headers["content-type"] == "image/png"
        assert client.post(f"/api/fons/opcions/{first['id']}/guardar").status_code == 201
        assert client.post(f"/api/fons/opcions/{first['id']}/guardar").status_code == 404
        upload = client.post("/fons/importar", data={"theme": "Bosc", "license": "pixabay", "source_url": "https://pixabay.com/x"},
                             files={"image": ("bosc.jpg", jpeg_bytes((1920, 1080)), "image/jpeg")}, follow_redirects=False)
        assert upload.status_code == 303 and "ok=" in upload.headers["location"]
        assert "bosc-importat-" in client.get("/fons").text
        home = client.get("/")
        assert "Biblioteca de fons" in home.text and "2 fons" in home.text


def test_automatic_mode_prefers_backgrounds_made_for_the_same_format_and_environment(dirs):
    root = lib.library_dir()
    for name, fmt, env in (("bosc-a", "pomodoro", "bosc"), ("bosc-b", "dormir", "nit"), ("bosc-c", "dormir", "bosc"), ("bosc-d", None, None)):
        png(root / f"{name}.png")
        if fmt:
            (root / f"{name}.png.json").write_text(json.dumps({"generation": {"format": fmt, "environment": env}}))
    pick = lambda env, fmt: {auto.choose_background("Bosc", env, random.Random(s), fmt)[0].name for s in range(12)}
    assert pick("bosc", "dormir") == {"bosc-c.png"}
    assert pick("nit", "dormir") == {"bosc-b.png"}
    assert pick("pluja", "dormir") == {"bosc-b.png", "bosc-c.png"}
    assert pick("bosc", "rol") == {"bosc-a.png", "bosc-c.png"}
    assert pick("vent", "rol") == {"bosc-a.png", "bosc-b.png", "bosc-c.png", "bosc-d.png"}
