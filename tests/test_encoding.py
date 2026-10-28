from app.services import encoding
from app.services.encoding import EncodingOptions, select_encoding


def test_auto_uses_nvenc_when_available():
    plan = select_encoding(EncodingOptions("auto", "balanced"), has_nvenc=True)
    assert plan.engine == "nvenc"
    assert "h264_nvenc" in plan.video_args


def test_auto_falls_back_to_cpu_without_nvenc():
    plan = select_encoding(EncodingOptions("auto", "balanced"), has_nvenc=False)
    assert plan.engine == "cpu"
    assert "libx264" in plan.video_args


def test_explicit_nvenc_falls_back_safely_when_unavailable():
    plan = select_encoding(EncodingOptions("nvenc", "quality"), has_nvenc=False)
    assert plan.requested_engine == "nvenc"
    assert plan.engine == "cpu"
    assert "-crf" in plan.video_args


def test_quality_profiles_change_encoder_arguments():
    fast = select_encoding(EncodingOptions("cpu", "fast"), has_nvenc=False)
    quality = select_encoding(EncodingOptions("cpu", "quality"), has_nvenc=False)
    assert fast.video_args != quality.video_args
    assert "fast" in fast.video_args
    assert "slow" in quality.video_args


def test_nvenc_detection_is_cached(monkeypatch):
    calls = 0

    def fake_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return type("Result", (), {"returncode": 0, "stdout": " h264_nvenc "})()
        return type("Result", (), {"returncode": 0, "stdout": ""})()

    encoding.clear_encoding_cache()
    monkeypatch.setattr(encoding.subprocess, "run", fake_run)
    assert encoding.nvenc_available()
    assert encoding.nvenc_available()
    assert calls == 2
    encoding.clear_encoding_cache()
