import json
from pathlib import Path
import pytest

from app.services.ambience_assets import AssetProvenance, import_background, safe_asset_name


def test_safe_asset_name():
    assert safe_asset_name("Biblioteca Plujosa 01") == "biblioteca-plujosa-01"


def test_import_background_copies_and_records_provenance(tmp_path: Path):
    source = tmp_path / "generated.png"
    source.write_bytes(b"png")
    assets = tmp_path / "assets"
    image, metadata = import_background(
        source,
        assets,
        "Observatori nocturn",
        AssetProvenance(prompt="night observatory", provider="local", model="test-model", license="owned"),
    )
    assert image.name == "observatori-nocturn.png"
    assert image.read_bytes() == b"png"
    data = json.loads(metadata.read_text(encoding="utf-8"))
    assert data["asset"] == image.name
    assert data["prompt"] == "night observatory"
    assert data["provider"] == "local"


def test_import_rejects_unknown_format(tmp_path: Path):
    source = tmp_path / "generated.exe"
    source.write_bytes(b"x")
    with pytest.raises(ValueError, match="Format"):
        import_background(source, tmp_path / "assets", "test", AssetProvenance(prompt="x"))


def test_import_does_not_overwrite(tmp_path: Path):
    source = tmp_path / "generated.jpg"
    source.write_bytes(b"jpg")
    assets = tmp_path / "assets"
    provenance = AssetProvenance(prompt="x")
    import_background(source, assets, "same", provenance)
    with pytest.raises(ValueError, match="existeix"):
        import_background(source, assets, "same", provenance)
