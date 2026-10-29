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
from app.services.renderer import (
    CHIME_BREAK_END, CHIME_FOCUS_END, SUPPORTED_AUDIO_SUFFIXES, SUPPORTED_IMAGE_SUFFIXES,
    SUPPORTED_VIDEO_SUFFIXES, _bell, noise_filter, noise_source,
)
from app.services.timer import format_timestamp

CHANNEL_NAME = "The Amber Window"

# Sonoritat objectiu (LUFS). La música i els efectes es normalitzen perquè cap
# pista tape les altres, independentment de com s'haja gravat cada fitxer.
MUSIC_LOUDNESS = -22.0
PRIMARY_AMBIENCE_LOUDNESS = -30.0
SECONDARY_AMBIENCE_LOUDNESS = -36.0
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
    "masmorra": Environment(
        "Masmorra (vent i aigua)", "Dungeon Wind & Dripping Water", "timeless darkness", "damp, cold air moving through stone corridors",
        "flickering torchlight on wet stone, deep shadows",
        (("vent-des-de-dins",), ("corrent-aigua", "cascada-petita")),
    ),
    "campament": Environment(
        "Campament de nit", "Campfire Night", "night", "clear starry night, crickets",
        "warm campfire glow and moonlight",
        (("camp-nit", "nit-grills-granotes"), ("foc-llar-oberta", "foc-llar-05", "foc-llar")),
    ),
    "tempesta-mar": Environment(
        "Tempesta al mar", "Stormy Sea", "night", "violent storm at sea, heavy rain and rough waves",
        "swinging lantern light, dark storm clouds and lightning",
        (("mar-agitada",), ("pluja-trons", "pluja-tempesta-35min")),
    ),
    "cafeteria": Environment(
        "Cafeteria plena", "Coffee Shop Chatter", "afternoon", "calm",
        "warm interior lights, soft daylight from the windows",
        (("cafeteria-capucins", "bar-ambient-01", "restaurant-brunch-02"),),
    ),
    "taverna": Environment(
        "Taverna plena", "Busy Tavern", "night", "calm",
        "warm candlelight and a crackling hearth, deep cozy shadows",
        (("restaurant-brunch-02", "restaurant-brunch-03", "restaurant-pizzeria"), ("foc-llar", "foc-llar-04", "foc-llar-oberta")),
    ),
    "cafeteria-carrer": Environment(
        "Cafeteria i carrer", "Café & Street Sounds", "late afternoon", "calm, city street visible through the window",
        "warm interior lamps contrasted with soft city light outside",
        (("cafeteria-capucins", "bar-ambient-01", "restaurant-brunch-03"), ("ciutat-carrer-paris", "ciutat-cruilla", "ciutat-aubervilliers")),
    ),
    "transit": Environment(
        "Trànsit de ciutat", "City Traffic", "afternoon", "calm, busy avenue outside",
        "natural city daylight",
        (("ciutat-aubervilliers", "ciutat-cruilla", "ciutat-carrer-paris"),),
    ),
    "pluja-ciutat": Environment(
        "Pluja a la ciutat", "Rainy City", "evening", "steady rain over the city, wet reflective streets",
        "warm window lights and reflections on wet streets",
        (("pluja-pedra", "pluja-terrassa", "pluja-bassal"), ("ciutat-nit-paris", "ciutat-carrer-paris")),
    ),
    "ciutat-nit": Environment(
        "Ciutat de nit", "City at Night", "night", "clear, quiet city night",
        "street lamps and lit windows",
        (("ciutat-nit-paris",),),
    ),
    "parc": Environment(
        "Parc i plaça", "Park & Plaza", "sunny afternoon", "pleasant breeze",
        "warm dappled sunlight through trees",
        (("parc-xiquets", "ciutat-placa-terrasses"), ("bosc-ocells", "vent-arbres", "vent-arbre")),
    ),
    "japo-carrer": Environment(
        "Carrers del Japó", "Japanese Street", "evening", "calm, a quiet crossing outside",
        "soft neon and warm lantern light",
        (("japo-cruilla", "japo-parada-bus"),),
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
    "Cafeteria moderna": ("minimalist modern specialty coffee shop", "light wood and concrete, plants, an espresso machine, large windows and a quiet table with a laptop and notebook", "contemporary"),
    "Cafeteria a Nova York": ("cozy coffee shop in a New York brownstone neighbourhood", "exposed brick walls, warm lamps, a big window onto a busy avenue with taxis and fire escapes", "contemporary"),
    "Cafeteria a Tòquio": ("small cozy café in a quiet Tokyo backstreet", "wooden counter, pour-over coffee, paper lanterns, plants and soft neon signs reflected in the window", "contemporary"),
    "Cafeteria a París": ("classic Parisian café corner", "small round marble tables, bentwood chairs, a big window onto a cobbled street with Haussmann buildings", "timeless"),
    "Parc a la ciutat": ("quiet bench and small study table in a leafy city park", "old trees, gravel paths, a fountain and city buildings in the distance", "contemporary"),
    "Masmorra": ("ancient stone dungeon corridor", "torches on damp stone walls, iron doors, chains, puddles and vaulted arches fading into darkness", "medieval fantasy"),
    "Campament d'aventurers": ("adventurers' camp in a forest clearing", "canvas tents, a campfire, bedrolls, an old map on a wooden crate, lanterns and tall pine trees", "medieval fantasy"),
    "Cova del drac": ("vast cavern with a dragon's hoard", "piles of gold coins, glowing crystals, an underground lake and a huge dark winged silhouette in the distance", "fantasy"),
    "Apartament a la ciutat": ("cozy city apartment study corner by a large window", "desk with books and a warm lamp, plants, city skyline and lit windows outside", "contemporary"),
}

