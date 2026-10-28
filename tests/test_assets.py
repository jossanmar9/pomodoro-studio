from pathlib import Path
import pytest
from app.services import assets


def test_resolve_asset_accepts_existing_file(tmp_path, monkeypatch):
    root=tmp_path/'assets'; folder=root/'backgrounds'; folder.mkdir(parents=True); target=folder/'scene.jpg'; target.write_bytes(b'x')
    monkeypatch.setattr(assets.settings,'assets_dir',root)
    assert assets.resolve_asset('backgrounds','scene.jpg') == target.resolve()


def test_resolve_asset_blocks_traversal(tmp_path, monkeypatch):
    root=tmp_path/'assets'; (root/'backgrounds').mkdir(parents=True); (tmp_path/'secret.jpg').write_bytes(b'x')
    monkeypatch.setattr(assets.settings,'assets_dir',root)
    with pytest.raises(ValueError): assets.resolve_asset('backgrounds','../secret.jpg')


def test_resolve_asset_rejects_unknown_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(assets.settings,'assets_dir',tmp_path)
    with pytest.raises(ValueError): assets.resolve_asset('other','x.jpg')
