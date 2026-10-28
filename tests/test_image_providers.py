import base64
from pathlib import Path
import pytest

from app.services.ambience_prompt import AmbiencePrompt
from app.services.image_providers import (
    A1111ImageProvider, GeneratedImage, ImageGenerationRequest, available_providers,
    configure_a1111, get_provider, provider_names, register_provider,
)


class FakeProvider:
    name = "fake-test-provider"
    def available(self): return True
    def generate(self, request):
        return GeneratedImage(Path("fake.png"), self.name, "fake-model")


class FakeResponse:
    status_code = 200
    def raise_for_status(self): return None
    def json(self):
        return {"images": [base64.b64encode(b"fake-png").decode()], "info": "ok"}


def test_manual_provider_is_always_present():
    assert "manual" in provider_names()
    assert "manual" in available_providers()


def test_manual_provider_does_not_generate():
    req = ImageGenerationRequest(AmbiencePrompt("scene", "text", ()))
    with pytest.raises(RuntimeError, match="mode manual"):
        get_provider("manual").generate(req)


def test_optional_provider_can_be_registered():
    register_provider(FakeProvider())
    assert "fake-test-provider" in available_providers()
    result = get_provider("fake-test-provider").generate(ImageGenerationRequest(AmbiencePrompt("scene", "", ())))
    assert result.model == "fake-model"


def test_a1111_generation_writes_returned_image(tmp_path, monkeypatch):
    calls = {}
    def fake_post(url, json, timeout):
        calls.update(url=url, json=json, timeout=timeout)
        return FakeResponse()
    monkeypatch.setattr("app.services.image_providers.httpx.post", fake_post)
    provider = A1111ImageProvider("http://127.0.0.1:7860", "model.safetensors")
    result = provider.generate(ImageGenerationRequest(
        AmbiencePrompt("original library", "logos", ()),
        width=1024, height=576, output_dir=tmp_path,
    ))
    assert result.path.read_bytes() == b"fake-png"
    assert result.provider == "a1111"
    assert result.model == "model.safetensors"
    assert calls["json"]["prompt"] == "original library"
    assert calls["json"]["negative_prompt"] == "logos"
    assert calls["json"]["override_settings"]["sd_model_checkpoint"] == "model.safetensors"


def test_a1111_requires_output_directory():
    provider = A1111ImageProvider("http://127.0.0.1:7860")
    with pytest.raises(ValueError, match="carpeta"):
        provider.generate(ImageGenerationRequest(AmbiencePrompt("scene", "", ()), output_dir=None))


def test_configure_a1111_is_optional():
    configure_a1111("http://127.0.0.1:7860")
    assert "a1111" in provider_names()
    configure_a1111("")
    assert "a1111" not in provider_names()
