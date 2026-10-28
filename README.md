# Pomodoro Studio

Aplicació privada i autohosteable per a crear vídeos llargs originals de tipus **Pomodoro / Study With Me / Focus Ambience**, pensats principalment per a YouTube.

> **Estat:** v0.1 implementada. Pendent únicament de validació amb un renderitzat real en una màquina amb Docker/FFmpeg.

## Funcions de la v0.1

- Projectes Pomodoro 25/5, 50/10 o personalitzats, amb duració configurable.
- Interfície i documentació en valencià.
- Historial de projectes reobrible des de la pàgina principal.
- Fons JPG, JPEG, PNG, WebP, MP4, MOV, MKV o WebM en bucle.
- Temporitzador, fase i número de sessió sobre el vídeo.
- Sons ambientals múltiples i música opcional amb volum independent.
- Renderitzat H.264/AAC amb FFmpeg.
- Cua d'un treball, protecció contra dobles enviaments, barra de progrés, estimació i cancel·lació.
- Estat final del renderitzat sincronitzat amb SQLite.
- Miniatura 1280×720 automàtica.
- Resultats: `video.mp4`, `thumbnail.jpg`, `title.txt`, `description.txt`, `chapters.txt` i `metadata.json`.
- Noms de carpeta segurs i únics; els accents valencians es transliteren correctament.
- Validació de paràmetres, recursos restringits a `assets/` i neteja si falla la preparació.
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

Els recursos apareixen automàticament en la interfície i el backend només resol fitxers existents dins de les carpetes autoritzades.

## Primera prova recomanada

```bash
docker compose up -d --build
docker compose exec pomodoro-studio pytest
docker compose exec pomodoro-studio ffmpeg -version
```

Afig un fons a `assets/backgrounds/`, obri la web i crea un projecte de **2 minuts**. Comprova el compte arrere, la miniatura, la barra de progrés i els fitxers de `output/`. Després prova l'àudio i finalment una sessió llarga.

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

`app/main.py` exposa la interfície i els endpoints. `services/timer.py` calcula la línia temporal; `services/assets.py` controla els recursos; `services/renderer.py` construïx les ordres FFmpeg; `services/jobs.py` executa la cua i interpreta `-progress pipe:1`; `services/metadata.py` prepara els resultats; `services/thumbnail.py` genera la miniatura.

FFmpeg s'executa sense `shell=True` i la cua limita el sistema a un vídeo simultani. La implementació del progrés seguix l'eixida estructurada de FFmpeg en lloc d'analitzar els missatges humans de consola.

## Limitacions conegudes

- La cua i el percentatge de progrés viuen en memòria; si es reinicia l'aplicació, un treball actiu no es reprén automàticament.
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
