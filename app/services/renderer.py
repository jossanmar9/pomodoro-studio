"""Construcció segura d'ordres FFmpeg per al renderitzat de Pomodoro Studio."""
from dataclasses import dataclass, field
from pathlib import Path

from app.services.encoding import EncodingOptions, EncodingPlan, select_encoding
from app.services.fonts import ResolvedFonts
from app.services.timer import TimelineSummary

SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}
SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}
FONT = "DejaVu Sans"


@dataclass(frozen=True)
class AudioTrack:
    path: Path
    volume: float = .25
    # Sonoritat objectiu en LUFS; si s'indica, la pista es normalitza abans del volum.
    loudness: float | None = None


@dataclass(frozen=True)
class RenderSpec:
    background: Path
    output: Path
    resolution: str
    timeline: TimelineSummary
    fps: int = 30
    ambience: list[AudioTrack] = field(default_factory=list)
    music: AudioTrack | None = None
    encoding: EncodingOptions = field(default_factory=EncodingOptions)
    # Idioma dels textos del comptador: "va" (per defecte) o "en" per al públic del canal.
    timer_language: str = "va"
    # Tipografies de l'ambientació; None = DejaVu Sans.
    fonts: ResolvedFonts | None = None
    # Campaneta suau en acabar cada concentració i cada descans.
    chime: bool = False


def _bell(first: float, second: float, gain: float = 0.16) -> str:
    """Campaneta de dues notes generada per FFmpeg (sense fitxers ni llicències)."""
    def note(freq: float, start: float) -> str:
        env = f"gte(t\\,{start})*min(1\\,(t-{start})/0.02)*exp(-2.6*(t-{start}))"
        return (f"({env})*(sin(2*PI*{freq}*(t-{start}))+0.35*sin(2*PI*{freq * 2}*(t-{start}))"
                f"+0.12*sin(2*PI*{freq * 3}*(t-{start})))")
    return f"aevalsrc='{gain}*({note(first, 0)}+0.8*{note(second, 0.45)})':s=48000:c=stereo:d=3.2"


# Nota més greu en acabar la concentració (descans) i més aguda en acabar el descans (tornar al treball).
CHIME_FOCUS_END = (783.99, 659.25)   # sol5 → mi5
CHIME_BREAK_END = (659.25, 783.99)   # mi5 → sol5


def chime_times(timeline: TimelineSummary) -> tuple[list[int], list[int]]:
    """Moments (en ms) en què acaba cada concentració i cada descans, excepte el final del vídeo."""
    focus_end, break_end = [], []
    for segment in timeline.segments:
        if segment.end_seconds >= timeline.total_seconds:
            continue
        (focus_end if segment.kind.value == "FOCUS" else break_end).append(segment.end_seconds * 1000)
    return focus_end, break_end


TIMER_LABELS = {
    "va": ("CONCENTRACIÓ", "DESCANS", "SESSIÓ"),
    "en": ("FOCUS", "BREAK", "SESSION"),
}


