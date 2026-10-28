# Pomodoro Studio

Aplicació privada i autohosteable per a crear vídeos llargs originals de tipus **Pomodoro / Study With Me / Focus Ambience**, pensats principalment per a YouTube.

> **Estat:** desenvolupament inicial (v0.1).

## Objectiu

Pomodoro Studio permetrà preparar una sessió d'estudi completa a partir d'una ambientació pròpia o amb llicència compatible, configurar els intervals de concentració i descans i generar automàticament el vídeo, la miniatura i les metadades necessàries per a publicar-lo.

Exemples d'ambientacions: biblioteca medieval, biblioteca màgica, taverna medieval, castell gòtic, cabana amb pluja, observatori, bosc, vaixell pirata, Japó feudal o nau espacial.

El projecte evita deliberadament noms, personatges, música i altres elements protegits de franquícies de tercers.

## Funcions previstes

- Configuració de cicles Pomodoro 25/5, 50/10 o personalitzats.
- Duració total configurable.
- Càlcul exacte de la línia temporal i dels capítols de YouTube.
- Fons JPG, PNG o vídeo MP4 en bucle.
- Mescla de sons ambientals i música pròpia o correctament llicenciada.
- Temporitzador i indicadors de concentració/descans sobre el vídeo.
- Renderitzat amb FFmpeg.
- Generació de miniatura, títol, descripció, capítols i `metadata.json`.
- Historial local de projectes i renderitzacions.
- Cua de renderitzat amb progrés i cancel·lació.
- Execució local o mitjançant Docker.
- Arquitectura preparada per a incorporar GPU, IA i publicació a YouTube més avant.

## Tecnologia

- Python 3.12+
- FastAPI
- Jinja2
- SQLAlchemy
- SQLite
- FFmpeg
- Docker i Docker Compose

FastAPI s'utilitza per al backend i Jinja2 per a la interfície web renderitzada al servidor. La primera versió evita frameworks de frontend innecessaris per mantindre el projecte lleuger i fàcil de mantindre.

## Estructura

```text
pomodoro-studio/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   ├── services/
│   ├── templates/
│   └── static/
├── assets/
│   ├── backgrounds/
│   ├── ambience/
│   ├── music/
│   └── fonts/
├── data/
├── output/
├── logs/
├── tests/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Posada en marxa amb Docker

1. Copia `.env.example` com a `.env`.
2. Executa:

```bash
docker compose up -d --build
```

3. Obri `http://localhost:8000` al navegador.

Les carpetes `data`, `assets`, `output` i `logs` es munten com a volums perquè la informació es conserve fora del contenidor.

## Desenvolupament local

Crea un entorn virtual, instal·la les dependències de `requirements.txt` i executa l'aplicació amb Uvicorn. FFmpeg ha d'estar disponible al sistema per a les funcions de renderitzat.

## Recursos multimèdia

Els recursos es classificaran així:

- `assets/backgrounds/`: imatges i vídeos de fons.
- `assets/ambience/`: pluja, foc, vent, bosc, pàgines, ones, etc.
- `assets/music/`: música opcional.
- `assets/fonts/`: tipografies utilitzades en els vídeos i miniatures.

Només s'han d'utilitzar recursos propis, de domini públic o amb una llicència compatible amb l'ús i la monetització previstos.

## Estat de la v0.1

Ja està implementada la base de l'aplicació, la persistència amb SQLite, la creació de projectes, el motor de línies temporals Pomodoro, els capítols automàtics, la interfície web inicial, Docker i els primers tests.

El següent bloc de desenvolupament és el motor de renderitzat amb FFmpeg: fons, temporitzador, àudio, cua de treball, progrés, cancel·lació i fitxers finals.

## Full de ruta

- **v0.1:** base web, projectes, timeline i primer renderitzat.
- **v0.2:** recursos ambientals, mescla d'àudio i plantilles.
- **v0.3:** miniatures i metadades avançades.
- **v0.4:** acceleració NVIDIA/NVENC opcional.
- **v0.5:** generació assistida d'ambientacions amb IA.
- **v0.6:** clips promocionals 9:16.
- **v1.0:** flux complet estable de creació de vídeos.

## Drets d'autor

Pomodoro Studio està dissenyat per a crear contingut original i monetitzable. No està pensat per a descarregar o republicar vídeos de tercers, música protegida ni material de franquícies sense autorització.
