# Pomodoro Studio

Aplicació privada i autohosteable per a crear vídeos llargs originals de tipus **Pomodoro / Study With Me / Focus Ambience**, pensats principalment per a YouTube.

> **Estat:** v0.1 implementada en `develop/v0.1`. El codi queda llest per a la validació local amb Docker/FFmpeg abans de fusionar-lo a `main`.

## Funcions de la v0.1

- Projectes Pomodoro 25/5, 50/10 o personalitzats, amb duració configurable.
- Interfície i documentació en valencià.
- Historial de projectes reobrible.
- Fons JPG, JPEG, PNG, WebP, MP4, MOV, MKV o WebM en bucle.
- Compte arrere de minuts i segons, fase i número de sessió sobre el vídeo.
- Sons ambientals múltiples i música opcional amb volum independent.
- Renderitzat H.264/AAC amb FFmpeg.
- Cua d'un treball, protecció contra dobles enviaments, barra de progrés, estimació i cancel·lació.
- Estat final sincronitzat amb SQLite i recuperable després de reiniciar la web.
- Miniatura 1280×720 automàtica.
- Fitxers finals: vídeo, miniatura, títol, descripció, capítols i metadata JSON.
- Noms de carpeta segurs i únics, validació de paràmetres i recursos restringits a assets.
- Docker i Docker Compose amb FFmpeg i DejaVu.
- Tests del timeline, FFmpeg i metadades.

## Posada en marxa

```bash
docker compose up -d --build
```

Obri `http://localhost:8000`. El fitxer `.env` és opcional.

## Recursos

```text
assets/backgrounds/   # imatges i vídeos de fons
assets/ambience/      # pluja, foc, vent, bosc, ones...
assets/music/         # música opcional
assets/fonts/         # tipografies pròpies o compatibles
```

## Primera prova recomanada

```bash
docker compose up -d --build
docker compose exec pomodoro-studio pytest
docker compose exec pomodoro-studio ffmpeg -version
docker compose exec pomodoro-studio ffmpeg -filters
```

Comprova que FFmpeg mostra el filtre `drawtext`. Afig un fons a `assets/backgrounds/`, obri la web i crea un projecte de **2 minuts**. Comprova el compte arrere, la miniatura, la barra de progrés i els fitxers de `output/`. Després prova l'àudio i finalment una sessió llarga.

## Resultat esperat

```text
output/2026-10-28-biblioteca-medieval-001/
├── video.mp4
├── thumbnail.jpg
├── title.txt
├── description.txt
├── chapters.txt
└── metadata.json
```

## Arquitectura

`app/main.py` exposa la interfície i els endpoints. `services/timer.py` calcula la línia temporal; `services/assets.py` controla els recursos; `services/renderer.py` construïx les ordres FFmpeg; `services/jobs.py` executa la cua i interpreta el progrés; `services/metadata.py` prepara els resultats; `services/thumbnail.py` genera la miniatura.

FFmpeg s'executa sense `shell=True` i la cua limita el sistema a un vídeo simultani. El temporitzador usa `drawtext` i expressions basades en el temps; el progrés usa l'eixida estructurada de FFmpeg.

## Limitacions conegudes

- Si l'aplicació es reinicia durant un renderitzat actiu, eixe procés no es reprén automàticament; l'estat dels treballs ja finalitzats sí que queda en SQLite.
- La v0.1 usa CPU (`libx264`).
- Encara no hi ha publicació automàtica en YouTube ni altres xarxes.

## Full de ruta

- **v0.1:** flux mínim complet de projecte i renderitzat.
- **v0.2:** plantilles d'ambientació, persistència avançada de treballs i presets reutilitzables.
- **v0.3:** metadades internacionals i presets de publicació.
- **v0.4:** NVIDIA NVENC opcional.
- **v0.5:** generació assistida d'ambientacions originals amb IA.
- **v0.6:** clips promocionals 9:16.
- **v1.0:** flux estable de producció i publicació assistida.

## Drets d'autor

Pomodoro Studio està dissenyat per a contingut original o correctament llicenciat. No descarrega ni republica vídeos de tercers, música protegida o elements de franquícies sense autorització. Consulta també `docs/recursos-i-llicencies.md`.
