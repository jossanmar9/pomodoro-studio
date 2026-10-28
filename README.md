# Pomodoro Studio

Aplicació privada i autohosteable per a crear vídeos llargs originals de tipus **Pomodoro / Study With Me / Focus Ambience**, pensats principalment per a YouTube.

> **Estat:** v0.1 funcional en fase de proves.

## Què fa

Pomodoro Studio permet crear un projecte, triar una ambientació, configurar intervals de concentració i descans, seleccionar un fons i àudios locals i generar un vídeo amb temporitzador mitjançant FFmpeg. La interfície i la documentació estan en valencià.

## Funcions de la v0.1

- Cicles Pomodoro 25/5, 50/10 o personalitzats i duració total configurable.
- Fons JPG, JPEG, PNG, WebP, MP4, MOV, MKV o WebM en bucle.
- Temporitzador, fase i número de sessió sobre el vídeo.
- Sons ambientals múltiples i música opcional amb volum independent.
- Renderitzat H.264/AAC amb FFmpeg.
- Cua d'un renderitzat concurrent, barra de progrés, estimació i cancel·lació.
- Historial de projectes en SQLite.
- Resultats sense sobreescriure: `video.mp4`, `thumbnail.jpg`, `title.txt`, `description.txt`, `chapters.txt` i `metadata.json`.
- Miniatura 1280×720 automàtica.
- Docker i Docker Compose, amb FFmpeg i DejaVu instal·lats al contenidor.
- Tests del timeline, FFmpeg i metadades.

## Tecnologia

Python 3.12+ · FastAPI · Jinja2 · SQLAlchemy · SQLite · FFmpeg · Docker

## Posada en marxa

```bash
docker compose up -d --build
```

Després obri `http://localhost:8000`. El fitxer `.env` és opcional; `.env.example` documenta els valors configurables.

## Recursos

```text
assets/backgrounds/   # imatges i vídeos de fons
assets/ambience/      # pluja, foc, vent, bosc, ones...
assets/music/         # música opcional
assets/fonts/         # tipografies pròpies o compatibles
```

Els recursos apareixen automàticament en la interfície. El backend resol únicament fitxers existents dins de les carpetes autoritzades.

## Flux de treball

1. Crea un projecte.
2. Revisa la línia temporal i els capítols.
3. Tria fons, sons ambientals i música opcional.
4. Ajusta els volums.
5. Inicia el renderitzat.
6. Seguix la barra de progrés o cancel·la el treball.
7. Troba els resultats en `output/`.

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

FFmpeg s'executa sense `shell=True`. El progrés s'obté amb `-progress pipe:1` i la interfície el consulta periòdicament. La cua executa un únic vídeo cada vegada per evitar saturar la màquina.

## Proves

```bash
pytest
```

Per a validar el renderitzat real cal tindre FFmpeg i almenys un fons dins de `assets/backgrounds/`.

## Limitacions conegudes de la v0.1

- La cua i el progrés viuen en memòria: reiniciar l'aplicació perd l'estat dels treballs actius.
- La persistència de l'estat final del renderitzat en SQLite es completarà després de les proves reals.
- La v0.1 usa CPU (`libx264`); NVENC queda reservat per a una versió posterior.
- Encara no hi ha publicació automàtica en YouTube ni altres xarxes.

## Full de ruta

- **v0.1:** flux mínim complet de projecte i renderitzat.
- **v0.2:** plantilles d'ambientació, persistència de treballs i presets reutilitzables.
- **v0.3:** metadades internacionals i presets de publicació.
- **v0.4:** NVIDIA NVENC opcional.
- **v0.5:** generació assistida d'ambientacions originals amb IA.
- **v0.6:** clips promocionals 9:16.
- **v1.0:** flux estable de producció i publicació assistida.

## Drets d'autor

Pomodoro Studio està dissenyat per a contingut original o correctament llicenciat. No descarrega ni republica vídeos de tercers, música protegida o elements de franquícies sense autorització. Consulta també `docs/recursos-i-llicencies.md`.
