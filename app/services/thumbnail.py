"""Generació de miniatures 1280x720."""
import subprocess
from pathlib import Path
from app.services.renderer import FONT, SUPPORTED_IMAGE_SUFFIXES

def build_thumbnail_command(background:Path,output:Path,text:str)->list[str]:
    escaped=text.replace("\\","\\\\").replace(":","\\:").replace("'","\\'"); font=FONT.replace(":","\\:"); command=["ffmpeg","-y","-nostdin"]
    command += ["-i",str(background)] if background.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES else ["-ss","1","-i",str(background)]
    vf=f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,drawbox=x=0:y=0:w=iw:h=ih:color=black@0.28:t=fill,drawtext=fontfile='{font}':text='{escaped}':fontcolor=white:fontsize=68:borderw=2:bordercolor=black@0.35:x=(w-text_w)/2:y=(h-text_h)/2"
    return command+["-vf",vf,"-frames:v","1","-q:v","2",str(output)]
def generate_thumbnail(background:Path,output:Path,text:str)->None:
    subprocess.run(build_thumbnail_command(background,output,text),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
