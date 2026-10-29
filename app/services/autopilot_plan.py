"""Decisions del mode automàtic que no depenen de la base de dades ni de la web.

Tot el que es pot decidir abans de renderitzar viu ací: quin fons, quins sons,
quina música, amb quin volum i amb quins crèdits. Així es pot provar sense
FFmpeg, sense Forge i sense YouTube.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import random
import re
import subprocess
import unicodedata

from app.services.ambience_prompt import AmbiencePromptSpec
from app.services.renderer import SUPPORTED_AUDIO_SUFFIXES, SUPPORTED_IMAGE_SUFFIXES, SUPPORTED_VIDEO_SUFFIXES

CHANNEL_NAME = "The Amber Window"

# Sonoritat objectiu (LUFS). La música i els efectes es normalitzen perquè cap
# pista tape les altres, independentment de com s'haja gravat cada fitxer.
MUSIC_LOUDNESS = -22.0
PRIMARY_AMBIENCE_LOUDNESS = -26.0
SECONDARY_AMBIENCE_LOUDNESS = -31.0
MUSIC_CROSSFADE_SECONDS = 6


@dataclass(frozen=True)
class Environment:
    label: str
    public_label: str
    time_of_day: str
    weather: str
    lighting: str
    # Cada capa és una llista de fitxers candidats; se'n tria un per capa.
    layers: tuple[tuple[str, ...], ...] = ()
    music: bool = True


ENVIRONMENTS: dict[str, Environment] = {
    "pluja": Environment(
        "Pluja suau", "Gentle Rain", "late evening", "steady gentle rain against the windows",
        "warm candlelight and soft lamp glow, cool blue light from rainy windows",
        (("pluja-terrassa", "pluja-pedra", "pluja-bassal", "pluja-lona"),),
    ),
    "tempesta": Environment(
        "Tempesta", "Thunderstorm", "night", "heavy rain and a distant thunderstorm",
        "warm interior light contrasted with dark stormy windows, occasional faint lightning glow",
        (("pluja-tempesta-35min", "pluja-trons", "pluja-tenda"),),
    ),
    "llar": Environment(
        "Llar de foc", "Crackling Fireplace", "night", "calm and dry",
        "warm amber glow from a crackling fireplace, deep cozy shadows",
        (("foc-llar", "foc-llar-04", "foc-llar-oberta", "foc-llar-05"),),
    ),
    "pluja-llar": Environment(
        "Pluja i llar de foc", "Rain & Fireplace", "late evening", "soft rain outside the windows",
        "warm amber fireplace glow with cool rainy window light",
        (("pluja-terrassa", "pluja-pedra", "pluja-bassal"), ("foc-llar", "foc-llar-04", "foc-llar-oberta")),
    ),
    "nit": Environment(
        "Nit tranquil·la", "Quiet Night", "deep night", "clear and still, starry sky",
        "moonlight and a few warm practical lights",
        (("nit-grills-granotes", "camp-nit"),),
    ),
    "bosc": Environment(
        "Bosc i ocells", "Forest Birdsong", "early morning", "fresh and calm with light mist",
        "soft golden morning sunlight filtering through leaves",
        (("bosc-02", "vora-bosc", "bosc-04", "bosc-ocells"),),
    ),
    "rierol": Environment(
        "Rierol de muntanya", "Mountain Stream", "afternoon", "calm, a stream flowing nearby",
        "soft natural daylight",
        (("rierol-muntanya", "bosc-rierol-01", "bosc-rierol-03", "torrent-muntanya"),),
    ),
    "mar": Environment(
        "Mar i ones", "Ocean Waves", "sunset", "calm sea breeze, waves visible in the distance",
        "warm sunset light over the water",
        (("ones-ocea", "ones-escuma-platja", "mar-agitada"),),
    ),
    "vent": Environment(
        "Vent", "Howling Wind", "evening", "strong wind outside, cold weather",
        "warm sheltered interior light against a cold grey sky",
        (("vent-des-de-dins", "vent-arbres", "vent-arbre"),),
    ),
    "musica": Environment(
        "Només música", "Calm Music", "evening", "calm",
        "soft cinematic practical lighting",
        (),
    ),
}


# Descripció visual original de cada ambientació (sense franquícies).
THEME_VISUALS: dict[str, tuple[str, str, str]] = {
    "Biblioteca medieval": ("vast medieval monastery library", "stone arches, oak reading desks, candles, parchment scrolls and leather-bound books", "medieval"),
    "Biblioteca màgica": ("enchanted wizard library", "towering curved bookshelves, floating candles, glowing runes, brass astrolabes and potion bottles", "fantasy"),
    "Biblioteca èlfica": ("ancient elven library inside living trees", "carved wooden balconies, vines, lanterns, elegant curved architecture and scrolls", "fantasy"),
    "Taverna medieval": ("quiet medieval tavern corner", "wooden beams, tankards, a hearth, handmade furniture and a reading nook", "medieval"),
    "Torre de l'alquimista": ("alchemist tower study", "glass flasks, copper instruments, old books, herbs drying and a round window", "medieval fantasy"),
    "Castell gòtic": ("gothic castle study hall", "tall pointed windows, stone columns, candelabras, tapestries and a large desk", "gothic"),
    "Cabana amb pluja": ("cozy wooden cabin interior", "large window, simple desk with books, blankets, plants and a mug of tea", "timeless"),
    "Biblioteca victoriana": ("victorian private library", "mahogany shelves, green banker lamps, leather armchairs and a rolling ladder", "victorian"),
    "Vaixell pirata": ("captain's cabin aboard an old wooden sailing ship", "nautical maps, lanterns, brass compass, wooden chests and stern windows", "age of sail"),
    "Roma antiga": ("ancient roman scholar's villa study", "marble columns, scrolls, oil lamps, mosaic floor and an atrium view", "ancient rome"),
    "Grècia antiga": ("ancient greek philosopher's study overlooking the sea", "white marble, scrolls, olive trees, clay amphorae and oil lamps", "ancient greece"),
    "Japó feudal": ("traditional japanese study room", "tatami floor, shoji screens, low writing desk, paper lanterns and a zen garden view", "feudal japan"),
    "Nau espacial": ("deep-space research station observation room", "large viewport with distant planets, clean workstations and soft ambient panels", "far future"),
    "Búnquer postapocalíptic": ("cozy underground survival bunker workspace", "salvaged furniture, warm work lamps, shelves of supplies, maps and old books", "post-apocalyptic"),
    "Bosc": ("small study nook in an ancient tranquil forest", "moss, giant tree roots, a wooden desk, lanterns and layered vegetation", "timeless"),
    "Observatori": ("old astronomy observatory", "large brass telescope, star charts, open dome showing the night sky and a desk", "timeless"),
    "Cafeteria acollidora": ("cozy coffee shop corner", "warm wooden tables, plants, books, steaming coffee and a large window", "modern"),
}

AUTO_THEMES = tuple(THEME_VISUALS)
DURATION_CHOICES = (60, 120, 180, 240, 480)
POMODORO_CHOICES = {"25/5": (25, 5), "50/10": (50, 10)}
PRIVACY_CHOICES = {"public": "Públic", "unlisted": "Ocult (amb enllaç)", "private": "Privat"}


def slugify(text: str) -> str:
    normal = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", normal).strip("-")


def prompt_spec(theme: str, environment: str) -> AmbiencePromptSpec:
    if theme not in THEME_VISUALS:
        raise ValueError("Ambientació no disponible en el mode automàtic")
    if environment not in ENVIRONMENTS:
        raise ValueError("Entorn no vàlid")
    subject, details, era = THEME_VISUALS[theme]
    env = ENVIRONMENTS[environment]
    return AmbiencePromptSpec(
        subject=subject, era=era, time_of_day=env.time_of_day, weather=env.weather,
        lighting=env.lighting, details=details,
        atmosphere="quiet, immersive, focused, cozy, no people",
        visual_style="highly detailed cinematic environmental concept art",
    )


def find_backgrounds(folder: Path, theme: str) -> list[Path]:
    """Fons existents que pertanyen a l'ambientació (pel nom del fitxer)."""
    if not folder.is_dir():
        return []
    slug = slugify(theme)
    suffixes = SUPPORTED_IMAGE_SUFFIXES | SUPPORTED_VIDEO_SUFFIXES
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in suffixes and slug in slugify(p.stem))