def _escape_drawtext(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def font_option(path: Path | None) -> str:
    """Opció drawtext per a una tipografia: fitxer concret o DejaVu Sans del sistema."""
    if path is None:
        return f"font='{FONT}'"
    return f"fontfile='{_escape_drawtext(str(path))}'"


SHADOW = "shadowcolor=black@0.45:shadowx=2:shadowy=2"


def build_timer_filters(timeline: TimelineSummary, language: str = "va", fonts: ResolvedFonts | None = None) -> str:
    if language not in TIMER_LABELS: raise ValueError("Idioma del comptador no compatible")
    focus_label, break_label, session_label = TIMER_LABELS[language]
    if fonts and not fonts.uppercase_labels:
        focus_label, break_label, session_label = (label.capitalize() for label in (focus_label, break_label, session_label))
    label_font = font_option(fonts.label if fonts else None)
    digits_font = font_option(fonts.digits if fonts else None)
    filters = []
    # Els minuts s'ancoren a l'esquerra dels dos punts i els segons a la dreta,
    # i la línia base és fixa: així el comptador no balla encara que la
    # tipografia tinga números d'amplària o altura diferents.
    big = "fontsize=h/8:borderw=2:bordercolor=black@0.35"
    baseline = "y=(h-ascent)/2"
    gap = "h*0.022"
    for segment in timeline.segments:
        start, end = segment.start_seconds, segment.end_seconds
        minutes = f"floor(({end}-t)/60)"; seconds = f"floor({end}-t)-60*floor(({end}-t)/60)"
        phase = focus_label if segment.kind.value == "FOCUS" else break_label
        enable = f"between(t\\,{start}\\,{max(start, end-.001)})"
        filters += [
            f"drawtext={label_font}:text='{_escape_drawtext(phase)}':fontcolor=white@0.9:fontsize=h/28:{SHADOW}:x=(w-text_w)/2:y=h*0.34:enable='{enable}'",
            f"drawtext={digits_font}:text='%{{eif\\:{minutes}\\:d\\:2}}':fontcolor=white:{big}:{SHADOW}:x=w/2-{gap}-text_w:{baseline}:enable='{enable}'",
            f"drawtext={digits_font}:text='%{{eif\\:{seconds}\\:d\\:2}}':fontcolor=white:{big}:{SHADOW}:x=w/2+{gap}:{baseline}:enable='{enable}'",
            f"drawtext={label_font}:text='{_escape_drawtext(session_label)} {segment.session}':fontcolor=white@0.78:fontsize=h/40:{SHADOW}:x=(w-text_w)/2:y=h*0.62:enable='{enable}'",
        ]
    if timeline.segments:
        filters.append(f"drawtext={digits_font}:text='\\:':fontcolor=white:{big}:{SHADOW}:x=(w-text_w)/2:{baseline}")
    return ",".join(filters)


def _validate_audio(track: AudioTrack) -> None:
    if track.path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES: raise ValueError(f"Format d'àudio no compatible: {track.path.suffix}")
    if not 0 <= track.volume <= 1: raise ValueError("El volum ha d'estar entre 0 i 1")


def build_ffmpeg_command(spec: RenderSpec, *, plan: EncodingPlan | None = None) -> list[str]:
    suffix = spec.background.suffix.lower()
    if suffix not in SUPPORTED_IMAGE_SUFFIXES | SUPPORTED_VIDEO_SUFFIXES: raise ValueError(f"Format de fons no compatible: {suffix}")
    try: width, height = (int(value) for value in spec.resolution.lower().split("x", 1))
    except (ValueError, AttributeError) as exc: raise ValueError("Resolució no vàlida; usa el format amplàriaxaltura") from exc
    if width <= 0 or height <= 0: raise ValueError("La resolució ha de ser positiva")

    selected = plan or select_encoding(spec.encoding)
    command = ["ffmpeg", "-y", "-nostdin", "-progress", "pipe:1", "-nostats"]
    command += ["-loop", "1", "-framerate", str(spec.fps), "-i", str(spec.background)] if suffix in SUPPORTED_IMAGE_SUFFIXES else ["-stream_loop", "-1", "-i", str(spec.background)]
    audio_tracks = [*spec.ambience, *([spec.music] if spec.music else [])]
    for track in audio_tracks:
        _validate_audio(track); command += ["-stream_loop", "-1", "-i", str(track.path)]
    chimes: list[tuple[int, list[int]]] = []
    if spec.chime:
        for notes, times in zip((CHIME_FOCUS_END, CHIME_BREAK_END), chime_times(spec.timeline)):
            if times:
                command += ["-f", "lavfi", "-i", _bell(*notes)]
                chimes.append((len(audio_tracks) + len(chimes) + 1, times))

    base = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"; timer = build_timer_filters(spec.timeline, spec.timer_language, spec.fonts)
    parts = [f"[0:v]{base},{timer}[vout]" if timer else f"[0:v]{base}[vout]"]
    fade_out = max(0, spec.timeline.total_seconds - 2)
    mix: list[str] = []
    for i, track in enumerate(audio_tracks, 1):
        normalize = f"loudnorm=I={track.loudness:g}:TP=-2:LRA=11,aresample=48000," if track.loudness is not None else ""
        parts.append(f"[{i}:a]{normalize}volume={track.volume},afade=t=in:st=0:d=2,afade=t=out:st={fade_out}:d=2[a{i}]")
        mix.append(f"[a{i}]")
    for index, times in chimes:
        labels = [f"c{index}_{n}" for n in range(len(times))]
        parts.append(f"[{index}:a]asplit={len(times)}" + "".join(f"[{l}s]" for l in labels) if len(times) > 1 else f"[{index}:a]anull[{labels[0]}s]")
        for label, ms in zip(labels, times):
            parts.append(f"[{label}s]adelay={ms}:all=1[{label}]")
            mix.append(f"[{label}]")
    if mix:
        parts.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=longest:normalize=0,alimiter=limit=0.95[aout]")
    command += ["-filter_complex", ";".join(parts), "-map", "[vout]"]
    if mix: command += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]
    command += ["-t", str(spec.timeline.total_seconds), "-r", str(spec.fps), *selected.video_args, "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if not mix: command.append("-an")
    command.append(str(spec.output)); return command
