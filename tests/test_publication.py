import json
import zipfile
from pathlib import Path

from app.services.metadata import PublicationDraft, build_publication_zip, default_publication, validate_publication, write_publication_files
from app.services.timer import build_timeline


def test_default_publication_is_ready_for_youtube():
    timeline = build_timeline(25, 5, 120)
    draft = default_publication(theme="Bosc", focus=25, pause=5, duration=120, timeline=timeline)
    assert draft.title
    assert len(draft.title) <= 100
    assert draft.chapters.startswith("00:00:00")
    assert "pomodoro" in draft.tags.lower()
    assert validate_publication(draft) == []


def test_validation_accepts_supported_zero_timestamps():
    for chapters in ("0:00 Focus", "00:00 Focus", "00:00:00 Focus"):
        draft = PublicationDraft("Focus", "Description", chapters, "pomodoro", "en")
        assert validate_publication(draft) == []


def test_validation_rejects_limits_and_bad_chapters():
    draft = PublicationDraft("x" * 101, "x" * 5001, "01:00 Too late", "x" * 501, "xx")
    errors = validate_publication(draft)
    assert len(errors) == 5


def test_validation_requires_chapters():
    draft = PublicationDraft("Focus", "Description", "", "pomodoro", "en")
    assert "Els capítols són obligatoris" in validate_publication(draft)


def test_write_publication_files_keeps_editable_values(tmp_path: Path):
    draft = PublicationDraft("My title", "My description", "0:00 Focus", "pomodoro, focus", "en")
    write_publication_files(tmp_path, draft, {"tema": "Bosc"})
    assert (tmp_path / "title.txt").read_text(encoding="utf-8").strip() == "My title"
    assert (tmp_path / "tags.txt").read_text(encoding="utf-8").strip() == "pomodoro, focus"
    data = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert data["title"] == "My title"
    assert data["tags"] == ["pomodoro", "focus"]


def test_publication_zip_only_adds_existing_known_files(tmp_path: Path):
    (tmp_path / "title.txt").write_text("Focus", encoding="utf-8")
    (tmp_path / "thumbnail.jpg").write_bytes(b"jpg")
    (tmp_path / "secret.txt").write_text("no", encoding="utf-8")
    archive = build_publication_zip(tmp_path)
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
    assert "title.txt" in names
    assert "thumbnail.jpg" in names
    assert "secret.txt" not in names
