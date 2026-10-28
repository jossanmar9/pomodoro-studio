# Guia d'ús

## 1. Preparar l'aplicació

En Linux Mint sense Docker, seguix la [guia de Python i Forge](INSTAL_LINUX_MINT.md). Després pots instal·lar els [accessos directes](ACCESSOS_DIRECTES.md).

Si encara no tens `.env`, copia `.env.example` a `.env` i inicia el servei amb:

```bash
docker compose up -d --build
```

Obri `http://localhost:8000`.

## 2. Afegir recursos

Copia els recursos a:

- `assets/backgrounds/`: JPG, JPEG, PNG, WebP, MP4, MOV, MKV o WebM.
- `assets/ambience/`: MP3, WAV, OGG, M4A, FLAC o AAC.
- `assets/music/`: música opcional en els mateixos formats d'àudio.

Registra l'origen i la llicència en `assets/REGISTRE_RECURSOS.md`. Consulta [àudios i llicències](AUDIO_I_LLICENCIES.md) per organitzar els comprovants i els crèdits.

## 3. Crear un projecte

Des del panell principal selecciona l'ambientació, minuts de concentració, descans, duració total i resolució. La duració final és exacta; l'última sessió pot ser més curta si és necessari.

## 4. Preparar la publicació

La fitxa del projecte genera una proposta en anglés de títol, descripció, capítols i etiquetes. Pots editar-la i guardar-la abans o després del renderitzat. Les metadades queden associades al projecte i es conserven en duplicar-lo.

Si el vídeo ja està generat, **Regenerar fitxers** actualitza els TXT i `metadata.json` sense tornar a codificar el vídeo. **Descarregar paquet de publicació** crea un ZIP amb els fitxers disponibles per a la pujada manual.

## 5. Generar el vídeo

Selecciona un fons, els sons ambientals i, opcionalment, música. Ajusta els volums, motor i qualitat i prem **Generar vídeo**.

Només s'executa un renderitzat alhora. La pantalla mostra el percentatge i una estimació del temps restant. Es pot cancel·lar el procés.

FFmpeg s'executa sense shell i en segon pla amb `-nostdin`; el progrés es llig des de la seua eixida estructurada.

## 6. Resultat

Cada renderitzat crea una carpeta única dins d'`output/` amb:

- `video.mp4`
- `thumbnail.jpg`
- `title.txt`
- `description.txt`
- `chapters.txt`
- `tags.txt`
- `metadata.json`
- `publication-package.zip` quan es demana des de la interfície.

La interfície i la documentació són en valencià. Les metadades públiques es generen en anglés per defecte per a facilitar un canal internacional.

## 7. Còpies de seguretat

Conserva almenys `data/`, `assets/` i els resultats d'`output/` que vulgues preservar. El contenidor es pot reconstruir; estes dades no.

## 8. Actualització

Quan hi haja una versió nova:

```bash
git pull --ff-only
docker compose up -d --build
```

Abans d'actualitzar una instal·lació amb contingut important, fes còpia de `data/`.


## Ambientacions originals opcionals

En la vista del projecte, prepara un prompt manualment o selecciona A1111/Forge si està configurat. Genera, revisa la previsualització, indica nom i llicència i prem **Acceptar com a fons**. Només aleshores s’importa a assets/backgrounds amb procedència i queda seleccionat per al vídeo. Consulta [v0.8](v0.8.md) per a configuració i API.

## Ús habitual sense Docker

La instal·lació només es fa una vegada. Per generar fons nous, arranca Forge i Pomodoro. Per preparar vídeos amb recursos ja acceptats, només cal Pomodoro. Cada servei usa un terminal; deixa’l obert i usa Ctrl+C per aturar-lo. Els accessos directes automatitzen l’arrancada i obrin el navegador.

Després de canviar `.env`, reinicia Pomodoro perquè torne a llegir la configuració. En l’explorador de fitxers de Mint, Ctrl+H mostra `.env` i `.venv`.

Per actualitzar una instal·lació Python, para Pomodoro i, dins de la seua carpeta, executa:

```bash
git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Conserva `.env`, `data/`, els recursos i les llicències. Si Git detecta canvis locals, revisa’ls abans de continuar; no els descartes per força.
