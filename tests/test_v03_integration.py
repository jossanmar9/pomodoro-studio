from pathlib import Path

import pytest
from fastapi import HTTPException

from app.main import output_file, validate_project_config
from app.models import Preset, Project


def test_project_can_be_duplicated_as_clean_draft():
    source = Project(theme="Bosc", focus_minutes=50, break_minutes=10, duration_minutes=180, resolution="2560x1440", status="COMPLETED", output_path="/tmp/old")
    duplicate = Project(theme=source.theme, focus_minutes=source.focus_minutes, break_minutes=source.break_minutes, duration_minutes=source.duration_minutes, resolution=source.resolution)
    assert duplicate.theme == source.theme
    assert duplicate.focus_minutes == 50
    assert duplicate.break_minutes == 10
    assert duplicate.duration_minutes == 180
    assert duplicate.resolution == "2560x1440"
    assert duplicate.output_path is None


def test_preset_preserves_project_configuration():
    preset = Preset(name="Profund", theme="Bosc", focus_minutes=50, break_minutes=10, duration_minutes=120, resolution="1920x1080")
    validate_project_config(preset.theme, preset.focus_minutes, preset.break_minutes, preset.duration_minutes, preset.resolution)


def test_validation_rejects_invalid_resolution():
    with pytest.raises(HTTPException) as exc:
        validate_project_config("Bosc", 25, 5, 120, "800x600")
    assert exc.value.status_code == 400


def test_generated_output_is_resolved_inside_project_folder(tmp_path: Path):
    folder = tmp_path / "project-1"
    folder.mkdir()
    (folder / "metadata.json").write_text("{}", encoding="utf-8")
    project = Project(theme="Bosc", output_path=str(folder))
    resolved = output_file(project, "metadata.json")
    assert resolved == (folder / "metadata.json").resolve()
    assert resolved.parent == folder.resolve()
