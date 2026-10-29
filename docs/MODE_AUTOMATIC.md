# Mode automàtic: un botó, un vídeo

La pàgina principal (`http://localhost:8000`) és ara el mode automàtic. Només cal triar:

1. **Tema**: biblioteca medieval, cabana, nau espacial…
2. **Entorn**: pluja, tempesta, llar de foc, pluja i llar de foc, nit, bosc, rierol, mar, vent o només música.
3. **Duració**: 1, 2, 3, 4 o 8 hores, amb Pomodoro 25/5 o 50/10.

I prémer **Generar i publicar**. L'estudi complet de sempre continua en **Mode avançat** (`/estudi`).

## Què fa el botó

| Pas | Què passa |
|---|---|
| Fons | Si Forge està obert, crea un fons nou i original amb el tema i l'entorn (llum, hora del dia, oratge). Si no, reutilitza un fons de `assets/backgrounds` que porte el nom del tema. |
| Ambient | Tria a l'atzar els sons de l'entorn (per exemple, una pluja i un foc) i els deixa baixets i igualats de volum. |
| Música | Per defecte **no n'hi ha**. Si marques **Afegir música**, fa una llista amb peces diferents de `assets/music`, sense repetir-les i amb fosa entre elles. |
| Avís | Si **Avís suau en acabar cada temporitzador** està marcat, sona una campaneta de dues notes: baixa en acabar la concentració i puja en acabar el descans. La genera l'aplicació, així que no té cap llicència. |
| Tipografia | Cada ambientació té la seua tipografia lliure (llibre antic, gòtica, romana, màquina d'escriure…). Vegeu `assets/fonts/README.md`. |
| Textos | Títol, descripció, capítols i etiquetes en anglés, amb els **crèdits de cada so (i de la música, si n'hi ha)** (autor, llicència i enllaç) agafats de `assets/audio-catalog.json`. |
| Vídeo | Renderitza en 1080p amb el comptador en anglés (FOCUS / BREAK / SESSION) i fa la miniatura. |
| YouTube | Puja el vídeo i la miniatura al canal amb la visibilitat triada. |

Pots tancar la pàgina mentre treballa; en tornar a obrir-la veuràs com va cada vídeo. Si demanes diversos vídeos, es fan d'un en un.

## Preparació (una sola vegada)

### 1. Sons i música

Els fitxers del catàleg (`assets/audio-catalog.json`) han d'estar en `assets/ambience/` i `assets/music/` amb el mateix nom. La pàgina mostra quants n'hi ha. Si falta el so d'un entorn, el vídeo s'atura i ho diu.

### 2. Fons

- **Amb Forge** (recomanat): obri Forge abans de prémer el botó. Cada vídeo tindrà un fons nou, que també es guarda en `assets/backgrounds/` amb la seua procedència.
- **Sense Forge**: posa imatges en `assets/backgrounds/` amb el nom del tema, per exemple `biblioteca-medieval-01.png` o `cabana-amb-pluja-02.jpg`.

Si Forge falla en escalar la imatge (per memòria de la GPU), es torna a provar sense escalar. Pots canviar-ho en `.env` amb `AUTO_HIRES_SCALE=1`.

### 3. YouTube

1. Seguix els passos de [v0.6](v0.6.md) per crear el client OAuth i guardar-lo com `data/youtube-client-secret.json`.
2. Instal·la `pip install -r requirements-youtube.txt`.
3. **Verifica el canal amb el telèfon** en <https://www.youtube.com/verify>. Sense verificar, YouTube només admet vídeos de fins a 15 minuts i elimina els més llargs després de pujar-los («s'ha suprimit perquè era massa llarg»). En <https://www.youtube.com/features> ha d'aparéixer activat «Vídeos de més de 15 minuts».
4. En la pàgina principal, prem **Connectar el canal** i tria **The Amber Window** en el navegador. Només cal fer-ho una vegada.

> **Important: auditoria de l'API de YouTube.** Google bloqueja en **privat** tots els vídeos pujats des d'un projecte de l'API que no ha passat la seua auditoria, encara que demanes «Públic». Mentre el projecte no estiga verificat, els vídeos arribaran al canal en privat i caldrà canviar-los a públic des de YouTube Studio. Per publicar-los directament en públic cal sol·licitar l'auditoria (*YouTube API Services – Audit and Quota Extension Form*) des de Google Cloud.

Si YouTube no està connectat, el vídeo es fa igualment i apareix el botó **Publicar ara** per pujar-lo més tard.

## Configuració opcional (`.env`)

```text
AUTO_DEFAULT_PRIVACY=public   # public, unlisted o private
AUTO_MUSIC_DEFAULT=false      # true perquè «Afegir música» isca marcat
AUTO_HIRES_SCALE=1.5          # 1 = sense escalar el fons de Forge
IMAGE_A1111_UPSCALER=Latent   # escalador de Forge per al fons
```

## Si alguna cosa falla

L'error apareix en vermell en la llista de vídeos, en valencià i amb la causa. Els casos més habituals:

- **No hi ha cap fons de «…»**: obri Forge o afig una imatge amb el nom del tema.
- **Falten els sons de l'entorn**: copia els àudios del catàleg en `assets/ambience/`.
- **YouTube ha fallat**: el vídeo ja està fet; revisa la connexió i prem **Publicar ara**.
- **YouTube diu que el vídeo s'ha suprimit perquè era massa llarg**: verifica el canal (pas 3 de YouTube) i prem **Tornar a pujar** en eixe vídeo.
- **Interromput per un reinici**: si tanques l'aplicació a mitjan vídeo, cal tornar-lo a demanar.