AUTO_THEMES = tuple(THEME_VISUALS)

# Formats del mode automàtic.
FORMATS = {
    "pomodoro": "Pomodoro",
    "dormir": "Per a dormir",
    "rol": "Partida de rol",
    "soroll": "Soroll de color",
}
# Color intern → (color de FFmpeg, nom públic en anglés, nom en valencià)
NOISE_COLORS = {
    "marro": ("brown", "Brown", "Marró"),
    "rosa": ("pink", "Pink", "Rosa"),
    "blanc": ("white", "White", "Blanc"),
}
NOISE_ENVIRONMENT = "soroll"
# La pantalla es fon a negre després de 30 minuts (vídeos per a dormir i soroll).
DIM_AFTER_SECONDS = 30 * 60
# Categoria de YouTube per format: 27 Education, 22 People & Blogs, 20 Gaming.
YOUTUBE_CATEGORIES = {"pomodoro": "27", "dormir": "22", "soroll": "22", "rol": "20"}
FORMAT_MOODS = {
    "pomodoro": "quiet, immersive, focused, cozy, no people",
    "dormir": "calm, restful, dim and sleepy, soft low light, no people",
    "soroll": "calm, restful, dark and minimal, soft low light, no people",
    "rol": "atmospheric, adventurous, immersive, mysterious, no people",
}
_NOISE_VISUAL = Environment("Soroll", "Noise", "night", "calm and still", "very soft dim warm light, dark and restful")
DURATION_CHOICES = (60, 120, 180, 240, 480)
POMODORO_CHOICES = {"25/5": (25, 5), "50/10": (50, 10)}
PRIVACY_CHOICES = {"public": "Públic", "unlisted": "Ocult (amb enllaç)", "private": "Privat"}


def slugify(text: str) -> str:
    normal = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", normal).strip("-")


