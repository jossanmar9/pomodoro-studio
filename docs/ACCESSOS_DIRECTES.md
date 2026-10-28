# Accessos directes en Linux Mint

L’instal·lador crea **Obrir Pomodoro** i **Obrir generador d’imatges** en l’escriptori i en el menú d’aplicacions. Cada accés obri un terminal, arranca el servei i obri el navegador quan l’endpoint local respon.

## Instal·lació

Primer completa la [instal·lació local](INSTAL_LINUX_MINT.md). Necessites Pomodoro amb `.venv/bin/python`, Forge amb `venv/bin/python`, `curl`, `python3`, `xdg-open` i `x-terminal-emulator`. `zenity` és opcional per seleccionar la carpeta en una finestra; sense ell, el terminal et demana la ruta.

Dins de la carpeta del projecte:

```bash
bash scripts/install-desktop-launchers.sh
```

Selecciona la carpeta que conté `app/`, `assets/` i `README.md`. Per defecte, Forge es busca en `~/IA/stable-diffusion-webui-forge`. Per indicar explícitament les dues rutes:

```bash
bash scripts/install-desktop-launchers.sh \
  /ruta/a/pomodoro-studio \
  /ruta/a/stable-diffusion-webui-forge
```

Les rutes amb espais s’han de posar entre cometes. L’instal·lador valida les dues carpetes abans d’escriure els accessos. No necessita `sudo`.

## Ús

Fes doble clic en l’accés. Si Mint ho demana, selecciona **Marcar com a fiable** o **Permetre l’execució**. La marca automàtica és un intent de millor esforç: depén del gestor de fitxers. Si no veus els accessos, comprova que Cinnamon mostra els elements de l’escriptori; també els trobaràs al menú.

- Pomodoro usa <http://127.0.0.1:8000> i el seu `.venv`.
- Forge usa <http://127.0.0.1:7860> amb `--api` i el seu `venv`.
- Deixa el terminal obert mentre uses el servei. Ctrl+C l’atura.
- Si el servei ja respon en el port esperat, l’accés obri el navegador i no arranca una segona instància.
- L’obertura automàtica pot esperar fins a uns 10 minuts, més el temps de les comprovacions HTTP. Si la primera instal·lació de Forge tarda més, usa manualment l’URL quan el registre indique que està preparat.
- No són serveis del sistema ni s’executen automàticament en iniciar sessió.

## Fitxers creats

- `~/.local/share/pomodoro-studio-launchers/obrir.sh`: llançador amb les rutes seleccionades.
- `~/.local/share/applications/pomodoro-studio.desktop` i `pomodoro-forge.desktop`.
- Còpies dels `.desktop` en la carpeta d’escriptori retornada per `xdg-user-dir DESKTOP`; si no està configurada, s’usa `~/Desktop`.

Si tens `XDG_DATA_HOME` personalitzat, s’usa eixa carpeta en lloc de `~/.local/share`. Tornar a executar l’instal·lador actualitza estos mateixos llançadors. Si mous el projecte o Forge, torna a instal·lar-los amb les noves rutes.

Per retirar-los, elimina només els dos `.desktop` creats i la carpeta `pomodoro-studio-launchers`; això no elimina ni el projecte, ni els models, ni els recursos. No toca `.env` ni instal·la paquets o models.
