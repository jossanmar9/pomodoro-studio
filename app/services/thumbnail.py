"""Generació de miniatures 1280x720."""
import subprocess
from pathlib import Path
from app.services.renderer import FONT, SUPPORTED_IMAGE_SUFFIXES

def build_thumbnail_command(background:Path,output:Path,text:str,fontsize:int=68)->list[str]:
    escaped=text.replace("\\","\\\\").replace(":","\\:").replace("'","\\'"); command=["ffmpeg","-y","-nostdin"]
    command += ["-i",str(background)] if background.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES else ["-ss","1","-i",str(background)]
    vf=f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,drawbox=x=0:y=0:w=iw:h=ih:color=black@0.28:t=fill,drawtext=font='{FONT}':text='{escaped}':fontcolor=white:fontsize={fontsize}:borderw=2:bordercolor=black@0.35:x=(w-text_w)/2:y=(h-text_h)/2"
    return command+["-vf",vf,"-frames:v","1","-q:v","2",str(output)]
def fitting_fontsize(text:str,width:int=1180,maximum:int=68)->int:
    """Mida de lletra perquè el text càpia en una línia de la miniatura."""
    return max(28,min(maximum,int(width/(0.68*max(1,len(text))))))
def generate_thumbnail(background:Path,output:Path,text:str,fontsize:int=68)->None:
    subprocess.run(build_thumbnail_command(background,output,text,fontsize),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
