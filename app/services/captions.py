"""Textos variats per als reels d'Instagram i Facebook i frases d'ambient per a les descripcions.

Cada text es munta amb peces triades segons un número (el vídeo i el Short): un ganxo amb el
nom del lloc, una línia segons el so (pluja, foc, mar…), una invitació segons el format, on
veure el vídeo sencer, un comiat i cinc hashtags. Amb 10-12 opcions per peça, cada tema té
centenars de combinacions, i els tres reels d'un mateix vídeo mai porten el mateix text.
"""
from __future__ import annotations

import hashlib

# ---------------------------------------------------------------- família del so

FAMILIES = (
    ("rain", ("rain", "monsoon", "storm", "thunder")),
    ("fire", ("fire", "campfire", "candle")),
    ("sea", ("ocean", "sea", "wave", "beach", "harbour")),
    ("water", ("river", "stream", "dripping", "cave")),
    ("forest", ("forest", "bird", "jungle", "spring", "garden", "cicada")),
    ("city", ("café", "cafe", "coffee", "city", "street", "traffic", "park", "plaza", "tavern", "shop")),
    ("wind", ("wind", "snow", "winter", "desert")),
    ("train", ("train", "airplane", "cabin")),
    ("night", ("night", "quiet", "halloween", "savanna")),
    ("music", ("music", "vinyl", "lofi", "lo-fi")),
)


def sound_family(sound: str) -> str:
    lowered = sound.casefold()
    for family, words in FAMILIES:
        if any(word in lowered for word in words):
            return family
    return "default"


# Una línia sobre el so. {sound} és el nom del so en minúscules.
MOODS = {
    "rain": (
        "Rain taps softly on the glass while the lamp keeps the room warm.",
        "Let the rain do the talking tonight.",
        "There's something about rain that makes everything slow down.",
        "Steady rain outside, a warm cup inside.",
        "The kind of rainy evening you never want to end.",
        "Rain against the window and nowhere else to be.",
        "Grey skies, soft rain and a quiet mind.",
        "Listen to the rain wash the day away.",
        "A rainy day is the coziest excuse to stay in.",
        "Raindrops on the window, calm in the room.",
        "Rain outside means it's time to slow down inside.",
        "Every drop of rain is one less worry.",
    ),
    "fire": (
        "The fire crackles and the whole room glows amber.",
        "Pull a blanket closer and listen to the fire.",
        "Warm light, crackling wood and a slow evening.",
        "Nothing beats the sound of a fire on a cold night.",
        "Sit by the fire and let the day melt away.",
        "Embers glowing, mind slowing down.",
        "A crackling fire is the best kind of company.",
        "Golden firelight and a quiet heart.",
        "Feel the warmth from the fireplace.",
        "The fire hums softly while the world outside goes cold.",
    ),
    "sea": (
        "Waves roll in, one after another, and so do your thoughts.",
        "Let the sea breathe for you for a while.",
        "Salt air, soft waves and a slower pace.",
        "The ocean never rushes, and neither should you.",
        "Listen to the tide come and go.",
        "Waves on the shore and a calm mind.",
        "The sea has a way of quieting everything else.",
        "Breathe in with the waves, breathe out with the tide.",
        "A window open to the sea and nothing to do.",
        "Soft waves for a soft evening.",
    ),
    "water": (
        "Flowing water and a quiet place to think.",
        "Let the stream carry your worries away.",
        "Water trickling softly in the background.",
        "The gentle sound of water that never stops.",
        "A slow river for a slow afternoon.",
        "Drip, drop, and a mind at ease.",
        "Listen to the water find its way.",
        "Cool water sounds and warm light.",
        "Calm water, calm thoughts.",
        "The steady sound of water to keep you company.",
    ),
    "forest": (
        "Birdsong, green light and fresh air through the window.",
        "The forest is awake and gentle today.",
        "Leaves rustling and birds singing softly outside.",
        "A little bit of nature for your busy day.",
        "Breathe in the green, breathe out the stress.",
        "Morning light through the trees and birds outside.",
        "The trees are calm, and so can you be.",
        "A quiet garden just outside the window.",
        "Nature sounds to bring you back to yourself.",
        "Soft birdsong to start again.",
    ),
    "city": (
        "The soft hum of the city while you stay warm inside.",
        "Distant voices, clinking cups and a cozy corner.",
        "A busy world outside, a quiet table for you.",
        "Café chatter and the smell of fresh coffee.",
        "City sounds, softened by the window.",
        "Find your corner in the middle of it all.",
        "Life goes on outside while you take your time.",
        "The gentle buzz of people around you, and your own little bubble.",
        "Coffee, quiet chatter and a page to write.",
        "Street lights on, cups warm, mind clear.",
    ),
    "wind": (
        "The wind howls outside but it's warm in here.",
        "Snow falling quietly and a warm room to watch it from.",
        "Cold winds outside, soft blankets inside.",
        "Let the wind sing while you rest.",
        "Winter outside, warmth within.",
        "Wrap up warm and listen to the wind.",
        "A cold night made cozy.",
        "The wind blows, the lamp glows.",
        "Frosty windows and a hot drink.",
        "Snowy hush and a quiet heart.",
    ),
    "train": (
        "The gentle rhythm of a journey with nowhere to be.",
        "Watch the world go by and let your thoughts travel.",
        "A soft hum and a window seat all to yourself.",
        "On the move, but completely still.",
        "Somewhere between here and there, a moment of calm.",
        "The road ahead can wait, enjoy the ride.",
        "Travel sounds to rest your mind.",
        "Lights passing by and a quiet seat.",
        "Let the journey rock you to calm.",
        "A long trip and a warm drink.",
    ),
    "night": (
        "A still night and a soft light in the window.",
        "The world is asleep. You can rest too.",
        "Quiet nights are made for slowing down.",
        "Stars outside, calm inside.",
        "Late night calm, just for you.",
        "Moonlight and silence, the best kind of evening.",
        "The night is long and gentle.",
        "Everything is quiet now.",
        "A peaceful night to rest your mind.",
        "Soft night sounds and nothing to worry about.",
    ),
    "music": (
        "Soft music and a warm room.",
        "A gentle melody to keep you company.",
        "Slow music for slow moments.",
        "Calm tunes and soft light.",
        "Let the music carry you somewhere quieter.",
        "Warm crackle, soft melody, slow evening.",
        "A little music for a little peace.",
        "Music low, mind at ease.",
        "Press play and let the melody do the rest.",
        "Quiet music and a cozy corner.",
    ),
    "default": (
        "A quiet place to slow down.",
        "Warm light and a calm mind.",
        "Take a deep breath and stay a while.",
        "Your cozy corner is waiting.",
        "A small escape from a busy day.",
        "Slow down. You're allowed.",
        "Soft sounds for a softer day.",
        "A calm place for whatever you need.",
        "Let everything else wait for a while.",
        "Peace and quiet, just for you.",
    ),
}

