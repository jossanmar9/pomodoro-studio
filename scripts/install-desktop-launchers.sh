#!/usr/bin/env bash
set -euo pipefail

fail() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }
command -v x-terminal-emulator >/dev/null || fail 'No es troba x-terminal-emulator.'
command -v xdg-open >/dev/null || fail 'No es troba xdg-open.'
command -v curl >/dev/null || fail 'No es troba curl.'
command -v python3 >/dev/null || fail 'No es troba python3.'

printf 'Selecciona la carpeta pomodoro-studio (la que conté app, assets i README.md).\n'
if [[ -n "${1:-}" ]]; then
    project_dir="$1"
elif command -v zenity >/dev/null && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    project_dir="$(zenity --file-selection --directory --title='Selecciona la carpeta pomodoro-studio')" || exit 0
else
    read -r -p 'Ruta completa de pomodoro-studio: ' project_dir
fi
[[ -d "$project_dir" ]] || fail 'La carpeta seleccionada no existeix.'
project_dir="$(cd -- "$project_dir" && pwd -P)"
[[ -f "$project_dir/app/main.py" ]] || fail 'La carpeta seleccionada no conté app/main.py.'
[[ -x "$project_dir/.venv/bin/python" ]] || fail 'Falta .venv/bin/python en la carpeta de Pomodoro.'
forge_dir="${2:-$HOME/IA/stable-diffusion-webui-forge}"
[[ -d "$forge_dir" ]] || fail 'La carpeta de Forge no existeix.'
forge_dir="$(cd -- "$forge_dir" && pwd -P)"
[[ -f "$forge_dir/launch.py" && -x "$forge_dir/venv/bin/python" ]] || fail 'No es troba Forge en ~/IA/stable-diffusion-webui-forge.'

launcher_dir="${XDG_DATA_HOME:-$HOME/.local/share}/pomodoro-studio-launchers"
applications_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
desktop_dir="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
[[ -n "$desktop_dir" && "$desktop_dir" != "$HOME" ]] || desktop_dir="$HOME/Desktop"
mkdir -p -- "$launcher_dir" "$applications_dir" "$desktop_dir"

# These paths are shell-quoted when written; spaces and shell characters are preserved.
{
    printf '#!/usr/bin/env bash\n'
    printf 'project_dir=%q\nforge_dir=%q\n' "$project_dir" "$forge_dir"
    cat <<'RUNNER'
set -uo pipefail
case "${1:-}" in
    pomodoro)
        cd -- "$project_dir" || exit 1
        url='http://127.0.0.1:8000'
        command=("$project_dir/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000)
        health="$url/health"
        ;;
    forge)
        cd -- "$forge_dir" || exit 1
        url='http://127.0.0.1:7860'
        command=("$forge_dir/venv/bin/python" launch.py --api --port 7860)
        health="$url/sdapi/v1/options"
        ;;
    *) exit 2 ;;
esac

# Detect an already running service before attempting another GPU/server instance.
if curl -fsS --max-time 2 "$health" >/dev/null 2>&1; then
    printf 'El servei ja està obert. Obrint el navegador…\n'
    xdg-open "$url" >/dev/null 2>&1 || true
    exit 0
fi

printf 'Deixa este terminal obert mentre uses el programa.\n'
printf 'Per aturar-lo, prem Ctrl+C.\n\n'
server_pid=''
stop_server() {
    trap - INT TERM
    if [[ -n "$server_pid" ]]; then
        kill -INT "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    exit 0
}
trap stop_server INT TERM
# A background job would otherwise inherit ignored SIGINT from the shell.
# Python restores it before replacing itself with the actual server process.
python3 -c 'import os,signal,sys; signal.signal(signal.SIGINT, signal.SIG_DFL); os.execv(sys.argv[1], sys.argv[1:])' "${command[@]}" &
server_pid=$!
opened=0
for ((i=0; i<300; i++)); do
    kill -0 "$server_pid" 2>/dev/null || break
    if curl -fsS --max-time 1 "$health" >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 || true
        opened=1
        break
    fi
    sleep 2
done
if [[ "$opened" == 0 ]] && kill -0 "$server_pid" 2>/dev/null; then
    printf '\nEncara està arrancant. Quan estiga preparat, obri %s\n' "$url"
fi
wait "$server_pid"
result=$?
printf '\nEl programa ha acabat (codi %s).\n' "$result"
read -r -p 'Prem Retorn per tancar esta finestra…' _ || true
exit "$result"
RUNNER
} > "$launcher_dir/obrir.sh"
chmod u+x "$launcher_dir/obrir.sh"

desktop_quote() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//\$/\\\$}"
    value="${value//\`/\\\`}"
    value="${value//%/%%}"
    printf '"%s"' "$value"
}
create_entry() {
    local mode="$1" title="$2" icon="$3" filename="$4"
    local entry="$applications_dir/$filename"
    {
        printf '[Desktop Entry]\nVersion=1.0\nType=Application\n'
        printf 'Name=%s\nComment=Obri el servei local en un terminal\n' "$title"
        printf 'Exec=x-terminal-emulator -e bash '
        desktop_quote "$launcher_dir/obrir.sh"
        printf ' %s\nIcon=%s\nTerminal=false\nCategories=AudioVideo;\nStartupNotify=false\n' "$mode" "$icon"
    } > "$entry"
    chmod u+x "$entry"
    cp -- "$entry" "$desktop_dir/$filename"
    chmod u+x "$desktop_dir/$filename"
    if command -v gio >/dev/null; then
        gio set "$desktop_dir/$filename" metadata::trusted true 2>/dev/null || true
    fi
}
create_entry pomodoro 'Obrir Pomodoro' applications-multimedia pomodoro-studio.desktop
create_entry forge 'Obrir generador d’imatges' applications-graphics pomodoro-forge.desktop
printf '\nFet! Els dos accessos estan en: %s\n' "$desktop_dir"
printf 'També els trobaràs al menú d’aplicacions.\n'
printf 'Si Mint pregunta si confies en el llançador, tria Marcar com a fiable.\n'
printf 'Per generar imatges obri els dos; per usar fons guardats, només Pomodoro.\n'
