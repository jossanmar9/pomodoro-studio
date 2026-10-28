# Instal·lació local en Linux Mint i generació d’imatges

Configuració de referència reportada el 29/10/2026: Linux Mint 22.3 Cinnamon, Python del sistema 3.12.3, NVIDIA RTX 3060 de 12 GB i uns 32 GB de RAM. L’usuari ha confirmat que Forge arranca amb CUDA després de les correccions de dependències següents. La generació completa des de Pomodoro encara s’ha de comprovar en cada instal·lació.

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

Obri <http://127.0.0.1:8000>. Deixa el terminal obert; Ctrl+C para el servei. `cp -n` conserva un `.env` que ja existisca. La carpeta `.venv` de Pomodoro és independent de la de Forge.

## 3. Instal·lar Forge amb Python separat

[Forge](https://github.com/lllyasviel/stable-diffusion-webui-forge) usa una branca de dependències anterior a Python 3.12; el seu [llançador](https://github.com/lllyasviel/stable-diffusion-webui-forge/blob/main/modules/launch_utils.py) recomana Python 3.10. No canvies el Python del sistema. Prepararem un Python 3.10 gestionat per [uv](https://docs.astral.sh/uv/getting-started/installation/).

En un altre terminal:

```bash
curl -LsSf https://astral.sh/uv/install.sh -o /tmp/install-uv.sh
sh /tmp/install-uv.sh
mkdir -p ~/IA
cd ~/IA
git clone git@github.com:lllyasviel/stable-diffusion-webui-forge.git
cd stable-diffusion-webui-forge
~/.local/bin/uv venv --python 3.10 --seed venv
```

Si uses una ruta d’instal·lació d’uv personalitzada, substituïx `~/.local/bin/uv` per la seua ruta. No actives l’entorn `.venv` de Pomodoro per instal·lar dependències de Forge.

### Model SDXL

Descarrega el [model SDXL base oficial de Stability AI](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0). És una descàrrega de diversos GB, addicional a PyTorch i les biblioteques CUDA. Conserva també la seua llicència Open RAIL++-M i revisa les condicions aplicables a l’ús previst.

```bash
mkdir -p models/Stable-diffusion
curl -fL --retry 3 --continue-at - \
  'https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors' \
  -o models/Stable-diffusion/sd_xl_base_1.0.safetensors
```

L’opció `--continue-at -` permet reprendre una descàrrega incompleta. Si l’ordre falla, no tractes el fitxer parcial com un model complet.

Arranca Forge:

```bash
venv/bin/python launch.py --api --port 7860
```

En la primera arrancada s’instal·len dependències. Espera el missatge `Running on local URL` i obri <http://127.0.0.1:7860>. El registre ha d’identificar la GPU com a dispositiu CUDA. No cal instal·lar manualment el CUDA Toolkit complet per a seguir esta recepta.

### Error de CLIP: `No module named 'pkg_resources'`

El [commit de CLIP usat per Forge](https://github.com/openai/CLIP/blob/d50d76daa670286dd6cacf3bcd80b5e4823fc8e1/setup.py) encara importa `pkg_resources`. Si falla la compilació aïllada, dins de la carpeta de Forge:

```bash
venv/bin/python -m pip install 'setuptools==69.5.1' wheel
venv/bin/python -m pip install --no-build-isolation \
  'https://github.com/openai/CLIP/archive/d50d76daa670286dd6cacf3bcd80b5e4823fc8e1.zip'
venv/bin/python launch.py --api --port 7860
```

69.5.1 és la versió de setuptools fixada pel [fitxer de requisits del commit de Forge provat](https://github.com/lllyasviel/stable-diffusion-webui-forge/blob/dfdcbab685e57677014f05a3309b48cc87383167/requirements_versions.txt). No reinstal·les PyTorch ni elimines el model per este error.

### Error: `numpy.dtype size changed`

És una incompatibilitat binària de NumPy i una extensió, en este cas `scikit-image`. La [documentació de NumPy](https://numpy.org/doc/stable/user/troubleshooting-importerror.html#downstream-importerror-attributeerror-or-c-api-abi-incompatibility) explica el diagnòstic. Per al commit de Forge anterior, restaura les versions que fixa el projecte:

```bash
venv/bin/python -m pip install --force-reinstall --no-deps \
  'numpy==1.26.2' 'scikit-image==0.21.0'
venv/bin/python -c 'import numpy, skimage; print(numpy.__version__, skimage.__version__)'
```

Ha de mostrar `1.26.2 0.21.0`. Torna a executar `venv/bin/python launch.py --api --port 7860`. Si reapareix després d’instal·lar extensions, consulta `venv/bin/python -m pip check` per identificar qui ha canviat les dependències. No actualitzes tots els paquets indiscriminadament: una futura versió de Forge pot requerir versions diferents.

L’avís sobre `insightface` no va ser l’error que bloquejava esta arrancada; és una dependència de preprocessadors opcionals i no s’ha hagut d’instal·lar per arribar a la interfície.

## 4. Connectar Forge amb Pomodoro

En la carpeta **de Pomodoro**, obri `.env` (Ctrl+H en l’explorador mostra els fitxers ocults). Modifica les línies existents, sense duplicar-les:

```env
IMAGE_A1111_URL=http://127.0.0.1:7860
IMAGE_A1111_MODEL=sd_xl_base_1.0.safetensors
IMAGE_GENERATION_DIR=./data/generated-images
```

Si uses un altre checkpoint, posa el seu nom exacte. Deixa `IMAGE_A1111_MODEL=` buit per usar el model seleccionat en Forge. Reinicia **Pomodoro**, perquè llija `.env`; mantín **Forge** obert.

Comprova l’API local:

```bash
curl --fail http://127.0.0.1:7860/sdapi/v1/options
```

Ha de retornar JSON. Estos passos són per a dos serveis executats directament en el mateix equip. En Docker, `127.0.0.1` apunta al contenidor i cal configurar la connectivitat amb el host; no uses esta URL sense adaptar-la.

## 5. Primera generació

1. Obri el projecte en Pomodoro.
2. En **Constructor d’ambientació original**, tria un preset i ajusta tema, clima i llum.
3. En **Generar imatge · IA opcional**, selecciona **a1111** i prem **Generar imatge**.
4. Espera la previsualització; la primera generació carrega el model en GPU.
5. Revisa el resultat, posa un nom i registra la llicència/notes que corresponguen. Prem **Acceptar com a fons**.
6. El fons apareixerà seleccionat en **Preparar vídeo**, amb la procedència al JSON lateral d’`assets/backgrounds/`.

Si només apareix `manual`, revisa `.env` i reinicia Pomodoro. Si apareix `a1111` però falla, comprova l’API, el terminal de Forge, el model carregat i la memòria GPU. Abans d’acceptar-la, la imatge és temporal i no forma part dels assets.

## 6. Cada vegada que ho uses

- Per generar imatges noves: arranca Forge i Pomodoro.
- Per renderitzar amb recursos guardats: només cal Pomodoro i FFmpeg.
- La instal·lació, la descàrrega del model i la configuració es fan una vegada.
- Pots crear [dos accessos directes](ACCESSOS_DIRECTES.md) per evitar escriure les ordres cada vegada.

La generació local de vídeo, efectes i música amb altres models és una possibilitat futura; esta versió només integra A1111/Forge per a imatges. Els altres recursos es poden importar manualment. La GPU disponible no garantix que tots els models o resolucions funcionen: executa els generadors d’un en un i comprova les seues condicions i requisits.