# Ganxo inicial: sempre amb el nom del lloc. {place} = «Cozy …», {name} = el nom tal qual, {icon} = emoji del so.
HOOKS = {
    "pomodoro": (
        "{place} {icon} Study with me",
        "Study session · {name} {icon}",
        "{place} · Focus mode on {icon}",
        "Your study spot for today: {name} {icon}",
        "{place} {icon} Let's get some work done",
        "One more session · {name} {icon}",
        "{place} {icon} Pomodoro time",
        "Deep focus · {name} {icon}",
        "{place} {icon} Open your notes",
        "Come study · {name} {icon}",
        "{place} {icon} Productive and calm",
        "Quiet study hours · {name} {icon}",
    ),
    "dormir": (
        "{place} {icon} Time to sleep",
        "Fall asleep · {name} {icon}",
        "{place} {icon} Goodnight",
        "Rest tonight · {name} {icon}",
        "{place} {icon} Sleep sounds",
        "Drift off · {name} {icon}",
        "{place} {icon} Close your eyes",
        "A peaceful night · {name} {icon}",
        "{place} {icon} Sweet dreams",
        "Lights out · {name} {icon}",
        "{place} {icon} Rest well",
        "Tonight: {name} {icon}",
    ),
    "llegir": (
        "{place} {icon} Reading time",
        "Read a chapter · {name} {icon}",
        "{place} {icon} Book and blanket",
        "Your reading corner: {name} {icon}",
        "{place} {icon} Get lost in a story",
        "Quiet pages · {name} {icon}",
        "{place} {icon} One more chapter",
        "A reading night · {name} {icon}",
        "{place} {icon} Read with me",
        "Open your book · {name} {icon}",
    ),
    "ambient": (
        "{place} {icon}",
        "Just listen: {name} {icon}",
        "{place} {icon} Pure ambience",
        "Step inside: {name} {icon}",
        "{place} {icon} No music, just sounds",
        "Spend a while here: {name} {icon}",
        "{place} {icon} Sounds to get lost in",
        "Welcome to {name} {icon}",
        "{place} {icon} Stay a while",
        "A moment · {name} {icon}",
    ),
    "rol": (
        "{place} {icon} Tonight's adventure",
        "Roll for initiative · {name} {icon}",
        "{place} {icon} Background for your campaign",
        "Your party arrives · {name} {icon}",
        "{place} {icon} Fantasy ambience",
        "The quest continues · {name} {icon}",
        "{place} {icon} For DMs and dreamers",
        "Set the scene: {name} {icon}",
        "{place} {icon} Into the story",
        "A new chapter begins · {name} {icon}",
    ),
    "soroll": (
        "{place} {icon} Sleep and focus",
        "{place} {icon} Block out the world",
        "{place} {icon} Steady and calm",
        "Tune out with {name} {icon}",
        "{place} {icon} Nothing but noise",
        "{place} {icon} Quiet your mind",
        "{place} {icon} For deep sleep",
        "Focus better with {name} {icon}",
        "{place} {icon} Soft and constant",
        "{place} {icon} Mask the noise",
    ),
    "respiracio": (
        "{place} {icon} Breathe with me",
        "Take a breath · {name} {icon}",
        "{place} {icon} A minute to reset",
        "{place} {icon} Calm down with your breath",
        "Breathe slowly · {name} {icon}",
        "{place} {icon} Follow the circle",
        "{place} {icon} In and out",
        "A calm breath · {name} {icon}",
        "{place} {icon} Pause and breathe",
        "{place} {icon} Let it go",
    ),
}

