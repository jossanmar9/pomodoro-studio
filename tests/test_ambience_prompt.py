import pytest

from app.services.ambience_prompt import (
    AmbiencePromptSpec,
    BASE_PRESETS,
    build_from_preset,
    build_prompt,
    detect_restricted_references,
)


def test_build_prompt_contains_scene_and_format():
    prompt = build_prompt(AmbiencePromptSpec(
        subject="rainy mountain reading room",
        era="late nineteenth century inspired",
        weather="heavy rain outside",
        lighting="warm lamps and cool window light",
    ))
    assert "rainy mountain reading room" in prompt.positive
    assert "composition for 16:9" in prompt.positive
    assert "logos" in prompt.negative


def test_presets_are_provider_independent():
    assert {"library", "cabin", "observatory", "forest", "tavern", "spaceship"} <= set(BASE_PRESETS)
    prompt = build_from_preset("observatory", time_of_day="midnight")
    assert "midnight" in prompt.positive
    assert "observatory" in prompt.positive


def test_rejects_direct_franchise_reference():
    spec = AmbiencePromptSpec(subject="library at Hogwarts")
    with pytest.raises(ValueError, match="franquícies"):
        build_prompt(spec)


def test_detects_reference_case_insensitively():
    assert "star wars" in detect_restricted_references("A STAR WARS style station")


def test_rejects_invalid_aspect_ratio():
    with pytest.raises(ValueError, match="Relació"):
        build_prompt(AmbiencePromptSpec(subject="forest study room", aspect_ratio="4:3"))
