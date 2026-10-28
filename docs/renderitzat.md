# Motor de renderitzat

Pomodoro Studio utilitza FFmpeg com a motor de composició i codificació.

## Principis

- El temporitzador es calcula amb expressions de `drawtext` basades en el temps del vídeo (`t`).
- No es creen milers d'imatges intermèdies per al compte arrere.
- Les ordres FFmpeg es construïxen com una llista d'arguments i s'executaran sense `shell=True`.
- Els fons d'imatge es mantenen en bucle i els fons de vídeo utilitzen `-stream_loop -1`.
- El fons s'escala i es retalla al centre per omplir exactament la resolució de destinació.
- La duració de renderitzat prové sempre de la línia temporal calculada pel motor Pomodoro.

## Formats inicials

Fons d'imatge:

- JPG/JPEG
- PNG
- WebP

Fons de vídeo:

- MP4
- MOV
- MKV
- WebM

## Temporitzador

Cada segment de la línia temporal crea tres capes textuals:

1. `CONCENTRACIÓ` o `DESCANS`.
2. Compte arrere `MM:SS`.
3. Número de sessió.

Els filtres només s'activen dins del rang temporal corresponent a cada segment.

## Codificació inicial

La v0.1 utilitza H.264 (`libx264`), 30 FPS, CRF 20 i `yuv420p` per prioritzar compatibilitat. L'acceleració NVIDIA/NVENC serà opcional en una versió posterior i no serà un requisit del projecte.

## Següents passos

- Executor asíncron de FFmpeg.
- Lectura de progrés de renderitzat.
- Cua d'un únic treball actiu.
- Cancel·lació segura del procés.
- Mescla de sons ambientals i música.
- Generació de miniatura i fitxers de metadades.
