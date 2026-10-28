import pytest
from fastapi import HTTPException

from app.main import validate_project_config
from app.models import Preset


def test_valid_project_config():
    validate_project_config("Biblioteca medieval", 25, 5, 120, "1920x1080")


def test_invalid_resolution():
    with pytest.raises(HTTPException) as exc:
        validate_project_config("Biblioteca medieval", 25, 5, 120, "800x600")
    assert exc.value.status_code == 400


def test_invalid_limits():
    with pytest.raises(HTTPException):
        validate_project_config("Biblioteca medieval", 0, 5, 120, "1920x1080")


def test_preset_keeps_project_configuration():
    preset = Preset(name="Estudi", theme="Biblioteca medieval", focus_minutes=50, break_minutes=10, duration_minutes=180, resolution="2560x1440")
    assert preset.name == "Estudi"
    assert preset.focus_minutes == 50
    assert preset.break_minutes == 10
    assert preset.duration_minutes == 180
    assert preset.resolution == "2560x1440"
