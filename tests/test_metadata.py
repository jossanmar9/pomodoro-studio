from app.services.metadata import slugify, write_metadata
from app.services.timer import build_timeline


def test_slugify_handles_accents():
    assert slugify("Biblioteca màgica") == "biblioteca-magica"


def test_metadata_publication_is_english(tmp_path):
    timeline = build_timeline(25, 5, 30)
    write_metadata(
        tmp_path,
        theme="Biblioteca medieval",
        focus=25,
        pause=5,
        duration=30,
        resolution="1920x1080",
        timeline=timeline,
    )
    assert "Medieval Library" in (tmp_path / "title.txt").read_text(encoding="utf-8")
    assert "Focus session 1" in (tmp_path / "chapters.txt").read_text(encoding="utf-8")
    assert "Contingut original" not in (tmp_path / "description.txt").read_text(encoding="utf-8")
