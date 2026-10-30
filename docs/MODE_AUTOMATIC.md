# Mode automàtic: un botó, un vídeo

La pàgina principal (`http://localhost:8000`) és ara el mode automàtic. Només cal triar:

0. **Format**:
   - **Pomodoro**: comptador de concentració i descans, amb campaneta opcional.
   - **Per a dormir**: només l'ambient, sense comptador ni campaneta. La pantalla es pot enfosquir a poc a poc als 30 minuts.
   - **Per a llegir**: ambient acollidor per a llegir (amb música si vols), sense comptador ni campaneta. Va molt bé amb el tema **Racó de lectura** o qualsevol biblioteca.
   - **Partida de rol**: ambient de fons per a partides (taverna, masmorra, campament, tempesta al mar…), sense comptador.
   - **Soroll de color**: soroll marró, rosa o blanc generat per l'aplicació mateixa (sense cap so de tercers), amb pantalla enfosquida opcional.
1. **Tema**: biblioteca medieval, cabana, nau espacial, masmorra, campament d'aventurers, cova del drac…
2. **Entorn**: pluja, tempesta, llar de foc, pluja i llar de foc, nit, bosc, rierol, mar, vent, cafeteria plena, taverna plena, cafeteria i carrer, trànsit de ciutat, pluja a la ciutat, ciutat de nit, parc i plaça, carrers del Japó o només música.
   - Tria el **volum de l'ambient** (molt baix, baix o normal) i prem **🔊 Escoltar mostra** per sentir 30 segons tal com sonarà el vídeo, campaneta inclosa. El vídeo usarà exactament els sons de la mostra; **🔁 Altres sons** en tria uns altres.
3. **Duració**: 1, 2, 3, 4 o 8 hores, amb Pomodoro 25/5 o 50/10.

I prémer **Generar i publicar**. L'estudi complet de sempre continua en **Mode avançat** (`/estudi`).

## Què fa el botó