def prompt_spec(theme: str, environment: str, fmt: str = "pomodoro") -> AmbiencePromptSpec:
    if theme not in THEME_VISUALS:
        raise ValueError("Ambientació no disponible en el mode automàtic")
    if fmt not in FORMATS:
        raise ValueError("Format no vàlid")
    if environment == NOISE_ENVIRONMENT:
        env = _NOISE_VISUAL
    elif environment in ENVIRONMENTS:
        env = ENVIRONMENTS[environment]
    else:
        raise ValueError("Entorn no vàlid")
    subject, details, era = THEME_VISUALS[theme]
    return AmbiencePromptSpec(
        subject=subject, era=era, time_of_day=env.time_of_day, weather=env.weather,
        lighting=env.lighting, details=details,
        atmosphere=FORMAT_MOODS[fmt],
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


# Volum de l'ambient triat en la pàgina: desplaçament en dB sobre la sonoritat base.
AMBIENCE_LEVELS = {-6: "Molt baix", 0: "Baix", 4: "Normal"}


def choose_ambience(folder: Path, environment: str, rng: random.Random, *, level: int = 0, preferred: list[str] | None = None) -> list[AmbienceLayer]:
    """Tria un so per capa. La primera capa sona més que les següents.

    Si `preferred` porta els noms de fitxer d'una mostra escoltada abans, es
    reutilitzen, perquè el vídeo sone igual que la mostra.
    """
    if level not in AMBIENCE_LEVELS:
        raise ValueError("Volum d'ambient no vàlid")
    env = ENVIRONMENTS[environment]
    available = _audio_by_stem(folder)
    wanted = {Path(name).stem for name in (preferred or [])}
    chosen: list[AmbienceLayer] = []
    for index, candidates in enumerate(env.layers):
        options = [available[name] for name in candidates if name in available]
        if not options:
            continue
        loudness = (PRIMARY_AMBIENCE_LOUDNESS if not chosen else SECONDARY_AMBIENCE_LOUDNESS) + level
        reused = [path for path in options if path.stem in wanted]
        chosen.append(AmbienceLayer(reused[0] if reused else rng.choice(options), loudness))
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


def _fit_title(options: list[str]) -> str:
    return next((t for t in options if len(t) <= 100), options[-1][:100])


def _finish_description(compose, credits: str, compact_credits: str) -> str:
    description = compose(credits)
    if len(description.encode("utf-8")) > MAX_DESCRIPTION_BYTES and compact_credits:
        description = compose(compact_credits)
    if len(description.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        raise ValueError("La descripció supera el límit de YouTube fins i tot amb els crèdits compactes")
    return description


def _join_blocks(*blocks: str) -> str:
    return "\n\n".join(block.strip() for block in blocks if block and block.strip())


def build_texts(*, public_theme: str, environment: str, duration: int, focus: int, pause: int, chapters: str, credits: str, compact_credits: str = "", music: bool = True, chime: bool = False, fmt: str = "pomodoro", noise: str | None = None, dim: bool = False) -> AutoTexts:
    if fmt == "pomodoro":
        return _pomodoro_texts(public_theme=public_theme, environment=environment, duration=duration, focus=focus, pause=pause, chapters=chapters, credits=credits, compact_credits=compact_credits, music=music, chime=chime)
    if fmt not in FORMATS:
        raise ValueError("Format no vàlid")
    label = duration_label(duration)
    dark_title = " · Dark Screen" if dim else ""
    dark_line = f"The screen slowly fades to black after {DIM_AFTER_SECONDS // 60} minutes, so it won't light up your room." if dim else ""
    outro = f"Original ambience created for {CHANNEL_NAME}. Subscribe for more."
    if fmt == "soroll":
        if noise not in NOISE_COLORS:
            raise ValueError("Color de soroll no vàlid")
        color = NOISE_COLORS[noise][1]
        title = _fit_title([
            f"{label} {color} Noise for Sleep, Focus & Relaxation | {public_theme}{dark_title}",
            f"{label} {color} Noise | {public_theme}{dark_title}",
            f"{label} {color} Noise{dark_title}",
        ])
        uses = {"Brown": "Deep and soft, like a distant waterfall.", "Pink": "Balanced and gentle, like steady rain.", "White": "Even and bright, great for masking noises."}[color]
        compose = lambda credit_text: _join_blocks(
            f"{label} of smooth {color.lower()} noise for sleeping, studying, relaxing or calming a baby. {uses}",
            f"No music, no voices: just continuous {color.lower()} noise over a {public_theme.lower()}. {dark_line}",
            f"Chapters:\n{chapters}",
            "The noise is generated for this video; no third-party audio is used.",
            credit_text,
            outro,
        )
        tags = [f"{color.lower()} noise", f"{color.lower()} noise for sleep", f"{color.lower()} noise {label.lower()}", "sleep sounds", "noise for sleeping", "focus noise", "baby sleep", "relaxing noise", public_theme.lower()]
        thumbnail = f"{color.upper()} NOISE · {label.upper()}"
    else:
        env = ENVIRONMENTS[environment]
        if not env.layers:
            sound = "calm instrumental music"
        elif music:
            sound = f"{env.public_label.lower()} sounds and calm instrumental music"
        else:
            sound = f"{env.public_label.lower()} sounds"
        if fmt == "dormir":
            title = _fit_title([
                f"{label} {public_theme} Ambience | {env.public_label} for Sleep & Relaxation{dark_title}",
                f"{label} {env.public_label} for Sleep | {public_theme}{dark_title}",
                f"{label} {env.public_label} for Sleep{dark_title}",
            ])
            compose = lambda credit_text: _join_blocks(
                f"Relax and fall asleep in a {public_theme.lower()} with {sound}. No timer, no alarms, no interruptions from us. {dark_line}",
                f"Chapters:\n{chapters}",
                credit_text,
                outro,
            )
            tags = ["sleep sounds", "sleep ambience", "relaxing sounds", f"{env.public_label.lower()} for sleep", f"{env.public_label.lower()} sounds", public_theme.lower(), f"{label.lower()} sleep sounds", "fall asleep fast"] + (["dark screen", "black screen sleep sounds"] if dim else [])
            thumbnail = f"{label.upper()} · {env.public_label.upper()}"
        else:  # rol
            title = _fit_title([
                f"{public_theme} Ambience | {env.public_label} | Tabletop RPG Background · {label}",
                f"{public_theme} | {env.public_label} | Tabletop RPG Ambience",
                f"{public_theme} | Tabletop RPG Ambience",
            ])
            compose = lambda credit_text: _join_blocks(
                f"Background ambience for your tabletop RPG sessions: a {public_theme.lower()} with {sound}. {label} without interruptions, so you can leave it playing while your party explores.",
                "Made for game masters and players of fantasy roleplaying games. No timer, no narration.",
                f"Chapters:\n{chapters}",
                credit_text,
                outro,
            )
            tags = ["tabletop rpg ambience", "dnd ambience", "rpg ambience", "fantasy ambience", "dungeon master", "game master ambience", public_theme.lower(), env.public_label.lower(), "ttrpg"]
            thumbnail = f"{public_theme.upper()} · {label.upper()}"
    description = _finish_description(compose, credits, compact_credits)
    return AutoTexts(title, description, ", ".join(dict.fromkeys(tags)), thumbnail)


def _pomodoro_texts(*, public_theme: str, environment: str, duration: int, focus: int, pause: int, chapters: str, credits: str, compact_credits: str = "", music: bool = True, chime: bool = False) -> AutoTexts:
    env = ENVIRONMENTS[environment]
    label = duration_label(duration)
    options = [
        f"{label} {public_theme} Pomodoro {focus}/{pause} | {env.public_label}{'' if music or not env.layers else ' Sounds'} Study Ambience",
        f"{label} {public_theme} Pomodoro {focus}/{pause} | {env.public_label}",
        f"{label} {public_theme} Pomodoro {focus}/{pause}",
    ]
    title = next((t for t in options if len(t) <= 100), options[-1][:100])
    if not env.layers:
        sound = "calm instrumental music"
    elif music:
        sound = f"{env.public_label.lower()} sounds and calm instrumental music"
    else:
        sound = f"soft {env.public_label.lower()} sounds (no music)"
    timer_line = "The timer on screen shows each session and break."
    if chime:
        timer_line += " A soft chime marks the end of every focus session and every break."
    def compose(credit_text: str) -> str:
        return (
            f"Focus for {label.lower()} in a {public_theme.lower()} with {sound}.\n"
            f"Pomodoro timer: {focus} minutes of focus, {pause} minutes of break. "
            f"{timer_line}\n\n"
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
        "pomodoro", "study with me", "focus music" if music or not env.layers else "ambient sounds", "study ambience", "pomodoro timer",
        f"{focus}/{pause} pomodoro", public_theme.lower(), env.public_label.lower(), f"{label.lower()} study",
    ]))
    thumbnail = f"{label.upper()} · {public_theme.upper()}"
    return AutoTexts(title, description, tags, thumbnail)


