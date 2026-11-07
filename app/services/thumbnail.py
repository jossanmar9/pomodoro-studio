"""Generació de miniatures 1280x720."""
import subprocess
from pathlib import Path
from app.services.renderer import SHADOW, SUPPORTED_IMAGE_SUFFIXES, font_option

def build_thumbnail_command(background:Path,output:Path,text:str,fontsize:int=68,fontfile:Path|None=None)->list[str]:
    escaped=text.replace("\\","\\\\").replace(":","\\:").replace("'","\\'"); command=["ffmpeg","-y","-nostdin"]
    command += ["-i",str(background)] if background.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES else ["-ss","1","-i",str(background)]
    vf=f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,drawbox=x=0:y=0:w=iw:h=ih:color=black@0.28:t=fill,drawtext={font_option(fontfile)}:text='{escaped}':fontcolor=white:fontsize={fontsize}:borderw=2:bordercolor=black@0.35:{SHADOW}:x=(w-text_w)/2:y=(h-text_h)/2"
    return command+["-vf",vf,"-frames:v","1","-q:v","2",str(output)]
def fitting_fontsize(text:str,width:int=1180,maximum:int=68)->int:
    """Mida de lletra perquè el text càpia en una línia de la miniatura."""
    return max(28,min(maximum,int(width/(0.68*max(1,len(text))))))
def generate_thumbnail(background:Path,output:Path,text:str,fontsize:int=68,fontfile:Path|None=None)->None:
    subprocess.run(build_thumbnail_command(background,output,text,fontsize,fontfile),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)


# ---------------------------------------------------------------- miniatura del mode automàtic

THUMB_W, THUMB_H = 1280, 720
AMBER = (243, 196, 122)


def _thumb_font(path: Path | None, size: int):
    from PIL import ImageFont
    for candidate in ([str(path)] if path else []) + ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"]:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_font(draw, text: str, path: Path | None, maximum: int, minimum: int, width: int):
    size = maximum
    while size > minimum:
        font = _thumb_font(path, size)
        if draw.textlength(text, font=font) <= width:
            return font
        size -= 4
    return _thumb_font(path, minimum)


def _wrap(draw, text: str, font, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        attempt = f"{line} {word}".strip()
        if line and draw.textlength(attempt, font=font) > width:
            lines.append(line)
            line = word
        else:
            line = attempt
    return lines + ([line] if line else [])


def make_thumbnail(background: Path, output: Path, title: str, subtitle: str = "", *,
                   title_font: Path | None = None, text_font: Path | None = None) -> Path:
    """Miniatura amb la imatge viva, un degradat fosc baix i el nom gran (com a molt dues línies)."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    source = background
    if background.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        source = output.with_suffix(".frame.png")
        subprocess.run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-ss", "1", "-i", str(background), "-frames:v", "1", str(source)], check=True)
    image = Image.open(source).convert("RGB")
    scale = max(THUMB_W / image.width, THUMB_H / image.height)
    image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left, top = (image.width - THUMB_W) // 2, (image.height - THUMB_H) // 2
    image = image.crop((left, top, left + THUMB_W, top + THUMB_H))
    image = ImageEnhance.Color(image).enhance(1.12)
    image = ImageEnhance.Contrast(image).enhance(1.05)
    # Degradat de baix a dalt perquè el text es llija sense enfosquir tota la imatge.
    shade = Image.new("L", (1, THUMB_H))
    for y in range(THUMB_H):
        k = max(0.0, (y - THUMB_H * 0.38) / (THUMB_H * 0.62))
        shade.putpixel((0, y), int(215 * k ** 1.4))
    image = Image.composite(Image.new("RGB", image.size, (8, 6, 4)), image, shade.resize(image.size))
    draw = ImageDraw.Draw(image)
    margin, width = 64, THUMB_W - 128
    title = title.upper()
    font = _fit_font(draw, title, title_font, 118, 76, width)
    lines = _wrap(draw, title, font, width)[:2]
    sub_font = _fit_font(draw, subtitle.upper(), text_font or title_font, 46, 26, width) if subtitle else None
    line_h = int(font.size * 1.05)
    y = THUMB_H - margin - (int(sub_font.size * 1.5) if sub_font else 0) - line_h * len(lines)
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for n, line in enumerate(lines):
        glow_draw.text((margin + 3, y + n * line_h + 4), line, font=font, fill=(0, 0, 0, 200))
    if sub_font:
        glow_draw.text((margin + 2, y + len(lines) * line_h + 14), subtitle.upper(), font=sub_font, fill=(0, 0, 0, 200))
    image.paste(glow.filter(ImageFilter.GaussianBlur(6)), (0, 0), glow.filter(ImageFilter.GaussianBlur(6)))
    for n, line in enumerate(lines):
        draw.text((margin, y + n * line_h), line, font=font, fill=(255, 247, 232))
    if sub_font:
        draw.text((margin, y + len(lines) * line_h + 12), subtitle.upper(), font=sub_font, fill=AMBER)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, quality=92)
    if source != background:
        source.unlink(missing_ok=True)
    return output


def make_title_card(output: Path, title: str, subtitle: str = "", *, width: int = 1920, height: int = 1080,
                    title_font: Path | None = None, text_font: Path | None = None) -> Path:
    """Capa transparent amb el mateix text i la mateixa posició que la miniatura, per a l'inici del vídeo.

    Porta un degradat fosc baix, suau, perquè el text es llija; el renderitzador la fa aparéixer i esvair-se.
    """
    from PIL import Image, ImageDraw, ImageFilter
    k = width / THUMB_W
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shade = Image.new("L", (1, height))
    for y in range(height):
        f = max(0.0, (y - height * 0.45) / (height * 0.55))
        shade.putpixel((0, y), int(170 * f ** 1.4))
    layer.putalpha(shade.resize((width, height)))
    layer = Image.composite(Image.new("RGBA", (width, height), (8, 6, 4, 255)), Image.new("RGBA", (width, height), (0, 0, 0, 0)), layer.getchannel("A"))
    measure = ImageDraw.Draw(layer)
    margin, text_width = int(64 * k), width - int(128 * k)
    title = title.upper()
    font = _fit_font(measure, title, title_font, int(118 * k), int(76 * k), text_width)
    lines = _wrap(measure, title, font, text_width)[:2]
    sub = subtitle.upper()
    sub_font = _fit_font(measure, sub, text_font or title_font, int(46 * k), int(26 * k), text_width) if subtitle else None
    line_h = int(font.size * 1.05)
    y = height - margin - (int(sub_font.size * 1.5) if sub_font else 0) - line_h * len(lines)
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for n, line in enumerate(lines):
        glow_draw.text((margin + 3, y + n * line_h + 4), line, font=font, fill=(0, 0, 0, 200))
    if sub_font:
        glow_draw.text((margin + 2, y + len(lines) * line_h + int(14 * k)), sub, font=sub_font, fill=(0, 0, 0, 200))
    layer = Image.alpha_composite(layer, glow.filter(ImageFilter.GaussianBlur(6 * k)))
    draw = ImageDraw.Draw(layer)
    for n, line in enumerate(lines):
        draw.text((margin, y + n * line_h), line, font=font, fill=(255, 247, 232, 255))
    if sub_font:
        draw.text((margin, y + len(lines) * line_h + int(12 * k)), sub, font=sub_font, fill=(*AMBER, 255))
    output.parent.mkdir(parents=True, exist_ok=True)
    layer.save(output)
    return output
