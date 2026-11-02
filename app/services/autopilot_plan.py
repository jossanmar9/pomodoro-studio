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
from app.services.scenes import SCENES, SEASONS, season_slugs
from app.services.renderer import (
    CHIME_BREAK_END, CHIME_FOCUS_END, SUPPORTED_AUDIO_SUFFIXES, SUPPORTED_IMAGE_SUFFIXES,
    SUPPORTED_VIDEO_SUFFIXES, _bell, noise_filter, noise_source,
)
from app.services.timer import format_timestamp

CHANNEL_NAME = "The Amber Window"
CHANNEL_URL = "https://www.youtube.com/@TheAmberWindow"

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
    # Soroll generat per FFmpeg com a so de l'entorn (p. ex. cabina d'avió = soroll marró).
    noise: str | None = None


ENVIRONMENTS: dict[str, Environment] = {
    "pluja": Environment(
        "Pluja suau", "Gentle Rain", "late evening", "steady gentle rain against the windows",
        "warm candlelight and soft lamp glow, cool blue light from rainy windows",
        (("pluja-terrassa", "pluja-pedra", "pluja-bassal"),),
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
        (("rierol-muntanya", "rierol-muntanya-01", "bosc-rierol-01", "bosc-rierol-03", "torrent-muntanya"),),
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
        (("cova-01", "cova-02"), ("vent-des-de-dins", "vent-des-de-dins-01", "vent-des-de-dins-03"), ("gotes-aigua-01", "gotes-aigua-03")),
    ),
    "campament": Environment(
        "Campament de nit", "Campfire Night", "night", "clear starry night, crickets",
        "warm campfire glow and moonlight",
        (("camp-nit", "nit-grills-granotes"), ("foc-foguera-01", "foc-foguera-02", "foc-foguera-03")),
    ),
    "tempesta-mar": Environment(
        "Tempesta al mar", "Stormy Sea", "night", "violent storm at sea, heavy rain and rough waves",
        "swinging lantern light, dark storm clouds and lightning",
        (("mar-agitada", "ones-mar"), ("vent-fort-01", "vent-fort-03", "vent-xiulet-01"), ("pluja-trons", "pluja-tempesta-35min")),
    ),
    "cafeteria": Environment(
        "Cafeteria plena", "Coffee Shop Chatter", "afternoon", "calm",
        "warm interior lights, soft daylight from the windows",
        (("cafeteria-capucins", "bar-ambient-01", "restaurant-brunch-02"),),
    ),
    "taverna": Environment(
        "Taverna plena", "Busy Tavern", "night", "calm",
        "warm candlelight and a crackling hearth, deep cozy shadows",
        (("restaurant-brunch-02", "restaurant-brunch-03", "bar-ambient-01", "bar-ambient-02"), ("foc-llar", "foc-llar-04", "foc-llar-oberta")),
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
        (("pluja-pedra", "pluja-terrassa", "pluja-bassal"), ("ciutat-despres-pluja", "ciutat-nit-paris")),
    ),
    "ciutat-nit": Environment(
        "Ciutat de nit", "City at Night", "night", "clear, quiet city night",
        "street lamps and lit windows",
        (("ciutat-nit-paris", "ciutat-despres-pluja"),),
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
    "pluja-bosc": Environment(
        "Pluja al bosc", "Rain in the Forest", "late afternoon", "steady rain falling on the leaves, misty forest",
        "soft grey light through wet leaves, gentle mist",
        (("pluja-terrassa", "pluja-bassal"), ("vent-arbres", "vent-arbre", "bosc-nit-pluja")),
    ),
    "pluja-finestra": Environment(
        "Pluja a la finestra", "Rain on the Window", "evening", "rain drops running down the window glass",
        "warm lamp light inside, blurred rainy window",
        (("pluja-parabrisa", "pluja-dins-cotxe"),),
    ),
    "cova": Environment(
        "Cova amb goteig", "Dripping Cave", "timeless darkness", "cool damp air, water dripping from the rocks",
        "faint glow on wet stone, deep shadows",
        (("cova-01", "cova-02"), ("gotes-aigua-01", "gotes-aigua-03")),
    ),
    "hivern": Environment(
        "Vent d'hivern i llar", "Winter Wind & Fireplace", "winter night", "cold wind howling outside, snow on the windows",
        "warm fireplace glow against cold blue winter light",
        (("vent-des-de-dins", "vent-des-de-dins-01", "vent-des-de-dins-03", "vent-xiulet-01"), ("foc-llar", "foc-llar-04", "foc-llar-oberta")),
    ),
    "temporal": Environment(
        "Vent fort entre arbres", "Howling Wind in the Trees", "evening", "strong gusts of wind shaking the trees",
        "dramatic stormy sky, swaying trees",
        (("vent-fort-arbres-01", "vent-fort-arbres-02", "vent-fort-arbres-03"),),
    ),
    "tren": Environment(
        "Tren de nit", "Night Train", "night", "the steady rhythm of a train carriage",
        "dim carriage lights, dark landscape passing by the window",
        (("tren-vago",),),
    ),
    "rellotge": Environment(
        "Rellotge i llar de foc", "Ticking Clock & Fireplace", "late evening", "quiet and still",
        "warm lamp and fireplace glow in a quiet study",
        (("foc-llar", "foc-llar-04", "foc-llar-oberta"), ("rellotge-pendul", "rellotge-tictac")),
    ),
    "bosc-tempesta": Environment(
        "Tempesta al bosc", "Forest Thunderstorm", "evening", "heavy rain and thunder over a dark forest, strong wind in the trees",
        "dark green and blue storm light, faint lightning in the distance",
        (("pluja-tempesta-35min", "pluja-trons"), ("vent-fort-arbres-01", "vent-fort-arbres-02", "vent-fort-arbres-03")),
    ),
    "platja-tempesta": Environment(
        "Tempesta a la platja", "Stormy Beach", "evening", "storm over the sea, big waves crashing, rain sweeping the shore",
        "dramatic dark clouds, a warm lighthouse light in the distance",
        (("mar-agitada", "ones-mar"), ("pluja-trons", "pluja-tempesta-35min"), ("vent-fort-01", "vent-fort-03")),
    ),
    "riu": Environment(
        "Riu", "Gentle River", "afternoon", "calm, clear water flowing over stones",
        "soft afternoon light through willow trees",
        (("rierol-muntanya-01", "bosc-rierol-01", "bosc-rierol-03", "corrent-aigua"), ("bosc-ocells", "bosc-02", "vora-bosc")),
    ),
    "llar-tempesta": Environment(
        "Llar de foc i tempesta", "Fireplace & Thunderstorm", "night", "thunderstorm and heavy rain outside the windows",
        "warm firelight against cold blue storm light",
        (("pluja-tempesta-35min", "pluja-trons"), ("foc-llar", "foc-llar-04", "foc-llar-oberta")),
    ),
    "biblioteca": Environment(
        "Biblioteca amb pluja", "Rainy Library", "night", "soft rain against tall windows, quiet room",
        "green banker lamps and warm reading lights",
        (("pluja-terrassa", "pluja-pedra"), ("rellotge-pendul", "rellotge-tictac")),
    ),
    "port": Environment(
        "Port amb pluja", "Rainy Harbour", "night", "light rain over a quiet harbour, small waves against the boats",
        "warm lamps reflected on wet stones and water, light fog",
        (("ones-escuma-platja", "ones-ocea"), ("pluja-pedra", "pluja-bassal")),
    ),
    "avio": Environment(
        "Cabina d'avió", "Airplane Cabin", "night", "steady hum of the engines high above the clouds",
        "dim warm cabin lights, moonlit clouds outside the window",
        (), music=False, noise="brown",
    ),
    "nit-halloween": Environment(
        "Nit de Halloween", "Halloween Night", "night", "wind howling outside, owls in the dark woods",
        "flickering candlelight and carved pumpkins, misty moonlight",
        (("vent-des-de-dins", "vent-des-de-dins-01", "vent-des-de-dins-03", "vent-grinyol"), ("mussols", "mussol-banyut")),
    ),
    "nit-estiu": Environment(
        "Nit d'estiu", "Summer Night", "summer night", "warm still air, crickets and frogs",
        "starlight, a warm lantern and glowing fireflies",
        (("nit-grills-granotes", "camp-nit", "nit-camp-03"), ("vent-herba", "vent-arbre")),
    ),
    "jardi": Environment(
        "Jardí amb ocells", "Spring Birdsong", "spring morning", "fresh breeze, birds singing",
        "soft bright morning sunlight",
        (("bosc-ocells", "vora-bosc", "bosc-02", "bosc-04"), ("vent-herba",)),
    ),
    "tardor": Environment(
        "Vent de tardor", "Autumn Wind", "autumn afternoon", "wind in the trees, leaves falling",
        "warm golden autumn light",
        (("vent-arbres", "vent-arbre", "vent-fort-arbres-03"), ("vent-herba", "vent-grinyol")),
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
    "Avió": ("airplane window seat at night above the clouds", "an oval window over a sea of moonlit clouds, faint city lights far below, dim warm cabin lights, a folded blanket and a cup of tea on the tray table", "contemporary"),
    "Tren": ("vintage night train compartment", "wooden panels, soft reading lamps, a large window over a snowy mountain landscape under a starry sky, a small table with a book and a cup of tea", "vintage"),
    "Platja": ("calm sandy beach", "gentle waves rolling onto the shore, wet sand reflecting the sky, dunes with tall grass", "natural"),
    "Riu": ("gentle river in a green valley", "clear water over smooth stones, willow trees on the banks, a small wooden bridge in the distance", "natural"),
    "Hivernacle": ("old victorian glass greenhouse", "raindrops on the glass roof, lush plants, hanging ferns and orchids, a small wrought-iron table with a teapot", "victorian"),
    "Port": ("quiet old harbour", "small wooden boats gently rocking, warm lamps reflected on wet stones and water, light fog over the sea", "timeless"),
    "Estiu": ("cozy summer scene", "warm golden summer light, open windows, sea, fields and warm evenings", "cozy"),
    "Tardor": ("cozy autumn scene", "red and golden trees, falling leaves, soft rain and warm lamps", "cozy"),
    "Primavera": ("cozy spring scene", "cherry blossoms, fresh flowers, soft bright light and green leaves", "cozy"),
    "Hivern": ("cozy winter scene", "snow outside the windows, warm fireplaces and hot drinks", "cozy"),
    "Nadal": ("cozy christmas scene", "christmas trees with warm lights, garlands, candles and snow outside", "cozy"),
    "Halloween": ("cozy halloween scene", "carved pumpkins with candlelight, autumn leaves, a full moon and light fog", "cozy"),
    "Pasqua": ("cozy easter scene", "pastel painted eggs, spring flowers and soft morning sunlight", "cozy"),
    "Racó de lectura": ("cozy reading nook in a window seat", "soft cushions and a knitted blanket, stacks of well-worn books, an open book, a cup of tea and a warm reading lamp by a large window", "cozy"),
}

AUTO_THEMES = tuple(THEME_VISUALS)
# Quadres de la pàgina: primer per tipus de lloc, després estacions i festes. Cada tema va en un sol quadre.
THEME_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "Biblioteques i lectura": ("📚", ("Biblioteca medieval", "Biblioteca màgica", "Biblioteca èlfica", "Biblioteca victoriana", "Racó de lectura", "Observatori")),
    "Cafeteries i ciutat": ("☕", ("Cafeteria acollidora", "Cafeteria moderna", "Cafeteria a Nova York", "Cafeteria a Tòquio", "Cafeteria a París", "Apartament a la ciutat", "Parc a la ciutat")),
    "Cases i refugis": ("🏡", ("Cabana amb pluja", "Hivernacle", "Búnquer postapocalíptic")),
    "Natura": ("🌲", ("Bosc", "Platja", "Riu", "Port")),
    "Viatges": ("🚆", ("Tren", "Avió", "Vaixell pirata")),
    "Història": ("🏛️", ("Roma antiga", "Grècia antiga", "Japó feudal", "Castell gòtic")),
    "Fantasia i rol": ("🐉", ("Taverna medieval", "Torre de l'alquimista", "Masmorra", "Campament d'aventurers", "Cova del drac")),
    "Estiu": ("☀️", ("Estiu",)),
    "Tardor": ("🍂", ("Tardor",)),
    "Primavera": ("🌸", ("Primavera",)),
    "Hivern": ("❄️", ("Hivern",)),
    "Nadal": ("🎄", ("Nadal",)),
    "Halloween": ("🎃", ("Halloween",)),
    "Pasqua": ("🐣", ("Pasqua",)),
}
# Valor del formulari per a «qualsevol tema d'este quadre».
GROUP_PREFIX = "grup:"


def grouped_themes() -> list[tuple[str, str, list[str]]]:
    """(nom, icona, temes) de cada quadre, en l'ordre de la pàgina."""
    return [(name, icon, list(themes)) for name, (icon, themes) in THEME_GROUPS.items()]


def group_themes(value: str) -> list[str] | None:
    """Temes d'un valor «grup:Nom», o None si no és un grup."""
    if not value.startswith(GROUP_PREFIX):
        return None
    group = THEME_GROUPS.get(value[len(GROUP_PREFIX):])
    return list(group[1]) if group else []

# Formats del mode automàtic.
FORMATS = {
    "pomodoro": "Pomodoro",
    "dormir": "Per a dormir",
    "llegir": "Per a llegir",
    "ambient": "So ambiental",
    "respiracio": "Respiració guiada",
    "short": "Només un Short",
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
# Tema dels vídeos de soroll de color: no usen cap foto ni ambientació.
NOISE_THEME = "Soroll de color"
# La pantalla es fon a negre després de 30 minuts (vídeos per a dormir i soroll).
DIM_AFTER_SECONDS = 30 * 60
# Categoria de YouTube per format: 27 Education, 22 People & Blogs, 20 Gaming.
YOUTUBE_CATEGORIES = {"pomodoro": "27", "dormir": "22", "llegir": "22", "ambient": "22", "respiracio": "26", "short": "22", "soroll": "22", "rol": "20"}
FORMAT_MOODS = {
    "pomodoro": "quiet, immersive, focused, cozy, no people",
    "dormir": "calm, restful, dim and sleepy, soft low light, no people",
    "ambient": "calm, immersive and peaceful, natural light, no people",
    "respiracio": "calm, serene and peaceful, soft light, uncluttered center, no people",
    "short": "quiet, immersive, cozy, no people",
    "llegir": "cozy, warm and inviting, soft golden reading light, peaceful, no people",
    "soroll": "calm, restful, dark and minimal, soft low light, no people",
    "rol": "atmospheric, adventurous, immersive, mysterious, no people",
}
_NOISE_VISUAL = Environment("Soroll", "Noise", "night", "calm and still", "very soft dim warm light, dark and restful")
# Estils de música: clau → (nom en valencià, descripció pública en anglés).
MUSIC_STYLES = {
    "calma": ("Tranquil·la", "calm instrumental music"),
    "medieval": ("Medieval i folk", "medieval folk music"),
    "fosca": ("Fantasia fosca", "dark fantasy music"),
    "jazz": ("Jazz de cafeteria", "soft jazz"),
    "nadal": ("Nadal", "calm Christmas music"),
}
# Música de temporada per tema (com Nadal): Halloween fosca; estiu, jazz suau.
SEASON_MUSIC = {"Halloween": "fosca", "Estiu": "jazz"}
CHRISTMAS_THEMES = {"Nadal"}
_JAZZ_ENVIRONMENTS = {"cafeteria", "cafeteria-carrer", "pluja-ciutat", "ciutat-nit", "japo-carrer", "transit"}
_MEDIEVAL_ENVIRONMENTS = {"taverna", "campament"}
_DARK_ENVIRONMENTS = {"masmorra", "tempesta-mar", "cova", "nit-halloween"}
_DARK_RPG_ENVIRONMENTS = _DARK_ENVIRONMENTS | {"tempesta", "vent", "nit", "temporal"}


def music_style(fmt: str, environment: str, theme: str | None = None) -> str:
    """Estil de música que encaixa amb el format, l'entorn i (per a Nadal) el tema."""
    if theme in CHRISTMAS_THEMES and fmt != "rol":
        return "nadal"
    if theme in SEASON_MUSIC and fmt != "rol" and not (fmt == "dormir" and SEASON_MUSIC[theme] == "jazz"):
        return SEASON_MUSIC[theme]
    if fmt == "dormir":
        return "calma"
    if fmt == "rol":
        return "fosca" if environment in _DARK_RPG_ENVIRONMENTS else "medieval"
    if environment in _MEDIEVAL_ENVIRONMENTS:
        return "medieval"
    if environment in _DARK_ENVIRONMENTS:
        return "fosca"
    if environment in _JAZZ_ENVIRONMENTS:
        return "jazz"
    return "calma"


_CROWD_ENVIRONMENTS = {"cafeteria", "cafeteria-carrer", "taverna", "transit", "japo-carrer", "ciutat-nit", "pluja-ciutat", "parc"}


def music_advice(fmt: str, environment: str, theme: str) -> dict:
    """Recomana si posar música segons el format, l'entorn i el tema (l'usuari pot canviar-ho)."""
    style = MUSIC_STYLES[music_style(fmt, environment, theme)][0]
    env = ENVIRONMENTS.get(environment)
    if fmt in {"ambient", "soroll"}:
        return {"recommended": None, "reason": "Este format no porta música.", "style": None}
    if env is not None and not env.layers and not env.noise:
        return {"recommended": True, "reason": "Este entorn només té música.", "style": style}
    seasonal = theme in CHRISTMAS_THEMES or theme in SEASON_MUSIC
    if fmt == "dormir":
        return {"recommended": False, "reason": "Per a dormir funciona millor el so sol: no hi ha canvis de cançó que desperten.", "style": style}
    if seasonal:
        kind = {"Nadal": "nadalenca", "Fantasia fosca": "fosca", "Jazz de cafeteria": "de jazz suau"}.get(style, style.lower())
        return {"recommended": True, "reason": f"La música {kind} encaixa amb el tema.", "style": style}
    if fmt == "pomodoro" and environment in _CROWD_ENVIRONMENTS:
        return {"recommended": False, "reason": "El murmuri ja fa de fons; la música el taparia.", "style": style}
    reasons = {
        "pomodoro": "Una música tranquil·la ajuda a concentrar-se en sessions llargues.",
        "llegir": "Una música tranquil·la fa companyia mentre llegeixes.",
        "respiracio": "Una música suau acompanya la respiració.",
        "rol": "La música dona ambient a la partida.",
        "short": "Els Shorts amb música enganxen més.",
    }
    return {"recommended": True, "reason": reasons.get(fmt, "La música hi encaixa."), "style": style}


def track_style(path: Path, catalog: dict[str, dict] | None = None) -> str:
    """Estil d'una peça: el del catàleg o, si no hi és, el prefix del nom (jazz-…); per defecte, tranquil·la."""
    style = ((catalog or {}).get(path.name) or {}).get("style")
    if style in MUSIC_STYLES:
        return style
    prefix = path.stem.split("-", 1)[0]
    return prefix if prefix in MUSIC_STYLES else "calma"


def music_tracks(folder: Path, style: str | None = None, catalog: dict[str, dict] | None = None) -> list[Path]:
    tracks = list(_audio_by_stem(folder).values())
    return [t for t in tracks if track_style(t, catalog) == style] if style else tracks


def sort_key(text: str) -> str:
    """Ordre alfabètic sense tindre en compte accents ni majúscules (à = a, ç = c…)."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").casefold()


def environments_by_label() -> list[tuple[str, Environment]]:
    """Entorns ordenats alfabèticament pel nom en valencià."""
    return sorted(ENVIRONMENTS.items(), key=lambda item: sort_key(item[1].label))


DURATION_CHOICES = (60, 120, 180, 240, 480, 600)
POMODORO_CHOICES = {"25/5": (25, 5), "50/10": (50, 10), "52/17": (52, 17), "90/15": (90, 15)}
# Ritmes llargs: es publiquen com a «Deep Work» en compte de «Pomodoro».
DEEP_WORK_MIN_FOCUS = 52
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
    own = season_slugs(theme) or [slugify(theme)]
    suffixes = SUPPORTED_IMAGE_SUFFIXES | SUPPORTED_VIDEO_SUFFIXES
    # Un fitxer és del nom més llarg que hi encaixa: «bosc-nevat-…» és de l'escena «Bosc nevat» (Hivern), no de «Bosc».
    known = {slugify(t) for t in THEME_VISUALS} | {slugify(scene) for scene in SCENES}
    longer = [k for k in known if k not in own and any(k.startswith(o + "-") for o in own)]

    def belongs(stem: str) -> bool:
        if not any(stem == o or stem.startswith(o + "-") for o in own):
            return False
        return not any(stem == other or stem.startswith(other + "-") for other in longer)

    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in suffixes and belongs(slugify(p.stem)))


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
# Volum de la música respecte del nivell normal (dB).
MUSIC_LEVELS = {-8: "Molt baixa", -4: "Baixa", 0: "Normal", 3: "Alta"}


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


def build_playlist(folder: Path, target_seconds: int, rng: random.Random, catalog: dict[str, dict] | None = None, style: str | None = None) -> list[Path]:
    """Ordre aleatori de peces sense repetir fins a cobrir la duració del vídeo.

    Si la biblioteca és més curta que el vídeo, el renderitzat repetirà la llista
    completa, no una sola peça.
    """
    tracks = music_tracks(folder, style, catalog)
    if not tracks:
        raise ValueError(f"No hi ha música {MUSIC_STYLES[style][0].lower()} en assets/music" if style else "No hi ha música en assets/music")
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


def build_music_mix_command(playlist: list[Path], output: Path, *, crossfade: int = MUSIC_CROSSFADE_SECONDS, level: int = 0) -> list[str]:
    """Una sola pista de música amb totes les peces encadenades i fosa entre elles."""
    if not playlist:
        raise ValueError("La llista musical és buida")
    command = ["ffmpeg", "-y", "-nostdin", "-loglevel", "error"]
    for track in playlist:
        command += ["-i", str(track)]
    parts = [f"[{i}:a]{loudnorm_filter(MUSIC_LOUDNESS + level)}[m{i}]" for i in range(len(playlist))]
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


def cozy_name(public_theme: str) -> str:
    """«Cozy …» al davant (és el que busca la gent), sense repetir-lo si el nom ja el porta."""
    return public_theme if public_theme.casefold().startswith("cozy") else f"Cozy {public_theme}"


def _hashtag(text: str) -> str:
    return "#" + re.sub(r"[^a-z0-9]", "", text.casefold())


def _hashtags(*words: str) -> str:
    """Les tres primeres etiquetes ixen damunt del títol en YouTube."""
    return " ".join(dict.fromkeys(_hashtag(w) for w in words if w))


def build_texts(*, public_theme: str, environment: str, duration: int, focus: int, pause: int, chapters: str, credits: str, compact_credits: str = "", music: bool = True, chime: bool = False, fmt: str = "pomodoro", noise: str | None = None, dim: bool = False, style: str = "calma", breath: str | None = None, screen: str = "color") -> AutoTexts:
    music_text = MUSIC_STYLES.get(style, MUSIC_STYLES["calma"])[1]
    if fmt == "pomodoro":
        return _pomodoro_texts(public_theme=public_theme, environment=environment, duration=duration, focus=focus, pause=pause, chapters=chapters, credits=credits, compact_credits=compact_credits, music=music, chime=chime, music_text=music_text)
    if fmt not in FORMATS:
        raise ValueError("Format no vàlid")
    label = duration_label(duration)
    cozy = cozy_name(public_theme)
    dark_title = " · Dark Screen" if dim else ""
    dark_line = f"The screen slowly fades to black after {DIM_AFTER_SECONDS // 60} minutes, so it won't light up your room." if dim else ""
    outro = f"Original ambience created for {CHANNEL_NAME}. New cozy videos every week: subscribe and leave the light on."
    if fmt == "soroll":
        if noise not in NOISE_COLORS:
            raise ValueError("Color de soroll no vàlid")
        color = NOISE_COLORS[noise][1]
        black = screen == "negre"
        screen_title = " · Black Screen" if black else dark_title
        title = _fit_title([
            f"{color} Noise for Sleep, Focus & Relaxation | {label}{screen_title}",
            f"{label} {color} Noise{screen_title}",
        ])
        if black:
            screen_line = "The screen stays black the whole time, so it won't light up your room."
        else:
            screen_line = f"Just continuous {color.lower()} noise over a calm {color.lower()} screen. {dark_line}"
        uses = {"Brown": "Deep and soft, like a distant waterfall.", "Pink": "Balanced and gentle, like steady rain.", "White": "Even and bright, great for masking noises."}[color]
        compose = lambda credit_text: _join_blocks(
            f"{label} of smooth {color.lower()} noise for sleeping, studying, focusing, relaxing or calming a baby. {uses}",
            f"No music, no voices, no ads in the middle from us. {screen_line}",
            f"Chapters:\n{chapters}",
            "The noise is generated for this video; no third-party audio is used.",
            credit_text,
            outro,
            _hashtags(f"{color} noise", "sleep sounds", "focus"),
        )
        tags = [f"{color.lower()} noise", f"{color.lower()} noise for sleep", f"{color.lower()} noise {label.lower()}", "sleep sounds", "noise for sleeping", "focus noise", "study noise", "baby sleep", "relaxing noise", "black screen" if dim or black else "", f"{color.lower()} screen" if not black else ""]
        thumbnail = f"{color.upper()} NOISE · {label.upper()}"
    else:
        env = ENVIRONMENTS[environment]
        sounds = f"{env.public_label} Sounds"
        if not env.layers and not env.noise:
            sound = music_text
        elif music and env.music:
            sound = f"{env.public_label.lower()} sounds and {music_text}"
        else:
            sound = f"{env.public_label.lower()} sounds"
        sound_tags = [f"{env.public_label.lower()} sounds", f"{env.public_label.lower()} ambience"]
        if fmt == "dormir":
            title = _fit_title([
                f"{cozy} Ambience | {sounds} for Sleep & Relaxation | {label}{dark_title}",
                f"{cozy} Ambience | {sounds} for Sleep | {label}{dark_title}",
                f"{label} {sounds} for Sleep{dark_title}",
            ])
            compose = lambda credit_text: _join_blocks(
                f"{cozy} ambience with {sound} to fall asleep, rest and relax. {label.lower().capitalize()} with no timer, no alarms and no interruptions from us.",
                f"Close your eyes and let the cozy ambience carry you to sleep. Also lovely as calm background sound for reading or a quiet evening. {dark_line}",
                f"Chapters:\n{chapters}",
                credit_text,
                outro,
                _hashtags("cozy ambience", "sleep sounds", env.public_label),
            )
            tags = ["cozy ambience", "sleep sounds", "sleep ambience", "relaxing sounds", f"{env.public_label.lower()} for sleep", *sound_tags, f"{public_theme.lower()} ambience", f"{label.lower()} sleep sounds", "fall asleep fast"] + (["dark screen", "black screen sleep sounds"] if dim else [])
            thumbnail = f"{label.upper()} · {env.public_label.upper()}"
        elif fmt == "respiracio":
            from app.services.breathing import PATTERNS
            if breath not in PATTERNS:
                raise ValueError("Respiració no vàlida")
            pattern = PATTERNS[breath]
            minutes = f"{duration} Minute"
            title = _fit_title([
                f"{minutes} {pattern.public} | Guided Breathing Exercise to Calm Down | {cozy}",
                f"{minutes} {pattern.public} | Guided Breathing Exercise | {public_theme}",
                f"{minutes} {pattern.public} | Guided Breathing Exercise",
            ])
            compose = lambda credit_text: _join_blocks(
                f"A {duration} minute guided breathing exercise ({pattern.public.lower()}) to calm down, ease stress and anxiety, focus before studying or unwind before sleep.",
                f"Take 15 seconds to get comfortable, then follow the circle: breathe in as it grows, hold when it stops, and breathe out as it shrinks. {pattern.how}",
                f"Scene: {cozy.lower()} with {sound}. No talking.",
                "Breathe gently and never force it. If you feel dizzy, stop and breathe normally.",
                credit_text,
                outro,
                _hashtags("breathing exercise", pattern.public, "relax"),
            )
            tags = [pattern.public.lower(), "breathing exercise", "guided breathing", "breathwork", "calm breathing", "breathing for anxiety", "breathing for stress", "relaxation", "meditation", f"{duration} minute breathing", public_theme.lower()]
            thumbnail = f"{pattern.public.upper()} · {duration} MIN"
        elif fmt == "ambient":
            title = _fit_title([
                f"{cozy} Ambience | {sounds}, No Music | {label}",
                f"{cozy} Ambience | {sounds} | {label}",
                f"{label} {sounds}, No Music",
            ])
            compose = lambda credit_text: _join_blocks(
                f"{cozy} ambience with pure {env.public_label.lower()} sounds: {label.lower()} with no music, no talking and no timer.",
                "Cozy background ambience for studying, working, reading, relaxing or sleeping. Turn it up, turn it down, and let the place do the rest.",
                f"Chapters:\n{chapters}",
                credit_text,
                outro,
                _hashtags("cozy ambience", env.public_label, "ambience"),
            )
            tags = ["cozy ambience", *sound_tags, "ambient sounds", "ambience no music", "relaxing sounds", "background sounds", "sounds for sleep", "study ambience", f"{public_theme.lower()} ambience", f"{label.lower()} ambience"]
            thumbnail = f"{env.public_label.upper()} · {label.upper()}"
        elif fmt == "llegir":
            reading = cozy if "reading" in cozy.casefold() else f"{cozy} Reading"
            title = _fit_title([
                f"{reading} Ambience | {sounds} for Reading & Relaxing | {label}",
                f"{reading} Ambience | {sounds} | {label}",
                f"{label} Reading Ambience | {public_theme}",
            ])
            compose = lambda credit_text: _join_blocks(
                f"{reading} ambience with {sound}. Grab a book and get comfortable for {label.lower()}.",
                "No timer, no alarms, no talking: just a cozy, quiet place to read, write in your journal or simply unwind.",
                f"Chapters:\n{chapters}",
                credit_text,
                outro,
                _hashtags("cozy ambience", "reading ambience", "booktube"),
            )
            tags = ["cozy ambience", "reading ambience", "cozy reading", "read with me", "book ambience", "reading sounds", "relaxing ambience", *sound_tags, f"{public_theme.lower()} ambience", f"{label.lower()} reading"]
            thumbnail = f"READING · {label.upper()}"
        else:  # rol
            title = _fit_title([
                f"{public_theme} Ambience | {sounds} | Tabletop RPG & Fantasy Background · {label}",
                f"{public_theme} Ambience | {sounds} | Tabletop RPG Ambience",
                f"{public_theme} | Tabletop RPG Ambience",
            ])
            compose = lambda credit_text: _join_blocks(
                f"{public_theme} ambience for your tabletop RPG and fantasy sessions, with {sound}. {label.lower().capitalize()} without interruptions, so you can leave it playing while your party explores.",
                "Made for game masters and players of fantasy roleplaying games, and for fantasy reading or writing. No timer, no narration.",
                f"Chapters:\n{chapters}",
                credit_text,
                outro,
                _hashtags("rpg ambience", "fantasy ambience", "ttrpg"),
            )
            tags = ["tabletop rpg ambience", "dnd ambience", "rpg ambience", "fantasy ambience", "dungeon master", "game master ambience", "fantasy music" if music else "fantasy sounds", f"{public_theme.lower()} ambience", env.public_label.lower(), "ttrpg"]
            thumbnail = f"{public_theme.upper()} · {label.upper()}"
    description = _finish_description(compose, credits, compact_credits)
    return AutoTexts(title, description, ", ".join(t for t in dict.fromkeys(tags) if t), thumbnail)


def _pomodoro_texts(*, public_theme: str, environment: str, duration: int, focus: int, pause: int, chapters: str, credits: str, compact_credits: str = "", music: bool = True, chime: bool = False, music_text: str = "calm instrumental music") -> AutoTexts:
    env = ENVIRONMENTS[environment]
    label = duration_label(duration)
    cozy = cozy_name(public_theme)
    deep = focus >= DEEP_WORK_MIN_FOCUS
    method = f"Deep Work {focus}/{pause}" if deep else f"Pomodoro {focus}/{pause}"
    sounds = f"{env.public_label} Sounds" if env.layers or env.noise else "Calm Music"
    title = _fit_title([
        f"{cozy} Ambience | {label} {method} Study With Me | {sounds}",
        f"{cozy} Ambience | {label} {method} | {sounds}",
        f"{cozy} Ambience | {label} {method}",
        f"{label} {method} | {public_theme}",
    ])
    if not env.layers and not env.noise:
        sound = music_text
    elif music and env.music:
        sound = f"{env.public_label.lower()} sounds and {music_text}"
    else:
        sound = f"soft {env.public_label.lower()} sounds (no music)"
    timer_line = "The timer on screen shows each session and break."
    if chime:
        timer_line += " A soft chime marks the end of every focus session and every break."
    def compose(credit_text: str) -> str:
        return _join_blocks(
            f"{cozy} ambience to study and focus with me for {label.lower()}, with {sound}.\n"
            f"{'Deep work timer' if deep else 'Pomodoro timer'}: {focus} minutes of focus, {pause} minutes of break. {timer_line}",
            "Cozy study ambience for exams, homework, reading, writing or deep work. Put your phone away, make yourself something warm and start the first session.",
            f"Chapters:\n{chapters}",
            credit_text,
            f"Original ambience created for {CHANNEL_NAME}. New study and focus sessions every week: subscribe and leave the light on.",
            _hashtags("study with me", "pomodoro" if not deep else "deep work", "cozy ambience"),
        )

    description = _finish_description(compose, credits, compact_credits)
    tags = ", ".join(dict.fromkeys([
        *(["deep work", "deep focus", f"{focus}/{pause} method", "work with me"] if deep else []),
        "cozy ambience", "study with me", "pomodoro", "pomodoro timer", f"{focus}/{pause} pomodoro", "study ambience", "cozy study",
        "focus music" if music and env.music else "ambient sounds", f"{env.public_label.lower()} sounds",
        f"{public_theme.lower()} ambience", f"{label.lower()} study with me",
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


def build_preview_command(ambience: list[AmbienceLayer], music: Path | None, chime: bool, output: Path, *, seconds: int = PREVIEW_SECONDS, noise: str | None = None, noise_loudness: float = -30.0, music_level: int = 0) -> list[str]:
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
        parts.append(f"[{index}:a]{loudnorm_filter(MUSIC_LOUDNESS + music_level)},afade=t=in:d=1[a{index}]")
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
