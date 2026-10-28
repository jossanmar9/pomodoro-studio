from pathlib import Path

import pytest

from app.services import assets


def test_resolve_asset_accepts_existing_file(tmp_path, monkeypatch):
    root = tmp_path / "assets"
    folder = root / "backgrounds"
    folder.mkdir(parents=True)
    target = folder / "scene.jpg"
    target.write_bytes(b"x")
    monkeypatch.setattr(assets.settings, "assets_dir", root)
    assert assets.resolve_asset("backgrounds", "scene.jpg") == target.resolve()


def test_resolve_asset_blocks_traversal(tmp_path, monkeypatch):
    root = tmp_path / "assets"
    (root / "backgrounds").mkdir(parents=True)
    (tmp_path / "secret.jpg").write_bytes(b"x")
    monkeypatch.setattr(assets.settings, "assets_dir", root)
    with pytest.raises(ValueError):
        assets.resolve_asset("backgrounds", "../secret.jpg")


def test_resolve_asset_rejects_nested_path_even_if_file_exists(tmp_path, monkeypatch):
    root = tmp_path / "assets"
    nested = root / "backgrounds" / "nested"
    nested.mkdir(parents=True)
    (nested / "scene.jpg").write_bytes(b"x")
    monkeypatch.setattr(assets.settings, "assets_dir", root)
    with pytest.raises(ValueError):
        assets.resolve_asset("backgrounds", "nested/scene.jpg")


def test_resolve_asset_rejects_wrong_suffix_for_kind(tmp_path, monkeypatch):
    root = tmp_path / "assets"
    folder = root / "backgrounds"
    folder.mkdir(parents=True)
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(assets.settings, "assets_dir", root)
    with pytest.raises(ValueError):
        assets.resolve_asset("backgrounds", "notes.txt")


def test_resolve_asset_rejects_unknown_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(assets.settings, "assets_dir", tmp_path)
    with pytest.raises(ValueError):
        assets.resolve_asset("other", "x.jpg")