def _audio_by_stem(folder: Path) -> dict[str, Path]:
    if not folder.is_dir():
        return {}
    return {p.stem: p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_SUFFIXES}


@dataclass(frozen=True)
class AmbienceLayer:
    path: Path
    loudness: float


def choose_ambience(folder: Path, environment: str, rng: random.Random) -> list[AmbienceLayer]:
    """Tria un so per capa. La primera capa sona més que les següents."""
    env = ENVIRONMENTS[environment]
    available = _audio_by_stem(folder)
    chosen: list[AmbienceLayer] = []
    for index, candidates in enumerate(env.layers):
        options = [available[name] for name in candidates if name in available]
        if not options:
            continue
        loudness = PRIMARY_AMBIENCE_LOUDNESS if not chosen else SECONDARY_AMBIENCE_LOUDNESS
        chosen.append(AmbienceLayer(rng.choice(options), loudness))
    if env.layers and not chosen:
        wanted = ", ".join(name for layer in env.layers for name in layer)
        raise ValueError(f"Falten els sons de l'entorn «{env.label}» en assets/ambience ({wanted})")
    return chosen


def load_catalog(path: Path) -> dict[str, dict]:
    """Catàleg d'àudios indexat pel nom del fitxer."""
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {Path(e["file"]).name: e for e in entries if isinstance(e, dict) and e.get("file")}


