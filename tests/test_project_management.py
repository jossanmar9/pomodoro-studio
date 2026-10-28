from pathlib import Path

import pytest
from fastapi import HTTPException

from app.main import output_file
from app.models import Project


def test_output_file_only_allows_known_generated_files(tmp_path: Path):
    (tmp_path / "title.txt").write_text("Focus", encoding="utf-8")
    project = Project(theme="Bosc", output_path=str(tmp_path))
    assert output_file(project, "title.txt") == (tmp_path / "title.txt").resolve()


def test_output_file_rejects_unknown_filename(tmp_path: Path):
    (tmp_path / "secret.txt").write_text("no", encoding="utf-8")
    project = Project(theme="Bosc", output_path=str(tmp_path))
    with pytest.raises(HTTPException) as exc:
        output_file(project, "secret.txt")
    assert exc.value.status_code == 404


def test_output_file_rejects_missing_output_path():
    project = Project(theme="Bosc", output_path=None)
    with pytest.raises(HTTPException):
        output_file(project, "video.mp4")