def plain_chapters(total_seconds: int, dim_after: int | None = None) -> str:
    """Capítols per a vídeos sense comptador: cada hora (o cada 15 min si dura una hora o menys)."""
    step = 3600 if total_seconds > 3600 else 900
    marks = {start: f"Hour {start // 3600 + 1}" if step == 3600 else f"Part {start // step + 1}" for start in range(0, total_seconds, step)}
    if dim_after is not None and 0 < dim_after < total_seconds:
        # YouTube demana almenys 10 s entre capítols.
        marks = {start: label for start, label in marks.items() if abs(start - dim_after) >= 10}
        marks[dim_after] = "Dark screen"
    return "\n".join(f"{format_timestamp(start)} {label}" for start, label in sorted(marks.items()))


@dataclass
class AutoPlan:
    """Resultat de la preparació, abans de renderitzar."""
    background: Path
    ambience: list[AmbienceLayer] = field(default_factory=list)
    music_playlist: list[Path] = field(default_factory=list)


PREVIEW_SECONDS = 30


def build_preview_command(ambience: list[AmbienceLayer], music: Path | None, chime: bool, output: Path, *, seconds: int = PREVIEW_SECONDS, noise: str | None = None, noise_loudness: float = -30.0) -> list[str]:
    """Mostra d'àudio amb els mateixos nivells que el vídeo final.

    La campaneta sona als 10 s (final de concentració) i als 20 s (final de descans).
    `noise` és el color de FFmpeg (white, pink o brown).
    """
    if not ambience and music is None and not chime and not noise:
        raise ValueError("No hi ha cap so per a la mostra")
    command = ["ffmpeg", "-y", "-nostdin", "-loglevel", "error"]
    parts: list[str] = []
    mix: list[str] = []
    index = 0
    if noise:
        command += ["-f", "lavfi", "-i", noise_source(noise, seconds)]
        parts.append(f"[{index}:a]{noise_filter(noise_loudness)},afade=t=in:d=1[a{index}]")
        mix.append(f"[a{index}]"); index += 1
    for layer in ambience:
        command += ["-stream_loop", "-1", "-i", str(layer.path)]
        parts.append(f"[{index}:a]loudnorm=I={layer.loudness:g}:TP=-2:LRA=11,aresample=48000,aformat=channel_layouts=stereo,afade=t=in:d=1[a{index}]")
        mix.append(f"[a{index}]"); index += 1
    if music is not None:
        command += ["-stream_loop", "-1", "-i", str(music)]
        parts.append(f"[{index}:a]{loudnorm_filter(MUSIC_LOUDNESS)},afade=t=in:d=1[a{index}]")
        mix.append(f"[a{index}]"); index += 1
    if chime:
        for notes, at in ((CHIME_FOCUS_END, 10_000), (CHIME_BREAK_END, 20_000)):
            command += ["-f", "lavfi", "-i", _bell(*notes)]
            parts.append(f"[{index}:a]adelay={at}:all=1[a{index}]")
            mix.append(f"[a{index}]"); index += 1
    parts.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=longest:normalize=0,alimiter=limit=0.95,afade=t=out:st={seconds - 2}:d=2[out]")
    command += ["-filter_complex", ";".join(parts), "-map", "[out]", "-t", str(seconds), "-c:a", "libmp3lame", "-q:a", "4", str(output)]
    return command


def has_fire(layers: list[AmbienceLayer]) -> bool:
    """Si l'ambient porta foc, la llum del vídeo parpelleja suaument."""
    return any(layer.path.stem.startswith("foc-") for layer in layers)
