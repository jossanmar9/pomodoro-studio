# Vídeos i pujades programades — The Amber Window

Flux local opcional: crear projecte → guardar metadades amb crèdits → enviar a la cua de render existent → esperar el resultat → pujar en privat amb data de publicació futura. La primera prova es queda privada, sense data de publicació. El programador no genera nous fons amb IA: reutilitza els recursos seleccionats en la configuració, preferentment fons ja acceptats a la web.

La programació de partida és **dilluns, dimecres i divendres a les 18:00, Europe/Madrid**, amb vídeos de **120 minuts** i Pomodoro 25/5. Es preparen fins a 48 hores abans. Els canvis d’hora d’estiu/hivern es calculen amb `zoneinfo`; el registre usa dates UTC.

## 1. Requisits

- Instal·lació Python local, amb Pomodoro obert en `127.0.0.1:8000` i el programador executat des de la mateixa carpeta i amb el mateix `.env`/base de dades.
- Almenys un fons disponible; no cal mantindre Forge obert si ja està acceptat.
- Àudios amb procedència coneguda, FFmpeg i espai suficient per als vídeos llargs. No s’esborren automàticament vídeos acabats.
- Equip encés i sense suspensió mentre renderitza o puja; connexió durant les pujades. El timer d’usuari requerix la sessió iniciada. Una vegada acceptada la programació per YouTube, el servidor de YouTube gestiona l’hora de publicació.
- Canal habilitat per a [vídeos de més de 15 minuts](https://support.google.com/youtube/answer/71673?hl=es). El programador consulta `longUploadsStatus` abans de fer el render llarg.

Dins de la carpeta de Pomodoro:

```bash
source .venv/bin/activate
pip install -r requirements.txt -r requirements-youtube.txt
```

## 2. Connectar el canal una vegada

1. En [Google Cloud Console](https://console.cloud.google.com/), crea o selecciona un projecte i activa **YouTube Data API v3**.
2. Configura el consentiment OAuth en Google Auth Platform. Per a les proves, afegix el teu compte com a usuari de prova si l’aplicació és externa.
3. Crea un client OAuth de tipus **Desktop app** i descarrega el JSON.
4. Guarda’l localment com `data/youtube-client-secret.json`. No l’envies pel xat ni el puges a Git.
5. Crea la configuració i autoritza el compte:

```bash
python -m app.automation init
python -m app.automation authorize
```

`init` crea `data/automation.json` sense sobreescriure’l, tria fins a tres fons locals i alguns àudios disponibles i deixa `enabled=false`. Revisa sempre les escenes triades, títols i volums abans de la prova. Si preferixes partir d’un exemple, copia `docs/automation.example.json` a eixa ruta i substituïx el fons de mostra.

`authorize` obri el navegador: selecciona **The Amber Window** (també si és un canal de marca) i concedix els permisos de pujada i lectura del canal. Mostra el títol i l’ID del canal autoritzat; només si és correcte, posa eixe ID en `expected_channel_id` de `data/automation.json`. Esta ordre demana consentiment de nou quan l’executes expressament; el timer mai obri un consentiment interactiu.

El token es guarda localment en `data/youtube-token.json`, amb escriptura atòmica i permisos restringits. Si canvies de canal o revoques permisos, torna a autoritzar i comprova l’ID. El programador comprova el canal abans de preparar i pujar cada vídeo.

Google pot fer caducar en 7 dies els refresh tokens de clients OAuth externs en estat **Testing** amb estos permisos. Per a un ús continu cal revisar la configuració de producció de l’app; la comprovació OAuth i la revisió de compliment de YouTube són processos diferents. Consulta les [condicions de refresh tokens](https://developers.google.com/identity/protocols/oauth2#expiration) i el [flux d’escriptori](https://developers.google.com/identity/protocols/oauth2/native-app).

## 3. Escenes i crèdits

En `data/automation.json`, cada escena té:

- `theme`: una ambientació existent, per exemple `Cabana amb pluja` o `Bosc`.
- `title`: títol breu en anglés; el programa afig duració i Pomodoro.
- `background`, `ambience` i `music`: només noms de recursos locals, sense rutes.
- `credits`: procedència i atribucions addicionals per a recursos que no formen part del catàleg.
- `ambience_volume` i `music_volume`: entre 0 i 1.

Els àudios del catàleg versionat es verifiquen per SHA-256 i s’hi afigen autor, llicència, font i nota de bucle/volum/fades. Si un àudio no coincidix amb el catàleg, el treball es bloqueja per revisar-lo; no s’assignen crèdits a un fitxer diferent només perquè té el mateix nom. Per a altres àudios cal omplir `credits`. Els fons necessiten un JSON lateral de procedència o crèdits manuals; les notes registrades al JSON es conserven en la descripció.

La procedència registrada no és una verificació jurídica automàtica. Revisa les llicències i el text final. Si els crèdits superen el límit de descripció, es bloqueja el treball en lloc de retallar atribucions. Els fitxers seleccionats es tornen a comprovar abans de pujar, i cada treball conserva una instantània de la seua configuració.

## 4. Primera prova privada

Mantín Pomodoro obert en un altre terminal i executa:

```bash
python -m app.automation test --watch
```

Prepara un vídeo amb la duració de la configuració (120 minuts per defecte), mostra l’estat mentre avança i el puja amb `privacyStatus=private`, **sense** `publishAt`. No apareixerà públic. Per a una comprovació tècnica curta pots posar temporalment `duration_minutes=1` abans de crear la prova; després torna a 120 per al calendari.

Pots interrompre el seguiment amb Ctrl+C: això no cancel·la un render ja enviat a la web. Torna a executar la mateixa ordre per continuar consultant el registre, sense crear un altre treball.

```bash
python -m app.automation status
```

Revisa el resultat en YouTube Studio: canal correcte, imatge, so, títol, crèdits i processament correcte. `UPLOADED` significa que YouTube ha retornat un ID o s’ha recuperat el marcador local; no garantix encara processament acabat ni visibilitat pública. La fallada de miniatura es registra en els logs i no torna a pujar el vídeo.

Quan l’hages revisat, usa l’ID exacte mostrat (l’ID real té 11 caràcters):

```bash
python -m app.automation approve-test --video-id ID_DEL_VIDEO
```

L’aprovació només és vàlida per al mateix canal configurat. No modifica la privacitat de la prova.

## 5. Activar el calendari

Posa `enabled=true` en `data/automation.json`, conserva la duració de 120 minuts i executa:

```bash
bash scripts/install-automation-timer.sh
```

Instal·la `pomodoro-automation.service` i `.timer` en el systemd de l’usuari, sense `sudo`. Cada cinc minuts processa una transició durable; la prova ha d’estar aprovada. Reutilitza la cua de la web, de manera que no inicia renders en processos independents que competisquen amb els de la interfície.

Els vídeos del calendari es pugen **en privat** amb `status.publishAt` futur: YouTube els programa per al dia indicat. Segons la [referència de l’API](https://developers.google.com/youtube/v3/docs/videos), `publishAt` requerix privacitat privada i una data futura; una data passada podria publicar immediatament. Per això, si queden menys de deu minuts i no s’ha confirmat la pujada, el programador marca el treball `MISSED` i no publica tard automàticament.

Cal verificar en Studio que la programació ha sigut acceptada: la configuració del projecte API, el compte, les restriccions o el processament poden afectar la disponibilitat. La primera prova privada i els tests simulats no certifiquen per si sols una publicació pública programada real.

Les escenes roten entre les entrades configurades; el programador no crea variants visuals ni una llista musical. Modificar la configuració afecta els nous treballs, no els ja preparats. El sistema no recupera slots antics perduts mentre l’equip estava apagat.

## 6. Estat, pausa i recuperació

```bash
python -m app.automation status
systemctl --user list-timers pomodoro-automation.timer
journalctl --user -u pomodoro-automation.service
systemctl --user disable --now pomodoro-automation.timer
```

Desactivar el timer no cancel·la un render ja enviat, una pujada que s’estiga executant ni una publicació que YouTube ja tinga programada. Posa també `enabled=false` per evitar nous avanços i gestiona els treballs actius des de la web/Studio. Una pujada interrompuda queda protegida contra reintents cecs.

El registre persistent és `data/automation/runs.sqlite3`; el bloqueig de fitxer evita dos workers simultanis. No esborres el registre ni els marcadors `.youtube-video-id`, `.youtube-upload.lock` o `.youtube-upload-uncertain` per «reintentar», perquè protegixen contra duplicats. El bloqueig per carpeta també impedix pujades concurrents des de la web i el programador. Un procés mort pot deixar un bloqueig; resol primer el resultat en Studio i associa l’ID amb `resolve-upload`.

- Errors de xarxa abans d’iniciar una pujada poden reintentar-se en el següent tick. Durant la sessió resumible s’aplica el backoff existent per a errors HTTP transitoris.
- Si el procés mor durant una pujada o es perd la resposta final, queda `UNCERTAIN`. No hi ha reintent automàtic d’un nou `videos.insert`. El calendari es pausa fins a revisió.
- Si el marcador local ja té ID, un estat `UPLOADING` es pot recuperar sense repetir la pujada.
- Un render fallit requerix revisió; no es renderitza repetidament sense límit.

Després de comprovar Studio, pots associar el vídeo existent a un slot incert:

```bash
python -m app.automation resolve-upload --slot SLOT_UTC --video-id ID_REAL
```

O ometre’l explícitament, sense tornar-lo a pujar:

```bash
python -m app.automation skip --slot SLOT_UTC
```

Per reintentar només un render fallit abans d’una pujada, amb els mateixos recursos:

```bash
python -m app.automation retry-render --slot SLOT_UTC
```

`SLOT_UTC` és exactament el text de la primera columna de `status`, o `private-test` per a la prova. Un treball `MISSED` no es publica immediatament en reactivar el servei. Les recuperacions manuals deixen rastre al registre.

## Abast i verificació

No s’han creat credencials, instal·lat el timer en l’equip de l’usuari ni fet pujades reals durant el desenvolupament. Les proves d’integració exercixen els endpoints reals de projecte i publicació amb renderitzat i API YouTube simulats. La suite manté també el renderitzat curt real de FFmpeg. La connexió OAuth, la revisió privada i la confirmació de la primera programació pública són passos locals pendents.
