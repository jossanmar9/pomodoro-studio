"""Constructor de prompts visuals originals per a ambientacions.

No depén de cap proveïdor d'IA. Genera text reutilitzable en eines locals,
serveis externs o fluxos manuals.
"""
from dataclasses import dataclass
import re

FORBIDDEN_REFERENCES = {
    "harry potter", "hogwarts", "lord of the rings", "middle earth", "mordor",
    "star wars", "star trek", "marvel", "dc comics", "game of thrones",
    "zelda", "pokemon", "disney", "pixar", "studio ghibli", "ghibli",
}

BASE_PRESETS = {
    "library": ("grand old library", "warm reading room with tall shelves, wooden desks and subtle lived-in details"),
    "cabin": ("remote cozy cabin", "quiet wooden interior, large window, simple desk and shelter from the weather"),
    "observatory": ("isolated night observatory", "astronomy instruments, dark sky, practical workspace and distant stars"),
    "forest": ("ancient tranquil forest", "deep woodland clearing, moss, layered vegetation and a small study nook"),
    "tavern": ("old roadside tavern", "wooden tables, hearth, handmade objects and a calm corner for reading"),
    "spaceship": ("deep-space research station", "functional observation room, restrained technology, distant planets and quiet work area"),
}

@dataclass(frozen=True)
class AmbiencePromptSpec:
    subject: str
    era: str = "timeless"
    place: str = ""
    time_of_day: str = "evening"
    weather: str = "calm"
    lighting: str = "soft cinematic practical lighting"
    atmosphere: str = "quiet, immersive, focused, cozy"
    visual_style: str = "cinematic environmental concept art"
    details: str = ""
    aspect_ratio: str = "16:9"

@dataclass(frozen=True)
class AmbiencePrompt:
    positive: str
    negative: str
    warnings: tuple[str, ...]


def detect_restricted_references(text: str) -> tuple[str, ...]:
    lowered = text.casefold()
    return tuple(sorted(name for name in FORBIDDEN_REFERENCES if name in lowered))


def _clean(value: str, max_length: int = 240) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    return value[:max_length]


def validate_spec(spec: AmbiencePromptSpec) -> list[str]:
    errors: list[str] = []
    if not _clean(spec.subject):
        errors.append("El tema visual és obligatori")
    if spec.aspect_ratio not in {"16:9", "1:1", "9:16"}:
        errors.append("Relació d'aspecte no admesa")
    combined = " ".join((spec.subject, spec.place, spec.visual_style, spec.details))
    refs = detect_restricted_references(combined)
    if refs:
        errors.append("Usa una descripció original sense referències directes a franquícies: " + ", ".join(refs))
    return errors


def build_prompt(spec: AmbiencePromptSpec) -> AmbiencePrompt:
    errors = validate_spec(spec)
    if errors:
        raise ValueError("; ".join(errors))
    parts = [
        _clean(spec.subject),
        _clean(spec.place),
        f"era: {_clean(spec.era)}",
        f"time: {_clean(spec.time_of_day)}",
        f"weather: {_clean(spec.weather)}",
        f"lighting: {_clean(spec.lighting)}",
        f"atmosphere: {_clean(spec.atmosphere)}",
        f"visual style: {_clean(spec.visual_style)}",
        _clean(spec.details),
        f"composition for {spec.aspect_ratio}, wide environmental shot, strong depth, clear focal area, suitable as a long focus-video background",
        "original worldbuilding, generic architecture and props, no recognisable copyrighted characters or brands",
    ]
    positive = ", ".join(part for part in parts if part)
    negative = (
        "text, captions, subtitles, logos, watermarks, signatures, UI, brand marks, "
        "recognisable copyrighted characters, franchise emblems, celebrity likenesses, "
        "busy foreground, distorted architecture, duplicate objects, low detail, low resolution"
    )
    return AmbiencePrompt(positive=positive, negative=negative, warnings=())


def build_from_preset(preset: str, **overrides) -> AmbiencePrompt:
    if preset not in BASE_PRESETS:
        raise ValueError("Preset d'ambientació no vàlid")
    subject, details = BASE_PRESETS[preset]
    data = {"subject": subject, "details": details}
    data.update({key: value for key, value in overrides.items() if value not in (None, "")})
    return build_prompt(AmbiencePromptSpec(**data))
