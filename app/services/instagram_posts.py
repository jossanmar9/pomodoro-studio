"""Publicacions d'imatges a Instagram: una imatge sola o un carrusel de 3, amb una pregunta.

Tria fons a l'atzar que encara no s'han publicat (de temes diferents en el carrusel), els
retalla en vertical (1080x1350), hi posa la pregunta i el nom del lloc amb la lletra del canal,
i escriu un text variat amb hashtags. La llista de fons ja publicats es guarda en
data/instagram-posts.json perquè no es repetisquen.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.services.captions import CTAS, ICONS, _pick, hashtags, mood_line, scene_line, sound_family

W, H = 1080, 1350
CREAM, AMBER = (255, 247, 232), (243, 196, 122)

# Preguntes del carrusel (3 llocs: 1, 2 o 3).
CAROUSEL_QUESTIONS = (
    "Which one would you choose?", "Which one is the most relaxing?", "Where would you study today?", "Pick your rainy day spot",
    "Where would you spend the night?", "Which one feels like home?", "Where would you read all day?", "Which one would help you focus?",
    "Pick one to fall asleep in", "Where would you drink your coffee?", "Which view would you wake up to?", "Where would you hide from the world?",
    "Which one is your comfort place?", "Where would you write your novel?", "Choose your cozy corner", "Which one would you move into?",
    "Where would you spend a lazy Sunday?", "Which one calms you the most?", "Pick your perfect study room", "Where would you wait out the storm?",
    "Which window would you sit by?", "Where would your cat be happiest?", "Which one matches your mood today?", "Where would you spend a snow day?",
    "Choose your evening escape", "Which desk would you work at?", "Where would you finish your book?", "Which one would you visit first?",
    "Where would you spend your exam week?", "Which one looks the coziest?", "Pick a place to slow down", "Where would you have tea tonight?",
    "Which one would you never leave?", "Where would you take a nap?", "Choose your dream reading nook", "Which one sounds the most peaceful?",
    "Where would you spend your birthday?", "Which one is perfect for a rainy day?", "Pick your getaway for tonight", "Which one would you stay in forever?",
)

# Preguntes de la imatge sola.
SINGLE_QUESTIONS = (
    "Study here or sleep here?", "Would you stay here all day?", "Could you focus here?", "Would you read here tonight?",
    "Coffee or tea in this place?", "How long would you stay here?", "Would you live here?", "Rain or sunshine here?",
    "Morning or night here?", "Would this help you relax?", "Book or nap?", "Could you write here?",
    "Rate this place from 1 to 10", "Would you bring a friend or come alone?", "What would you do here first?", "Is this your dream desk?",
    "Would you work from here?", "What music would you play here?", "Stay inside or go for a walk?", "Would you fall asleep here?",
    "One hour or the whole day?", "What would you read here?", "Would this be your study spot?", "Is this cozy enough for you?",
    "Would you spend a rainy weekend here?", "Hot chocolate or coffee here?", "Could you stay off your phone here?", "Would your cat love it here?",
)

ANSWER_PROMPTS = (
    "1, 2 or 3? Tell us in the comments 👇", "Comment your number 👇", "Drop 1, 2 or 3 below 👇", "Vote in the comments: 1, 2 or 3 ✨",
    "Tell us your pick below 🕯️", "Which number? We read every comment 🤍", "Your choice in the comments 👇", "1, 2 or 3? No wrong answers 🤍",
)
SINGLE_PROMPTS = (
    "Tell us in the comments 👇", "Answer below 🕯️", "We read every comment 🤍", "Let us know below ✨",
    "Your answer in the comments 👇", "Be honest in the comments 😌",
)


@dataclass(frozen=True)
class Pick:
    path: Path
    name: str          # nom públic del lloc
    theme: str         # tema intern (per als hashtags de temporada)
    sound: str         # nom públic del so


def _posted_file() -> Path:
    from app.config import settings
    return settings.instagram_token_file.parent / "instagram-posts.json"


def posted_names(file: Path | None = None) -> set[str]:
    try:
        data = json.loads((file or _posted_file()).read_text(encoding="utf-8"))
        return {entry["name"] for entry in data if isinstance(entry, dict) and "name" in entry}
    except (OSError, ValueError, TypeError):
        return set()


def remember_posted(names: list[str], post_id: str, file: Path | None = None) -> None:
    file = file or _posted_file()
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        data = data if isinstance(data, list) else []
    except (OSError, ValueError):
        data = []
    stamp = datetime.utcnow().isoformat(timespec="seconds")
    data += [{"name": name, "post": post_id, "date": stamp} for name in names]
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def choose_backgrounds(groups: list[dict], count: int, style: str | None, *, folder: Path, posted: set[str],
                       rng: random.Random | None = None) -> list[Pick]:
    """Fons a l'atzar de l'estil triat, de temes diferents i, si pot ser, encara no publicats."""
    from app.services.autopilot_plan import ENVIRONMENTS
    from app.themes import publication_theme
    rng = rng or random.Random()
    candidates = [(group["theme"], item) for group in groups for item in group["items"]
                  if not style or item.get("style", "realista") == style]
    if not candidates:
        raise ValueError("No hi ha fons d'eixe estil")
    fresh = [c for c in candidates if c[1]["name"] not in posted]
    pool = fresh if len({t for t, _ in fresh}) >= count else candidates
    rng.shuffle(pool)
    chosen, themes = [], set()
    for theme, item in pool:
        if theme in themes:
            continue
        env = ENVIRONMENTS.get(item.get("environment") or "")
        chosen.append(Pick(folder / item["name"], publication_theme(theme), theme, env.public_label if env else "Ambience"))
        themes.add(theme)
        if len(chosen) == count:
            return chosen
    raise ValueError("No hi ha prou temes diferents per al carrusel")


def _font(path: Path | None, size: int):
    for candidate in ([str(path)] if path else []) + ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "DejaVuSerif-Bold.ttf"]:
        try:
            font = ImageFont.truetype(candidate, size)
            try:
                font.set_variation_by_axes([700])  # Lora variable: negreta
            except (OSError, ValueError, AttributeError):
                pass
            return font
        except OSError:
            continue
    return ImageFont.load_default()


def _two_lines(text: str) -> list[str]:
    words = text.upper().split()
    if len(words) <= 3:
        return [" ".join(words)]
    half = (len(words) + 1) // 2
    return [" ".join(words[:half]), " ".join(words[half:])]


def make_slide(source: Path, output: Path, *, name: str, number: int | None = None, total: int = 3, question: str = "",
               hint: str = "", font: Path | None = None) -> Path:
    """Imatge vertical 1080x1350 amb la pregunta (si n'hi ha), el número i el nom del lloc."""
    with Image.open(source) as image:
        image = image.convert("RGB")
        scale = max(W / image.width, H / image.height)
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left, top = (image.width - W) // 2, (image.height - H) // 2
    image = image.crop((left, top, left + W, top + H))
    shade = Image.new("L", (1, H))
    for y in range(H):
        alpha = 0.0
        if question and y < H * 0.34:
            alpha = 200 * (1 - y / (H * 0.34)) ** 1.2
        elif not question and y < H * 0.12:
            alpha = 90 * (1 - y / (H * 0.12))
        if y > H * 0.62:
            alpha = max(alpha, 215 * ((y - H * 0.62) / (H * 0.38)) ** 1.3)
        shade.putpixel((0, y), int(alpha))
    image = Image.composite(Image.new("RGB", (W, H), (8, 6, 4)), image, shade.resize((W, H)))
    texts = []
    if question:
        lines = _two_lines(question)
        size = 70
        measure = ImageDraw.Draw(image)
        while size > 44 and max(measure.textlength(line, font=_font(font, size)) for line in lines) > W - 100:
            size -= 4
        for n, line in enumerate(lines):
            texts.append(((W // 2, 90 + n * int(size * 1.2)), line, _font(font, size), CREAM, "mt"))
        if hint:
            texts.append(((W // 2, 100 + len(lines) * int(size * 1.2)), hint, _font(font, 34), AMBER, "mt"))
    elif number:
        texts.append(((W - 60, 60), f"{number}/{total}", _font(font, 36), CREAM, "rt"))
    if number:
        texts.append(((64, H - 190), str(number), _font(font, 150), AMBER, "ls"))
    texts.append(((64, H - 80), name.upper(), _font(font, 66 if len(name) < 22 else 52), CREAM, "ls"))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for (x, y), text, f, _, anchor in texts:
        glow_draw.text((x + 2, y + 3), text, font=f, fill=(0, 0, 0, 190), anchor=anchor)
    result = image.convert("RGBA")
    result.alpha_composite(glow.filter(ImageFilter.GaussianBlur(5)))
    draw = ImageDraw.Draw(result)
    for (x, y), text, f, colour, anchor in texts:
        draw.text((x, y), text, font=f, fill=colour, anchor=anchor)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.convert("RGB").save(output, "JPEG", quality=92)
    return output


def post_caption(picks: list[Pick], question: str, seed: int) -> str:
    """Text de la publicació: la pregunta, cada lloc amb una frase, on vore'l a YouTube i cinc hashtags."""
    first = picks[0]
    icon = _pick(ICONS[sound_family(first.sound)], seed, 9)
    lines = [f"{question} {icon}"]
    if len(picks) > 1:
        lines.append(_pick(ANSWER_PROMPTS, seed, 20))
        lines.append("")
        for n, pick in enumerate(picks, 1):
            lines.append(f"{n} · {pick.name}: {scene_line(pick.name, seed + n)}")
    else:
        lines.append(_pick(SINGLE_PROMPTS, seed, 20))
        lines.append("")
        lines.append(f"{first.name}. {scene_line(first.name, seed)} {mood_line(first.sound, seed)}")
    lines += ["", _pick(CTAS, seed, 11).format(where="link in bio"), "", " ".join(hashtags(first.theme, "ambient", first.sound, seed))]
    return "\n".join(lines)


def prepare_post(groups: list[dict], *, kind: str, style: str | None, folder: Path, out_dir: Path, font: Path | None,
                 seed: int | None = None, posted: set[str] | None = None) -> tuple[list[Path], str, list[str]]:
    """Fa les imatges i el text. Torna (imatges, text, noms dels fons usats)."""
    seed = random.randrange(1_000_000) if seed is None else seed
    rng = random.Random(seed)
    count = 3 if kind == "carrusel" else 1
    picks = choose_backgrounds(groups, count, style, folder=folder, posted=posted if posted is not None else posted_names(), rng=rng)
    questions = CAROUSEL_QUESTIONS if count > 1 else SINGLE_QUESTIONS
    question = _pick(questions, seed, 21)
    hint = "Swipe to see all three  »" if count > 1 else _pick(("Tell us in the comments", "Answer in the comments", "Be honest"), seed, 22)
    images = []
    for n, pick in enumerate(picks, 1):
        images.append(make_slide(pick.path, out_dir / f"instagram-{seed}-{n}.jpg", name=pick.name,
                                 number=n if count > 1 else None, total=count, question=question if n == 1 else "",
                                 hint=hint if n == 1 else "", font=font))
    return images, post_caption(picks, question, seed), [p.path.name for p in picks]
