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
    return SimpleNamespace(root=tmp_path)


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
    mine = lib.import_uploaded(jpeg_bytes((1920, 1080)), "nook.png", "Racó de lectura", "chatgpt", "", "", "llegir", "pluja")
    assert mine.name.startswith("raco-de-lectura-pluja-llegir-")
    meta = json.loads(mine.with_suffix(mine.suffix + ".json").read_text())
    assert meta["license"] == "Generat amb ChatGPT (OpenAI)" and meta["generation"]["format"] == "llegir"
    item = [g for g in lib.library() if g["theme"] == "Racó de lectura"][0]["items"][0]
    assert item["format"] == "llegir" and item["environment"] == "pluja"
    with pytest.raises(ValueError, match="Entorn"):
        lib.import_uploaded(jpeg_bytes((1920, 1080)), "a.jpg", "Bosc", "chatgpt", "", "", "", "inventat")


def test_automatic_mode_prefers_library_and_avoids_recent(dirs, monkeypatch):
    root = lib.library_dir()
    for n in range(3):
        png(root / f"bosc-0{n}.png")
    picks = {auto.choose_background("Bosc", "bosc", random.Random(seed), recent={"bosc-00.png", "bosc-01.png"})[0].name for seed in range(10)}
    assert picks == {"bosc-02.png"}
    path, note = auto.choose_background("Bosc", "bosc", random.Random(0), chosen="bosc-00.png", recent={"bosc-00.png"})
    assert path.name == "bosc-00.png" and note == "Fons triat a mà"
    path, note = auto.choose_background("Bosc", "bosc", random.Random(0), chosen="esborrat.png")
    assert path.name.startswith("bosc-0") and "ja no existeix" in note
    with pytest.raises(auto.AutopilotError, match="Biblioteca de fons"):
        auto.choose_background("Masmorra", "masmorra", random.Random(0))


def test_library_page_and_api(dirs, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
    with TestClient(main.app) as client:
        page = client.get("/fons")
        assert page.status_code == 200 and "Biblioteca de fons" in page.text and "Forge" not in page.text
        assert client.post("/api/fons/generar", data={"theme": "Bosc", "environment": "bosc"}).status_code in (404, 405)
        png(lib.library_dir() / "bosc-a.png")
        upload = client.post("/fons/importar", data={"theme": "Bosc", "license": "pixabay", "source_url": "https://pixabay.com/x"},
                             files={"image": ("bosc.jpg", jpeg_bytes((1920, 1080)), "image/jpeg")}, follow_redirects=False)
        assert upload.status_code == 303 and "ok=" in upload.headers["location"]
        assert "bosc-importat-" in client.get("/fons").text
        home = client.get("/")
        assert "Biblioteca de fons" in home.text and "2 fons" in home.text and "Forge" not in home.text
        assert "/assets/backgrounds/bosc-a.png" in home.text


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
