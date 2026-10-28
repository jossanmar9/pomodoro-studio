"""Construcció segura d'ordres FFmpeg per al renderitzat de Pomodoro Studio."""
from dataclasses import dataclass, field
from pathlib import Path
from app.services.timer import TimelineSummary
SUPPORTED_IMAGE_SUFFIXES={".jpg",".jpeg",".png",".webp"}; SUPPORTED_VIDEO_SUFFIXES={".mp4",".mov",".mkv",".webm"}; SUPPORTED_AUDIO_SUFFIXES={".mp3",".wav",".ogg",".m4a",".flac",".aac"}; FONT="DejaVu Sans"
@dataclass(frozen=True)
class AudioTrack: path:Path; volume:float=.25
@dataclass(frozen=True)
class RenderSpec: background:Path; output:Path; resolution:str; timeline:TimelineSummary; fps:int=30; ambience:list[AudioTrack]=field(default_factory=list); music:AudioTrack|None=None

def _escape_drawtext(text:str)->str: return text.replace("\\","\\\\").replace(":","\\:").replace("'","\\'")
def build_timer_filters(timeline:TimelineSummary)->str:
    """Genera els overlays de fase, compte arrere i sessió segons el temps `t`."""
    filters=[]
    for segment in timeline.segments:
        start,end=segment.start_seconds,segment.end_seconds; minutes=f"floor(({end}-t)/60)"; seconds=f"floor({end}-t)-60*floor(({end}-t)/60)"; timer=f"%{{eif\\:{minutes}\\:d}}\\:%{{eif\\:{seconds}\\:d}}"; phase="CONCENTRACIÓ" if segment.kind.value=="FOCUS" else "DESCANS"; session=f"SESSIÓ {segment.session}"; enable=f"between(t\\,{start}\\,{max(start,end-.001)})"; prefix=f"drawtext=font='{FONT}':"
        filters += [f"{prefix}text='{_escape_drawtext(phase)}':fontcolor=white@0.88:fontsize=h/32:x=(w-text_w)/2:y=h*0.37:enable='{enable}'",f"{prefix}text='{timer}':fontcolor=white:fontsize=h/9:borderw=2:bordercolor=black@0.35:x=(w-text_w)/2:y=(h-text_h)/2:enable='{enable}'",f"{prefix}text='{_escape_drawtext(session)}':fontcolor=white@0.72:fontsize=h/44:x=(w-text_w)/2:y=h*0.62:enable='{enable}'"]
    return ",".join(filters)
def _validate_audio(track:AudioTrack)->None:
    if track.path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES: raise ValueError(f"Format d'àudio no compatible: {track.path.suffix}")
    if not 0<=track.volume<=1: raise ValueError("El volum ha d'estar entre 0 i 1")
def build_ffmpeg_command(spec:RenderSpec)->list[str]:
    """Construïx una ordre FFmpeg sense shell per a vídeo, overlays i àudio."""
    suffix=spec.background.suffix.lower()
    if suffix not in SUPPORTED_IMAGE_SUFFIXES|SUPPORTED_VIDEO_SUFFIXES: raise ValueError(f"Format de fons no compatible: {suffix}")
    try: width,height=(int(value) for value in spec.resolution.lower().split("x",1))
    except (ValueError,AttributeError) as exc: raise ValueError("Resolució no vàlida; usa el format amplàriaxaltura") from exc
    if width<=0 or height<=0: raise ValueError("La resolució ha de ser positiva")
    command=["ffmpeg","-y","-nostdin","-progress","pipe:1","-nostats"]; command += ["-loop","1","-framerate",str(spec.fps),"-i",str(spec.background)] if suffix in SUPPORTED_IMAGE_SUFFIXES else ["-stream_loop","-1","-i",str(spec.background)]
    audio_tracks=[*spec.ambience,*([spec.music] if spec.music else [])]
    for track in audio_tracks: _validate_audio(track); command += ["-stream_loop","-1","-i",str(track.path)]
    base=f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"; timer=build_timer_filters(spec.timeline); parts=[f"[0:v]{base},{timer}[vout]" if timer else f"[0:v]{base}[vout]"]
    for i,track in enumerate(audio_tracks,1): parts.append(f"[{i}:a]volume={track.volume}[a{i}]")
    if audio_tracks: parts.append("".join(f"[a{i}]" for i in range(1,len(audio_tracks)+1))+f"amix=inputs={len(audio_tracks)}:duration=longest:normalize=0[aout]")
    command += ["-filter_complex",";".join(parts),"-map","[vout]"]
    if audio_tracks: command += ["-map","[aout]","-c:a","aac","-b:a","192k"]
    command += ["-t",str(spec.timeline.total_seconds),"-r",str(spec.fps),"-c:v","libx264","-preset","medium","-crf","20","-pix_fmt","yuv420p","-movflags","+faststart"]
    if not audio_tracks: command.append("-an")
    command.append(str(spec.output)); return command
