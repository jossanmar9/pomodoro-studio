from app.services.metadata import slugify

def test_slugify_is_filesystem_friendly():
    assert slugify("Biblioteca Medieval!") == "biblioteca-medieval"

def test_slugify_has_fallback():
    assert slugify("***") == "pomodoro"
