from pathlib import Path
import pytest

from app.services.ambience_prompt import AmbiencePrompt
from app.services.image_providers import (
    GeneratedImage, ImageGenerationRequest, available_providers,
    get_provider, provider_names, register_provider,
)

class FakeProvider:
    name = "fake-test-provider"
    def available(self): return True
    def generate(self, request):
        return GeneratedImage(Path("fake.png"), self.name, "fake-model")


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
