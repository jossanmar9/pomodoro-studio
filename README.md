# Pomodoro Studio

Aplicació privada i autohosteable per a crear, renderitzar i publicar vídeos llargs originals de tipus **Pomodoro / Study With Me / Focus Ambience**, pensats principalment per a YouTube.

> **Estat:** v0.9 — **mode automàtic**: tria tema, entorn i duració, prem un botó i el vídeo es genera i es publica sol. Vegeu la [guia del mode automàtic](docs/MODE_AUTOMATIC.md).

## Mode automàtic

La pàgina principal té un selector de **format** (Pomodoro, Per a dormir, Partida de rol o Soroll de color), tres preguntes i un botó:

1. **Tema** (biblioteca medieval, taverna, cabana, cafeteria a Nova York, Tòquio o París, parc a la ciutat, nau espacial…).
2. **Entorn** (pluja, tempesta, llar de foc, bosc, mar, cafeteria, taverna, trànsit, pluja a la ciutat…), amb mostra de 30 s abans de generar.
3. **Duració** (1–8 h, Pomodoro 25/5 o 50/10).

En prémer **Generar i publicar**, Pomodoro Studio crea el fons amb Forge (o reutilitza un del tema), tria els efectes de l'entorn, munta una llista musical sense repeticions amb fosa entre peces, iguala els volums, escriu títol, descripció, capítols i crèdits en anglés, renderitza el vídeo i el puja a YouTube. L'estudi complet continua en **Mode avançat** (`/estudi`).

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

- Generació opcional de fons amb A1111/Forge, previsualització i registre automàtic de procedència.

## Posada en marxa

```bash
cp -n .env.example .env
docker compose up -d --build
```

Obri `http://localhost:8000` (mode automàtic) o `http://localhost:8000/estudi` (mode avançat).

Per a una instal·lació Python local:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

En Linux Mint, consulta la [instal·lació local i Forge](docs/INSTAL_LINUX_MINT.md). Per obrir els programes amb doble clic, usa els [accessos directes](docs/ACCESSOS_DIRECTES.md).

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

En el mode avançat no es publica res automàticament. En el mode automàtic, la publicació es fa en acabar el vídeo si la casella **Publicar a YouTube** està marcada.

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

Les credencials i el token estan exclosos de Git. En el mode avançat la privacitat per defecte és **private**; en el mode automàtic es tria en la pàgina (per defecte, `AUTO_DEFAULT_PRIVACY`). El token també es pot crear amb el botó **Connectar el canal** de la pàgina principal.

> Google manté en privat els vídeos pujats des d'un projecte de l'API sense auditar. Vegeu la [guia del mode automàtic](docs/MODE_AUTOMATIC.md#3-youtube).

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
- `app/services/autopilot_plan.py`: decisions del mode automàtic (entorns, sons, llista musical, crèdits i textos).
- `app/services/autopilot.py`: procés automàtic en segon pla (fons → àudio → vídeo → YouTube).
- `app/themes.py`: noms interns i noms públics d'ambientació.

FFmpeg s'executa sense `shell=True`, amb `-nostdin`. La cua limita el sistema a un vídeo simultani i el progrés es llig des de `-progress pipe:1`.

## Documentació

- [Mode automàtic](docs/MODE_AUTOMATIC.md).
- [Guia d’ús](docs/GUIA_US.md).
- [Linux Mint, Forge i correcció d’errors](docs/INSTAL_LINUX_MINT.md).
- [Accessos directes en Linux](docs/ACCESSOS_DIRECTES.md).
- [Generació local: imatges, clips, efectes i música](docs/GENERACIO_LOCAL.md).
- [Àudios, bucles, procedència i crèdits](docs/AUDIO_I_LLICENCIES.md).
- [Catàleg de 38 efectes i 20 peces musicals](assets/audio-catalog.json).
- `docs/arquitectura.md`: components i decisions tècniques.
- `docs/recursos.md`: criteris de drets d'ús.
- `docs/v0.6.md`: configuració de YouTube.
- `assets/REGISTRE_RECURSOS.md`: registre pràctic dels recursos emprats.

## Versions

- **v0.1:** flux local complet de projecte, renderitzat i fitxers finals.
- **v0.2:** previsualització, presets, duracions ràpides i controls d'àudio.
- **v0.3:** persistència avançada, edició, duplicació, filtres i validacions.
- **v0.4:** perfils de renderitzat, NVIDIA NVENC i fallback automàtic a CPU.
- **v0.5:** metadades editables, regeneració i paquet de publicació.
- **v0.6:** publicació opcional a YouTube amb OAuth 2.0.
- **v0.7:** robustesa i comprovacions prèvies.
- **v0.8:** ambientacions originals, generació local opcional, previsualització i procedència.
- **v0.9:** mode automàtic d'un botó, llista musical amb fosa, volums normalitzats, crèdits automàtics i comptador en anglés per al canal.

## Full de ruta

- **v0.10 — Shorts:** clips verticals 9:16.
- **v1.0 — Estable:** migracions, còpies/restauració, configuració inicial guiada, seguretat i UX.

## Limitacions actuals

- Un renderitzat interromput per un reinici no es reprén des del punt on estava.
- Els clips verticals promocionals queden pendents per a v0.9.
- La IA és opcional. La generació d’imatges té connector A1111/Forge; vídeo, efectes i música generats amb IA encara s’han d’importar manualment.
- En el mode avançat es mescla una sola peça musical repetida; el mode automàtic ja fa llistes sense repeticions. Els bucles dels efectes no tenen costura garantida.
- En el mode avançat els crèdits dels àudios es copien manualment; el mode automàtic els afig sols a la descripció.
- La integració directa de publicació està centrada en YouTube.

## Drets d'autor

Pomodoro Studio està dissenyat per a contingut original o correctament llicenciat. No descarrega ni republica vídeos de tercers, música protegida o elements de franquícies sense autorització. Evita usar noms, personatges, logotips o altres elements distintius de franquícies com a substitut d'una ambientació original.


### Generació opcional d’ambientacions

La vista del projecte permet generar amb A1111/Forge, previsualitzar i acceptar explícitament un resultat com a fons amb metadades de procedència. El mode manual continua disponible sense IA. Vegeu [v0.8](docs/v0.8.md).