# Invitació segons el format.
INVITES = {
    "pomodoro": (
        "Pick one task, put your phone away and start the timer.",
        "Perfect for studying, exams, coding or deep work.",
        "Twenty-five minutes at a time, you've got this.",
        "Ideal for exam season, essays and long to-do lists.",
        "Make a warm drink, open your notes and begin.",
        "Study, write or plan your week, one session at a time.",
        "Great for students, writers and remote workers.",
        "Stay focused, take your breaks and be proud of the progress.",
        "Small sessions, big progress.",
        "Turn procrastination into progress, one session at a time.",
    ),
    "dormir": (
        "Perfect for falling asleep, naps or a calm night.",
        "Leave it on and let sleep come slowly.",
        "No alarms, no timers, just rest.",
        "Turn down the lights and let your body relax.",
        "Ideal for insomnia, naps or long nights.",
        "Hours of calm to help you drift off.",
        "Lie down, breathe slowly and let go.",
        "For deep sleep and peaceful dreams.",
        "Your bedtime ritual starts here.",
        "Sleep sounds to quiet a busy mind.",
    ),
    "llegir": (
        "Perfect for reading, journaling or a quiet evening.",
        "Grab your book and a blanket.",
        "No timer, no alarms, just pages and calm.",
        "For book lovers and quiet souls.",
        "Ideal for novels, notes, poetry or your journal.",
        "Read slowly and enjoy every page.",
        "Make some tea and get lost in a story.",
        "The perfect background for a long chapter.",
        "Silence your phone and let the story take over.",
        "For cozy reading nights.",
    ),
    "ambient": (
        "Perfect for studying, working, reading or sleeping.",
        "No music, no talking, just the sounds of the place.",
        "Leave it running in the background and breathe.",
        "Ideal when music is too distracting.",
        "Turn it up, turn it down, let it fill the silence.",
        "Great for focus, relaxation or a quiet evening.",
        "Background sounds for whatever your day needs.",
        "Calm sounds without anything asking for your attention.",
        "For work, rest and everything in between.",
        "Put on your headphones and stay a while.",
    ),
    "rol": (
        "Perfect for D&D, tabletop RPGs and fantasy writing.",
        "Set the mood for your next session.",
        "No narration, no timer, just the world around your party.",
        "For DMs, players and fantasy readers.",
        "Let the background build the world for you.",
        "Ideal for campaigns, one-shots and worldbuilding.",
        "Bring your table to life.",
        "Great for writing fantasy or reading epic stories.",
        "Your players will feel like they are really there.",
        "Atmosphere for heroes, villains and dice.",
    ),
    "soroll": (
        "Perfect for sleeping, studying or calming a busy mind.",
        "Masks noises and helps you stay focused.",
        "No music, no voices, no sudden changes.",
        "Ideal for babies, light sleepers and open offices.",
        "Steady sound for deep sleep and concentration.",
        "Block out the world and find your focus.",
        "Great for tinnitus, naps and long study sessions.",
        "Consistent and soothing, all night long.",
        "For sleep, focus and everything in between.",
        "Let the noise cover everything else.",
    ),
    "respiracio": (
        "Follow the circle: breathe in as it grows, out as it shrinks.",
        "A few minutes to calm stress and anxiety.",
        "Perfect before an exam, a meeting or bed.",
        "Slow breathing to reset your body and mind.",
        "Breathe gently and never force it.",
        "Your quick reset for a busy day.",
        "Calm your nervous system in minutes.",
        "Take this moment just for yourself.",
        "Let your breath slow everything down.",
        "Short, simple and calming.",
    ),
}

