# Àudios per a vídeos llargs i registre de llicències

Pomodoro Studio mescla diversos efectes ambientals simultanis i una pista musical opcional. Repetix els fitxers fins a la duració del vídeo. No cal un MP3 de tres hores per renderitzar un vídeo de tres hores, però les peces llargues reduïxen la repetició perceptible. Actualment no hi ha alternança automàtica entre diverses cançons ni bucles sense costura garantits.

## Biblioteca preparada

El [catàleg versionat](../assets/audio-catalog.json) conté 58 recursos, inclosos els del primer paquet:

| Grup | Recursos | Duració original acumulada aproximada |
|---|---:|---:|
| Efectes de natura i ambient | 38 | 2 h 02 min |
| Música de piano llarga | 5 | 2 h 55 min |
| Música ambiental i variada | 15 | 2 h 23 min |

Són unes 5,3 hores de música. Les duracions són la suma dels originals, no vídeos ja muntats. Hi ha pluja (algunes pistes amb trons), foc, boscos, rierols, cascades, mar, vent i nits rurals. La música inclou peces de diversos minuts i peces llargues com Deep Relaxation, Garden Music i Peace of Mind.

Els MP3 i els ZIP no formen part del repositori. El catàleg inclou per a cada recurs `file` (destinació local), títol, autor, `source_url`, `download_url`, llicència, duració i SHA-256. Pots descarregar-lo des de la pàgina de l’autor o l’enllaç oficial indicat i conservar el nom de destinació. No hi ha un descarregador automàtic integrat.

Els originals del paquet es van inspeccionar amb ffprobe i descodificar amb FFmpeg sense errors. La comprovació tècnica no equival a una audició completa, ni garantix unions imperceptibles. No s’han editat ni allargat; només s’han canviat els noms dels fitxers.

## Instal·lar els àudios

Descomprimix cada paquet i copia els fitxers, sense introduir un nivell addicional de carpetes:

```text
pomodoro-studio/
└── assets/
    ├── ambience/   # MP3 dels efectes
    ├── music/      # MP3 de les peces musicals
    └── llicencies/
        ├── efectes/
        ├── musica-piano/
        └── musica-variada/
```

En cada subcarpeta de `llicencies`, conserva els fitxers del paquet corresponent:

- `REGISTRE_AUDIO.md`
- `PROCEDENCIA_AUDIO.json`
- `CREDITS_PER_AL_VIDEO.txt`
- `LLEGIX-ME.txt`

Això evita sobreescriure registres amb el mateix nom. Conserva també una còpia dels comprovants fora del repositori com a còpia de seguretat. Pots afegir les entrades pertinents a [REGISTRE_RECURSOS.md](../assets/REGISTRE_RECURSOS.md). El flux manual no llig automàticament estos registres, ni copia els crèdits a la descripció. El [programador opcional](AUTOMATITZACIO_YOUTUBE.md) usa el catàleg versionat i verifica els fitxers per SHA-256 abans d’incorporar-ne els crèdits; els recursos externs necessiten notes manuals.

Recarrega la web i obri el projecte. En **Preparar vídeo**, selecciona els efectes i la música i escolta la previsualització. Comença amb efectes al 20–25% i música al 8–12%, i ajusta escoltant: els originals poden tindre nivells diferents.

## Llicències i crèdits

- **Efectes:** Joseph SARDIN / [BigSoundBank](https://bigsoundbank.com/licenses.html), CC0 1.0. Permeten ús comercial i redistribució; atribució opcional. Conserva la pàgina original i el registre.
- **Música:** Kevin MacLeod / [Incompetech](https://incompetech.com/music/royalty-free/licenses/), CC BY 4.0. Requerix atribució i indicar els canvis. Conserva la pàgina de cada pista i l’[enllaç de llicència](https://creativecommons.org/licenses/by/4.0/).

Copia només el bloc de la música utilitzada a la **Descripció** de la publicació en Pomodoro i guarda-la abans d’exportar o pujar a YouTube. Revisa que el paquet final i la descripció publicada conserven els crèdits. Si canvies de pista, actualitza’ls.

Exemple per a una peça (substituïx-lo per les dades del recurs real):

```text
Music: Garden Music — Kevin MacLeod (Incompetech).
Source: https://incompetech.com/music/royalty-free/index.html?isrc=USUAN1500081
License: Creative Commons Attribution 4.0 — https://creativecommons.org/licenses/by/4.0/
Changes: repeated to match the video duration; volume adjusted.
```

La frase de canvis ha de descriure el muntatge real. Els materials descarregats no es convertixen en propietat exclusiva teua. Llicència d’ús i elegibilitat de monetització de YouTube són qüestions diferents; no es garantix que un vídeo amb música repetida siga monetitzable.

## Altres fonts

[Freesound](https://freesound.org/help/faq/) té CC0, CC BY i CC BY-NC: comprova cada fitxa; no tries BY-NC per a vídeos comercials sense permís addicional. La [Biblioteca d’àudio de YouTube](https://support.google.com/youtube/answer/3376882?hl=es) també és una opció, amb requisits d’atribució segons la pista.

## Generació local futura

La v0.8 no genera música ni efectes. Pots generar-los externament i importar el resultat en els mateixos formats. En eixe cas registra model, versió, prompt, data, condicions aplicables i qualsevol material de referència utilitzat. La integració actual d’IA en la web és per a imatges amb A1111/Forge.
