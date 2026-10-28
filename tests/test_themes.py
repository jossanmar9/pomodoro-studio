from app.services.timer import build_chapters, build_timeline
from app.themes import publication_theme


def test_publication_theme_is_international():
    assert publication_theme("Biblioteca medieval") == "Medieval Library"


def test_chapters_can_be_generated_in_english():
    timeline = build_timeline(25, 5, 60)
    chapters = build_chapters(timeline, language="en")
    assert chapters.startswith("00:00:00 Focus session 1")
    assert "00:25:00 Break" in chapters


def test_chapters_default_to_valencian():
    timeline = build_timeline(25, 5, 30)
    assert build_chapters(timeline).startswith("00:00:00 Sessió 1")
