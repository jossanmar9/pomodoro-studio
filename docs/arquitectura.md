# Arquitectura de Pomodoro Studio

## Principis

Pomodoro Studio és una aplicació privada, local i autohosteable. La primera versió prioritza simplicitat, mantenibilitat i independència de serveis externs.

## Components

### FastAPI

Gestiona les rutes HTTP, formularis, validació i coordinació entre la interfície, la base de dades i els serveis interns.

### Jinja2

Renderitza la interfície HTML al servidor. En la fase inicial no s'utilitza cap framework JavaScript de frontend.

### SQLite i SQLAlchemy

SQLite guarda els projectes i l'estat de les renderitzacions. SQLAlchemy encapsula l'accés a les dades i permet migrar posteriorment a PostgreSQL si fora necessari.

### Motor Pomodoro

`app/services/timer.py` transforma la configuració de concentració, descans i duració total en una línia temporal exacta. Esta línia temporal és la font de veritat tant per al renderitzat com per als capítols de YouTube.

### FFmpeg

Serà el motor de producció audiovisual. S'encarregarà de:

- repetir imatges o vídeos de fons;
- dibuixar el temporitzador;
- combinar pistes ambientals;
- incorporar música opcional;
- codificar el vídeo final;
- informar del progrés del renderitzat.

## Flux previst

```text
Configuració web
      ↓
Projecte SQLite
      ↓
Timeline Pomodoro
      ↓
Cua de renderitzat
      ↓
FFmpeg
      ↓
output/<projecte>/
      ├── video.mp4
      ├── thumbnail.jpg
      ├── title.txt
      ├── description.txt
      ├── chapters.txt
      └── metadata.json
```

## Decisions de disseny

- Un únic renderitzat simultani en la primera versió.
- Sense Redis ni Celery fins que hi haja una necessitat real.
- Sense dependència obligatòria de GPU.
- Els processos FFmpeg s'executaran sense `shell=True`.
- Les rutes de fitxers es gestionaran amb `pathlib`.
- Els recursos multimèdia no es guardaran en Git.
- La publicació automàtica a YouTube queda fora de la v0.1.

## Evolució prevista

L'arquitectura haurà de permetre substituir la cua local per Redis/RQ o Celery, utilitzar NVENC, generar ambientacions amb IA i afegir serveis de publicació sense reescriure el motor Pomodoro.