# On es pot veure sencer. {where} = «link in bio» o l'enllaç del canal.
CTAS = (
    "🕯️ The full version is on YouTube: {where}",
    "▶️ Watch the full ambience on YouTube: {where}",
    "🎧 Hours of it on our YouTube channel: {where}",
    "📺 Full video on YouTube, {where}",
    "🕯️ Want the long version? It's on YouTube: {where}",
    "▶️ Listen to the whole thing on YouTube: {where}",
    "🎧 The complete video is waiting on YouTube: {where}",
    "📺 Stay longer with the full video on YouTube: {where}",
    "🕯️ Full ambience on The Amber Window YouTube: {where}",
    "▶️ More hours of calm on YouTube: {where}",
)

CLOSERS = (
    "Save this for a quiet moment 🤍",
    "Send this to someone who needs to slow down 💌",
    "Save it for your next study session 📌",
    "Tag a friend who'd love this place ✨",
    "Which sound do you want next? Tell us below 👇",
    "Save it for tonight 🌙",
    "Share it with your study buddy 📚",
    "Follow for a new cozy place every week 🕯️",
    "Would you stay here for a while? 🤍",
    "Where would you rather be right now? 👇",
    "Keep this for a calm evening ✨",
    "Come back whenever you need some calm 🤍",
)

ICONS = {
    "rain": ("🌧️", "☔", "💧"), "fire": ("🔥", "🕯️", "✨"), "sea": ("🌊", "🐚", "⛵"), "water": ("💧", "🌿", "🪨"),
    "forest": ("🌿", "🍃", "🐦"), "city": ("☕", "🌆", "🏙️"), "wind": ("❄️", "🌬️", "🧣"), "train": ("🚂", "✈️", "🌄"),
    "night": ("🌙", "✨", "🌌"), "music": ("🎶", "📻", "🎵"), "default": ("✨", "🕯️", "🤍"),
}

# ---------------------------------------------------------------- hashtags

