# Instal·lació local en Linux Mint

Configuració de referència reportada el 29/10/2026: Linux Mint 22.3 Cinnamon, Python del sistema 3.12.3, NVIDIA RTX 3060 de 12 GB i uns 32 GB de RAM.

## 1. Descarregar Pomodoro

Si encara no tens el projecte, amb [SSH configurat en GitHub](https://docs.github.com/en/authentication/connecting-to-github-with-ssh):

```bash
git clone git@github.com:jossanmar9/pomodoro-studio.git
cd pomodoro-studio
```

Alternativa HTTPS: `git clone https://github.com/jossanmar9/pomodoro-studio.git` (un repositori privat requerix autenticació). Si ja tens una còpia, entra en la seua carpeta i actualitza-la amb `git pull --ff-only` després de revisar els canvis locals.

## 2. Instal·lar i arrancar Pomodoro sense Docker

```bash
sudo apt update
sudo apt install git curl python3-venv python3-pip ffmpeg fonts-dejavu-core libgl1 libglib2.0-0
```

Dins de la carpeta del projecte:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp -n .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Obri <http://127.0.0.1:8000>. Deixa el terminal obert; Ctrl+C para el servei. `cp -n` conserva un `.env` que ja existisca.

## 3. Cada vegada que ho uses

- Només cal arrancar Pomodoro (amb FFmpeg instal·lat). Ja no es fa servir Forge.
- Pots crear l'[accés directe](ACCESSOS_DIRECTES.md) per evitar escriure les ordres cada vegada.

Si tenies Forge instal·lat només per a Pomodoro, el pots esborrar: `rm -rf ~/IA/stable-diffusion-webui-forge`.