def probe_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return float(result.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0.0


def build_playlist(folder: Path, target_seconds: int, rng: random.Random, catalog: dict[str, dict] | None = None) -> list[Path]:
    """Ordre aleatori de peces sense repetir fins a cobrir la duració del vídeo.

    Si la biblioteca és més curta que el vídeo, el renderitzat repetirà la llista
    completa, no una sola peça.
    """
    tracks = list(_audio_by_stem(folder).values())
    if not tracks:
        raise ValueError("No hi ha música en assets/music")
    rng.shuffle(tracks)
    catalog = catalog or {}
    playlist: list[Path] = []
    total = 0.0
    for track in tracks:
        duration = float((catalog.get(track.name) or {}).get("duration_seconds") or 0) or probe_duration(track)
        playlist.append(track)
        total += max(0.0, duration - MUSIC_CROSSFADE_SECONDS)
        if total >= target_seconds:
            break
    return playlist


def loudnorm_filter(target: float) -> str:
    # loudnorm treballa internament a 192 kHz; es torna a 48 kHz estèreo.
    return f"loudnorm=I={target:g}:TP=-2:LRA=11,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"


def build_music_mix_command(playlist: list[Path], output: Path, *, crossfade: int = MUSIC_CROSSFADE_SECONDS) -> list[str]:
    """Una sola pista de música amb totes les peces encadenades i fosa entre elles."""
    if not playlist:
        raise ValueError("La llista musical és buida")
    command = ["ffmpeg", "-y", "-nostdin", "-loglevel", "error"]
    for track in playlist:
        command += ["-i", str(track)]
    parts = [f"[{i}:a]{loudnorm_filter(MUSIC_LOUDNESS)}[m{i}]" for i in range(len(playlist))]
    last = "m0"
    for i in range(1, len(playlist)):
        label = f"x{i}"
        parts.append(f"[{last}][m{i}]acrossfade=d={crossfade}:c1=tri:c2=tri[{label}]")
        last = label
    command += ["-filter_complex", ";".join(parts), "-map", f"[{last}]", "-c:a", "aac", "-b:a", "192k", str(output)]
    return command


def credit_line(entry: dict, fallback_name: str, *, compact: bool = False) -> str:
    title = entry.get("title") or Path(fallback_name).stem
    author = entry.get("author") or "Unknown"
    license_name = entry.get("license") or "see source"
    license_url = entry.get("license_url") or ""
    source = entry.get("source_url") or ""
    line = f'"{title}" by {author} — {license_name}'
    if license_url and not compact:
        line += f" ({license_url})"
    if source:
        line += f" — {source}"
    return line


def build_credits(music: list[Path], ambience: list[Path], catalog: dict[str, dict], *, compact: bool = False) -> str:
    """Crèdits per a la descripció. CC BY obliga a citar autor, obra i llicència."""
    lines: list[str] = []
    if music:
        lines.append("Music:")
        lines += [f"• {credit_line(catalog.get(p.name, {}), p.name, compact=compact)}" for p in music]
    if ambience:
        if lines:
            lines.append("")
        lines.append("Ambient sounds:")
        lines += [f"• {credit_line(catalog.get(p.name, {}), p.name, compact=compact)}" for p in ambience]
    if compact:
        used = {}
        for p in [*music, *ambience]:
            entry = catalog.get(p.name) or {}
            if entry.get("license") and entry.get("license_url"):
                used[entry["license"]] = entry["license_url"]
        if used:
            lines += ["", "Licenses: " + " · ".join(f"{name} {url}" for name, url in used.items())]
    return "\n".join(lines)


def duration_label(minutes: int) -> str:
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} Hour" if hours == 1 else f"{hours} Hours"
    return f"{minutes} Min"


