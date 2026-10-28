# Guia d'ús

## 1. Preparar l'aplicació

Copia `.env.example` a `.env` i inicia el servei amb:

```bash
docker compose up -d --build
```

Obri `http://localhost:8000`.

## 2. Afegir recursos

Copia els recursos a:

- `assets/backgrounds/`: JPG, JPEG, PNG, WebP, MP4, MOV, MKV o WebM.
- `assets/ambience/`: MP3, WAV, OGG, M4A, FLAC o AAC.
- `assets/music/`: música opcional en els mateixos formats d'àudio.

Registra l'origen i la llicència en `assets/REGISTRE_RECURSOS.md`.

## 3. Crear un projecte

Des del panell principal selecciona l'ambientació, minuts de concentració, descans, duració total i resolució. La duració final és exacta; l'última sessió pot ser més curta si és necessari.

## 4. Generar el vídeo

En la fitxa del projecte selecciona un fons, els sons ambientals i, opcionalment, música. Ajusta els volums i prem **Generar vídeo**.

Només s'executa un renderitzat alhora. La pantalla mostra el percentatge i una estimació del temps restant. Es pot cancel·lar el procés.

FFmpeg s'executa sense shell i en segon pla amb `-nostdin`; el progrés es llig des de la seua eixida estructurada.

## 5. Resultat

Cada renderitzat crea una carpeta única dins d'`output/` amb:

- `video.mp4`
- `thumbnail.jpg`
- `title.txt`
- `description.txt`
- `chapters.txt`
- `metadata.json`

La interfície i la documentació són en valencià. Les metadades públiques es generen en anglés per defecte per a facilitar un canal internacional.

## 6. Còpies de seguretat

Conserva almenys `data/`, `assets/` i els resultats d'`output/` que vulgues preservar. El contenidor es pot reconstruir; estes dades no.

## 7. Actualització

Quan hi haja una versió nova:

```bash
git pull
docker compose up -d --build
```

Abans d'actualitzar una instal·lació amb contingut important, fes còpia de `data/`.
