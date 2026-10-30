# Accessos directes en Linux Mint

L’instal·lador crea **Obrir Pomodoro** en l’escriptori i en el menú d’aplicacions. Obri un terminal, arranca el servei i obri el navegador quan està preparat. Si tenies l’antic accés **Obrir generador d’imatges** (Forge), l’instal·lador l’esborra.

## Instal·lació

Primer completa la [instal·lació local](INSTAL_LINUX_MINT.md). Necessites Pomodoro amb `.venv/bin/python`, `curl`, `python3`, `xdg-open` i `x-terminal-emulator`. `zenity` és opcional per seleccionar la carpeta en una finestra; sense ell, el terminal et demana la ruta.

Dins de la carpeta del projecte:

```bash
bash scripts/install-desktop-launchers.sh
```

Selecciona la carpeta que conté `app/`, `assets/` i `README.md`. També la pots indicar directament:

```bash
bash scripts/install-desktop-launchers.sh /ruta/a/pomodoro-studio
```

Les rutes amb espais s’han de posar entre cometes. L’instal·lador valida la carpeta abans d’escriure l’accés. No necessita `sudo`.

## Ús

Fes doble clic en l’accés. Si Mint ho demana, selecciona **Marcar com a fiable** o **Permetre l’execució**. La marca automàtica és un intent de millor esforç: depén del gestor de fitxers. Si no veus els accessos, comprova que Cinnamon mostra els elements de l’escriptori; també els trobaràs al menú.

- Pomodoro usa <http://127.0.0.1:8000> i el seu `.venv`.
- Deixa el terminal obert mentre uses el servei. Ctrl+C l’atura.
- Si el servei ja respon en el port esperat, l’accés obri el navegador i no arranca una segona instància.
- No són serveis del sistema ni s’executen automàticament en iniciar sessió.

## Fitxers creats

- `~/.local/share/pomodoro-studio-launchers/obrir.sh`: llançador amb les rutes seleccionades.
- `~/.local/share/applications/pomodoro-studio.desktop`.
- Còpies dels `.desktop` en la carpeta d’escriptori retornada per `xdg-user-dir DESKTOP`; si no està configurada, s’usa `~/Desktop`.

Si tens `XDG_DATA_HOME` personalitzat, s’usa eixa carpeta en lloc de `~/.local/share`. Tornar a executar l’instal·lador actualitza estos mateixos llançadors. Si mous el projecte, torna a instal·lar-lo amb la nova ruta.

Per retirar-los, elimina només el `.desktop` creat i la carpeta `pomodoro-studio-launchers`; això no elimina ni el projecte, ni els models, ni els recursos. No toca `.env` ni instal·la paquets o models.