| Pas | Què passa |
|---|---|
| Fons | Usa el fons que has triat en el formulari o, amb **🎲 A l'atzar**, un dels guardats per al tema (primer els fets per al mateix format i entorn) evitant repetir els dels últims vídeos. Si el tema no en té cap, el vídeo s'atura i t'avisa. |
| Ambient | Tria a l'atzar els sons de l'entorn (per exemple, una pluja i un foc) i els deixa baixets i igualats de volum. |
| Música | Per defecte **no n'hi ha**. Si marques **Afegir música**, fa una llista amb peces diferents de l'estil triat, sense repetir-les i amb fosa entre elles. L'estil **Automàtic** tria segons el vídeo: jazz suau en cafeteries i ciutat, medieval i folk en tavernes, campaments i partides de rol, fantasia fosca en masmorres i tempestes de rol, i tranquil·la en la resta i sempre en els vídeos per a dormir. Si encara no tens música d'eixe estil, usa la tranquil·la i ho avisa. |
| Avís | Si **Avís suau en acabar cada temporitzador** està marcat, sona una campaneta de dues notes: baixa en acabar la concentració i puja en acabar el descans. La genera l'aplicació, així que no té cap llicència. |
| Moviment | Si **Moviment suau** està marcat, la càmera es desplaça molt a poc a poc sobre el fons (amplia un 6 % i va i ve en uns dos minuts), i en escenes amb foc la llum parpelleja lleugerament. El comptador no es mou. Fa el renderitzat una mica més lent. |
| Tipografia | Cada ambientació té la seua tipografia lliure (llibre antic, gòtica, romana, màquina d'escriure…). Vegeu `assets/fonts/README.md`. |
| Textos | Títol, descripció, capítols i etiquetes en anglés, amb els **crèdits de cada so (i de la música, si n'hi ha)** (autor, llicència i enllaç) agafats de `assets/audio-catalog.json`. |
| Vídeo | Renderitza en 1080p i fa la miniatura. En format Pomodoro, amb el comptador en anglés (FOCUS / BREAK / SESSION); en els altres, sense comptador i amb capítols cada hora. |
| YouTube | Puja el vídeo i la miniatura al canal amb la visibilitat triada, en la categoria del format: Educació (Pomodoro), Gent i blogs (dormir, llegir i soroll) o Videojocs (rol). |

Pots tancar la pàgina mentre treballa; en tornar a obrir-la veuràs com va cada vídeo. Si demanes diversos vídeos, es fan d'un en un.

### On es guarden els vídeos

Cada vídeo es guarda en `output/<data>-<tema>-<número>/` amb `video.mp4`, la miniatura i els textos publicats. Si la casella **Esborrar el vídeo de l'ordinador 3 dies després de publicar-lo** està marcada (ho està per defecte), passats eixos dies s'esborra `video.mp4` i es conserven la miniatura i els textos. Els 3 dies són perquè tingues temps de comprovar que YouTube l'ha acceptat; mentrestant encara el pots **Tornar a pujar**. Els dies es poden canviar en `.env` amb `KEEP_PUBLISHED_DAYS`.

### Apagar l'ordinador en acabar

Si marques **Apagar l'ordinador en acabar**, quan el vídeo s'haja publicat (o fet, si no havies demanat publicar-lo) i no quede cap altre vídeo en cua, l'aplicació espera **2 minuts** i apaga l'ordinador amb `systemctl poweroff`. Durant eixe temps la pàgina mostra un compte enrere amb el botó **Cancel·lar l'apagada**. Si el vídeo falla, o YouTube no està connectat, **no s'apaga**, perquè pugues veure què ha passat. Demanar un vídeo nou també cancel·la l'apagada pendent.

En Linux Mint funciona sense contrasenya amb la sessió oberta. Amb Docker no funciona, perquè un contenidor no pot apagar l'ordinador. L'espera i l'ordre es poden canviar en `.env` amb `SHUTDOWN_DELAY_SECONDS` i `SHUTDOWN_COMMAND`.

## Preparació (una sola vegada)

### 1. Sons i música

Els fitxers del catàleg (`assets/audio-catalog.json`) han d'estar en `assets/ambience/` i `assets/music/` amb el mateix nom. Per baixar els que falten, des de la carpeta del projecte:

```bash
python3 scripts/descarregar-sons.py
```

Només baixa els que no tens i comprova que no estiguen corromputs. La pàgina mostra quants sons hi ha. Si falta el so d'un entorn, la mostra i el vídeo ho diuen.

La música és de Kevin MacLeod ([incompetech.com](https://incompetech.com), CC BY 4.0) i està separada per estils (tranquil·la, medieval i folk, fantasia fosca, jazz de cafeteria). Si poses música teua en `assets/music/`, comença el nom per l'estil (`jazz-…`, `medieval-…`, `fosca-…`) perquè la trie en eixe estil; sense prefix compta com a tranquil·la.

Els sons de ciutat, cafeteria, restaurant, bar, Japó i parc són de [BigSoundBank](https://bigsoundbank.com) amb llicència CC0: lliures, fins i tot per a ús comercial, i sense obligació de citar-los (el vídeo els cita igualment). Les veus de fons de cafeteries i restaurants són murmuri en francés.

### 2. Fons

Els fons els poses tu. En **Biblioteca de fons** (`/fons`) pots afegir imatges (fetes amb ChatGPT o lliures de Pexels, Unsplash…), indicar opcionalment per a quin format i entorn són, i eliminar les que no vulgues. També pots copiar imatges a `assets/backgrounds/` amb un nom que comence pel tema, per exemple `biblioteca-medieval-01.png`.

En la pàgina principal, en triar el tema veus les miniatures dels seus fons: tria'n una o deixa **🎲 A l'atzar**. L'aplicació no genera imatges: no cal Forge ni cap altre programa.

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
```

## Si alguna cosa falla

L'error apareix en vermell en la llista de vídeos, en valencià i amb la causa. Els casos més habituals:

- **No hi ha cap fons de «…» en la biblioteca**: genera'n o importa'n en **Biblioteca de fons**.
- **Falten els sons de l'entorn**: copia els àudios del catàleg en `assets/ambience/`.
- **YouTube ha fallat**: el vídeo ja està fet; revisa la connexió i prem **Publicar ara**.
- **YouTube diu que el vídeo s'ha suprimit perquè era massa llarg**: verifica el canal (pas 3 de YouTube) i prem **Tornar a pujar** en eixe vídeo.
- **Interromput per un reinici**: si tanques l'aplicació a mitjan vídeo, cal tornar-lo a demanar.
