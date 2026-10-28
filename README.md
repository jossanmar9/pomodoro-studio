# Pomodoro Studio

Aplicació privada i autohosteable per a crear vídeos llargs originals de tipus **Pomodoro / Study With Me / Focus Ambience**, pensats principalment per a YouTube.

> **Estat:** v0.1 funcional en `develop/v0.1`, amb proves automàtiques i prova d'integració real de FFmpeg abans de fusionar a `main`.

## Què fa la v0.1

- Projectes Pomodoro 25/5, 50/10 o personalitzats, amb duració configurable.
- Interfície, README i documentació en valencià.
- Historial de projectes reobrible amb SQLite.
- Fons JPG, JPEG, PNG, WebP, MP4, MOV, MKV o WebM en bucle.
- Compte arrere MM:SS, fase i número de sessió sobre el vídeo.
- Sons ambientals múltiples i música opcional amb control de volum.
- Renderitzat H.264/AAC amb FFmpeg.
- Cua d'un treball, protecció contra dobles enviaments, barra de progrés, estimació i cancel·lació.
- Miniatura 1280×720 automàtica.
- `video.mp4`, `thumbnail.jpg`, `title.txt`, `description.txt`, `chapters.txt` i `metadata.json`.
- Metadades públiques en anglés per defecte i interfície interna en valencià.
- Noms de carpeta segurs i únics i recursos restringits a `assets/`.
- Registre de llicències dels recursos per a facilitar un ús monetitzable responsable.
- Docker i Docker Compose amb FFmpeg i DejaVu.
- GitHub Actions amb proves unitàries i un renderitzat FFmpeg curt real.

## Posada en marxa

```bash
cp .env.example .env
docker compose up -d --build
```

Obri `http://localhost:8000`.

## Recursos

```text
assets/backgrounds/   # imatges i vídeos de fons
assets/ambience/      # pluja, foc, vent, bosc, ones...
assets/music/         # música opcional
assets/fonts/         # tipografies pròpies o compatibles
```

Abans de publicar o monetitzar un vídeo, registra l'origen i la llicència de cada recurs en `assets/REGISTRE_RECURSOS.md`.

## Flux d'ús

1. Afig els recursos multimèdia a `assets/`.
2. Crea un projecte des de la web.
3. Selecciona fons, ambient i música.
4. Inicia el renderitzat.
5. Consulta el progrés o cancel·la'l si és necessari.
6. Revisa els fitxers creats en `output/`.
7. Publica manualment quan hages verificat vídeo, miniatura, metadades i llicències.

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

## Proves

```bash
docker compose exec pomodoro-studio pytest -q
```

La CI instal·la FFmpeg i DejaVu, executa les proves unitàries i genera un MP4 curt real per a detectar errors del filtre `drawtext`, del còdec o de la construcció de l'ordre.

## Documentació

- `docs/GUIA_US.md`: instal·lació i ús pas a pas.
- `docs/arquitectura.md`: components, flux i decisions tècniques.
- `docs/recursos-i-llicencies.md`: criteris de drets d'ús.
- `assets/REGISTRE_RECURSOS.md`: registre pràctic dels recursos emprats.

## Arquitectura

`app/main.py` exposa la interfície i els endpoints. `services/timer.py` calcula la línia temporal; `services/assets.py` controla els recursos; `services/renderer.py` construïx les ordres FFmpeg; `services/jobs.py` executa la cua i interpreta el progrés; `services/metadata.py` prepara els resultats; `services/thumbnail.py` genera la miniatura; `themes.py` separa els noms interns en valencià dels noms públics internacionals.

FFmpeg s'executa sense `shell=True`, amb `-nostdin`, i la cua limita el sistema a un vídeo simultani. El temporitzador usa `drawtext` i expressions temporals. El progrés es llig amb l'eixida estructurada de `-progress pipe:1`.

## Limitacions conegudes

- Si l'aplicació es reinicia durant un renderitzat actiu, el procés no es reprén automàticament.
- La v0.1 usa CPU (`libx264`). NVIDIA NVENC queda per a una versió posterior.
- La publicació a YouTube, Instagram o TikTok és manual en la v0.1.
- La generació d'imatges, vídeo o música amb IA no forma part del nucli inicial.

## Full de ruta

- **v0.1:** flux complet local de projecte, renderitzat i fitxers finals.
- **v0.2:** plantilles d'ambientació, presets reutilitzables i persistència avançada de treballs.
- **v0.3:** presets de publicació, SEO i variants de metadades.
- **v0.4:** NVIDIA NVENC opcional.
- **v0.5:** generació assistida d'ambientacions originals amb IA.
- **v0.6:** clips promocionals 9:16 per a Shorts/Reels/TikTok.
- **v1.0:** flux estable de producció i publicació assistida.

## Drets d'autor

Pomodoro Studio està dissenyat per a contingut original o correctament llicenciat. No descarrega ni republica vídeos de tercers, música protegida o elements de franquícies sense autorització. Evita usar noms o elements distintius de franquícies com a substitut d'una ambientació original.
