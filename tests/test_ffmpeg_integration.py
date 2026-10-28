import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.renderer import RenderSpec, build_ffmpeg_command
from app.services.timer import SegmentType, TimelineSegment, TimelineSummary


pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg no està instal·lat")


def test_real_ffmpeg_render_creates_short_mp4(tmp_path: Path):
    background = tmp_path / "background.png"
    output = tmp_path / "video.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x203040:s=640x360:d=1",
        "-frames:v", "1", str(background),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    segment = TimelineSegment(SegmentType.FOCUS, 1, 0, 2)
    timeline = TimelineSummary([segment], 1, 2, 0, 2)
    command = build_ffmpeg_command(RenderSpec(background, output, "640x360", timeline, fps=10))
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)

    assert result.returncode == 0, result.stderr + result.stdout
    assert output.exists()
    assert output.stat().st_size > 0