FORMAT_TAGS = {
    "pomodoro": ("#studywithme", "#pomodoro", "#studymotivation", "#studyvibes", "#focusmusic", "#studygram"),
    "dormir": ("#sleepsounds", "#sleepmusic", "#relaxingsounds", "#insomnia", "#sleepwell", "#bedtime"),
    "llegir": ("#readingambience", "#bookstagram", "#cozyreading", "#readingnook", "#booklover", "#readingtime"),
    "ambient": ("#ambience", "#ambientsounds", "#asmrsounds", "#naturesounds", "#backgroundsounds", "#relaxingsounds"),
    "rol": ("#dndambience", "#dnd", "#ttrpg", "#dungeonsanddragons", "#fantasyambience", "#rpgmusic"),
    "soroll": ("#whitenoise", "#brownnoise", "#sleepsounds", "#focussounds", "#noiseforsleep", "#babysleep"),
    "respiracio": ("#breathwork", "#breathingexercise", "#mindfulness", "#anxietyrelief", "#calm", "#meditation"),
}
FAMILY_TAGS = {
    "rain": ("#rainsounds", "#rainyday", "#rainambience"), "fire": ("#fireplacesounds", "#fireplace", "#cozynight"),
    "sea": ("#oceansounds", "#wavesounds", "#seaside"), "water": ("#watersounds", "#riversounds", "#naturesounds"),
    "forest": ("#forestsounds", "#birdsong", "#naturesounds"), "city": ("#cafeambience", "#coffeeshopvibes", "#citysounds"),
    "wind": ("#winterambience", "#snowyday", "#windsounds"), "train": ("#trainsounds", "#travelvibes", "#nighttrain"),
    "night": ("#nightambience", "#nightsounds", "#calmnight"), "music": ("#lofi", "#calmmusic", "#chillvibes"),
    "default": ("#cozyvibes", "#relaxing", "#calm"),
}
SEASONAL_TAGS = {"Nadal": "#christmasambience", "Hivern": "#winterambience", "Tardor": "#autumnambience", "Primavera": "#springambience",
                 "Estiu": "#summerambience", "Halloween": "#halloweenambience", "Pasqua": "#springvibes"}
GENERAL_TAGS = ("#cozyambience", "#cozyvibes", "#cozyaesthetic", "#ambience", "#relaxingsounds", "#calmvibes", "#slowliving", "#cozyhome")


def _pick(options, seed: int, salt: int):
    """Opció «aleatòria» però sempre la mateixa per al mateix número: cada peça gira pel seu compte."""
    digest = hashlib.sha256(f"{seed}:{salt}".encode()).digest()
    return options[int.from_bytes(digest[:8], "big") % len(options)]


def hashtags(theme: str, fmt: str, sound: str, seed: int = 0) -> list[str]:
    """Cinc hashtags: un general, el de la temporada (si n'hi ha), un del format i un del so, i un altre que va canviant."""
    family = sound_family(sound)
    fmt_tags = FORMAT_TAGS.get(fmt, FORMAT_TAGS["ambient"])
    if fmt == "soroll":
        fmt_tags = tuple(t for t in fmt_tags if t != ("#whitenoise" if "Brown" in sound else "#brownnoise"))
    tags = [_pick(GENERAL_TAGS, seed, 1)]
    if theme in SEASONAL_TAGS:
        tags.append(SEASONAL_TAGS[theme])
    tags.append(fmt_tags[0])
    tags.append(_pick(FAMILY_TAGS[family], seed, 2))
    for pool, salt in ((fmt_tags[1:], 3), (GENERAL_TAGS, 4), (FAMILY_TAGS[family], 5), (fmt_tags, 6)):
        candidate = _pick(pool, seed, salt)
        if len(tags) < 5 and candidate not in tags:
            tags.append(candidate)
    for extra in GENERAL_TAGS:
        if len(tags) < 5 and extra not in tags:
            tags.append(extra)
    return tags[:5]


def mood_line(sound: str, seed: int) -> str:
    """Una frase sobre el so del vídeo (per a reels i descripcions)."""
    return _pick(MOODS[sound_family(sound)], seed, 8)


def reel_caption(public_theme: str, subtitle: str, *, theme: str = "", fmt: str = "pomodoro", channel_url: str = "",
                 facebook: bool = False, seed: int = 0) -> str:
    """Text del reel. `seed` canvia segons el vídeo i el Short, perquè cap reel repetisca el text de l'anterior."""
    place = public_theme if public_theme.lower().startswith("cozy") or fmt == "soroll" else f"Cozy {public_theme}"
    sound = subtitle.split("·", 1)[-1].strip() if "·" in subtitle else subtitle
    family = sound_family(sound)
    fmt_key = fmt if fmt in HOOKS else "ambient"
    where = channel_url if facebook and channel_url else "link in bio"
    hook = _pick(HOOKS[fmt_key], seed, 0).format(place=place, name=public_theme, icon=_pick(ICONS[family], seed, 9))
    return "\n".join([
        hook,
        f"{subtitle}. {mood_line(sound, seed)}",
        "",
        _pick(INVITES[fmt_key], seed, 10),
        _pick(CTAS, seed, 11).format(where=where),
        "",
        _pick(CLOSERS, seed, 12),
        "",
        " ".join(hashtags(theme, fmt, sound, seed)),
    ])