@dataclass(frozen=True)
class AutoTexts:
    title: str
    description: str
    tags: str
    thumbnail_text: str


MAX_DESCRIPTION_BYTES = 4900


def build_texts(*, public_theme: str, environment: str, duration: int, focus: int, pause: int, chapters: str, credits: str, compact_credits: str = "") -> AutoTexts:
    env = ENVIRONMENTS[environment]
    label = duration_label(duration)
    options = [
        f"{label} {public_theme} Pomodoro {focus}/{pause} | {env.public_label} Study Ambience",
        f"{label} {public_theme} Pomodoro {focus}/{pause} | {env.public_label}",
        f"{label} {public_theme} Pomodoro {focus}/{pause}",
    ]
    title = next((t for t in options if len(t) <= 100), options[-1][:100])
    sound = "calm instrumental music" if not env.layers else f"{env.public_label.lower()} sounds and calm instrumental music"
    def compose(credit_text: str) -> str:
        return (
            f"Focus for {label.lower()} in a {public_theme.lower()} with {sound}.\n"
            f"Pomodoro timer: {focus} minutes of focus, {pause} minutes of break. "
            "The timer on screen shows each session and break.\n\n"
            f"Chapters:\n{chapters}\n\n"
            f"{credit_text}\n\n"
            f"Original ambience created for {CHANNEL_NAME}. Subscribe for new study and focus sessions."
        ).strip()

    description = compose(credits)
    if len(description.encode("utf-8")) > MAX_DESCRIPTION_BYTES and compact_credits:
        description = compose(compact_credits)
    if len(description.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        raise ValueError("La descripció supera el límit de YouTube fins i tot amb els crèdits compactes")
    tags = ", ".join(dict.fromkeys([
        "pomodoro", "study with me", "focus music", "study ambience", "pomodoro timer",
        f"{focus}/{pause} pomodoro", public_theme.lower(), env.public_label.lower(), f"{label.lower()} study",
    ]))
    thumbnail = f"{label.upper()} · {public_theme.upper()}"
    return AutoTexts(title, description, tags, thumbnail)


@dataclass
class AutoPlan:
    """Resultat de la preparació, abans de renderitzar."""
    background: Path
    ambience: list[AmbienceLayer] = field(default_factory=list)
    music_playlist: list[Path] = field(default_factory=list)
