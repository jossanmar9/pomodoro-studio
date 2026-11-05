import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    """Les proves mai escriuen còpies de seguretat en la carpeta personal."""
    monkeypatch.setattr(settings, "backup_dir", tmp_path / "copies")
