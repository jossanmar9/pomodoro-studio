# Pomodoro Studio

Aplicació privada i autohosteable per a crear, renderitzar i publicar vídeos llargs originals de tipus **Pomodoro / Study With Me / Focus Ambience**, pensats principalment per a YouTube.

> **Estat:** v0.6 estable en `main`. Desenvolupament de la v0.7 en `develop/v0.7`.

## Funcions actuals

- Projectes Pomodoro 25/5, 50/10 o personalitzats, amb duració i resolució configurables.
- Ambientacions predefinides i personalitzades, presets persistents i duplicació de projectes.
- Historial amb SQLite, filtres, edició i accions ràpides.
- Fons JPG/JPEG/PNG/WebP o vídeo MP4/MOV/MKV/WebM en bucle.
- Compte arrere, fase i número de sessió sobre el vídeo.
- Diversos sons ambientals i música opcional amb volums independents, fades i limitador.
- Renderitzat H.264/AAC amb FFmpeg en CPU (`libx264`) o NVIDIA NVENC, amb detecció i fallback automàtic a CPU.
- Perfils de qualitat ràpid, equilibrat i alta qualitat.
- Cua d'un renderitzat, protecció contra dobles enviaments, progrés, ETA i cancel·lació.
- Miniatura 1280×720 automàtica i previsualització.
- Metadades editables: títol, descripció, capítols, etiquetes i idioma.
- Regeneració de metadades sense tornar a renderitzar i paquet ZIP de publicació.
- Publicació opcional a YouTube amb OAuth 2.0, YouTube Data API v3, privacitat configurable i miniatura personalitzada.
- Metadades públiques en anglés per defecte i interfície/documentació en valencià.
- Registre de llicències dels recursos per a facilitar un ús monetitzable responsable.
- Docker/Compose i GitHub Actions amb proves automàtiques i renderitzat FFmpeg curt real.

## Posada en marxa

```bash
cp .env.example .env
docker compose up -d --build
```

Obri `http://localhost:8000`.

Per a una instal·lació Python local:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Recursos

```text
assets/backgrounds/   # imatges i vídeos de fons
assets/ambience/      # pluja, foc, vent, bosc, ones...
assets/music/         # música opcional
assets/fonts/         # tipografies pròpies o compatibles
```

Abans de publicar o monetitzar un vídeo, registra l'origen i la llicència de cada recurs en `assets/REGISTRE_RECURSOS.md`.

## Flux de treball

1. Afig els recursos multimèdia a `assets/`.
2. Crea un projecte o reutilitza un preset.
3. Configura Pomodoro, ambientació, fons, àudio, resolució, motor i qualitat.
4. Revisa o edita les metadades de publicació.
5. Genera el vídeo i consulta el progrés; pots cancel·lar-lo si cal.
6. Revisa vídeo, miniatura, metadades i llicències.
7. Descarrega el paquet de publicació o publica opcionalment a YouTube.

No es publica res automàticament.

## Fitxers generats

```text
output/2026-10-28-biblioteca-medieval-001/
├── video.mp4
├── thumbnail.jpg
├── title.txt
├── description.txt
├── chapters.txt
├── tags.txt
├── metadata.json
└── publication-package.zip   # quan es demana
```

## YouTube opcional

La integració amb YouTube no és necessària per a usar Pomodoro Studio. Per activar-la:

1. Crea un projecte en Google Cloud i activa **YouTube Data API v3**.
2. Crea un client OAuth de tipus **Desktop app**.
3. Guarda el JSON com `data/youtube-client-secret.json`.
4. Instal·la les dependències opcionals:

```bash
pip install -r requirements-youtube.txt
```

5. Genera un vídeo i usa **Publicar a YouTube** des de la fitxa del projecte.
6. En la primera autorització es guardarà el token local en `data/youtube-token.json`.

Les credencials i el token estan exclosos de Git. La privacitat per defecte és **private** i la publicació sempre requerix una acció explícita.

## Proves

```bash
python -m pytest -q
```

Amb Docker:

```bash
docker compose exec pomodoro-studio pytest -q
```

La CI usa Python 3.12, instal·la FFmpeg i DejaVu, executa les proves i genera un MP4 curt real per a detectar regressions del renderitzat.

## Arquitectura

- `app/main.py`: interfície i endpoints FastAPI.
- `app/models/`: persistència SQLite/SQLAlchemy.
- `app/services/timer.py`: línia temporal Pomodoro.
- `app/services/assets.py`: catàleg i validació de recursos.
- `app/services/renderer.py`: construcció d'ordres FFmpeg.
- `app/services/encoding.py`: CPU/NVENC i perfils de qualitat.
- `app/services/jobs.py`: cua, procés FFmpeg, progrés i cancel·lació.
- `app/services/metadata.py`: metadades i paquet de publicació.
- `app/services/thumbnail.py`: miniatura.
- `app/services/youtube.py`: OAuth i publicació opcional a YouTube.
- `app/themes.py`: noms interns i noms públics d'ambientació.

FFmpeg s'executa sense `shell=True`, amb `-nostdin`. La cua limita el sistema a un vídeo simultani i el progrés es llig des de `-progress pipe:1`.

## Documentació

- `docs/GUIA_US.md`: instal·lació i ús pas a pas.
- `docs/arquitectura.md`: components i decisions tècniques.
- `docs/recursos-i-llicencies.md`: criteris de drets d'ús.
- `docs/v0.6.md`: configuració de YouTube.
- `assets/REGISTRE_RECURSOS.md`: registre pràctic dels recursos emprats.

## Versions

- **v0.1:** flux local complet de projecte, renderitzat i fitxers finals.
- **v0.2:** previsualització, presets, duracions ràpides i controls d'àudio.
- **v0.3:** persistència avançada, edició, duplicació, filtres i validacions.
- **v0.4:** perfils de renderitzat, NVIDIA NVENC i fallback automàtic a CPU.
- **v0.5:** metadades editables, regeneració i paquet de publicació.
- **v0.6:** publicació opcional a YouTube amb OAuth 2.0.

## Full de ruta

- **v0.7 — Robustesa:** recuperació d'estats després de reinicis, errors i logs més útils, comprovacions prèvies, gestió de fitxers grans i més tests d'integració.
- **v0.8 — Shorts:** generació de clips verticals 9:16 preparats per a YouTube Shorts i reutilitzables en Reels/TikTok.
- **v0.9 — Ambientacions originals:** assistència opcional per a generar/importar ambientacions i variants de miniatura, sense convertir la IA en dependència del nucli.
- **v1.0 — Estable:** migracions de base de dades, còpies/restauració, configuració inicial guiada, revisió de seguretat, documentació i UX final.

## Limitacions actuals

- Un renderitzat interromput per un reinici no es reprén des del punt on estava.
- La v0.6 no genera encara clips verticals promocionals.
- La generació d'imatges, vídeo o música amb IA no forma part del nucli actual.
- La integració directa de publicació està centrada en YouTube.

## Drets d'autor

Pomodoro Studio està dissenyat per a contingut original o correctament llicenciat. No descarrega ni republica vídeos de tercers, música protegida o elements de franquícies sense autorització. Evita usar noms, personatges, logotips o altres elements distintius de franquícies com a substitut d'una ambientació original.
