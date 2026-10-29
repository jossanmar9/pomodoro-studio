#!/usr/bin/env bash
set -euo pipefail
# Run from the repository, never as root. This installs a user timer, not a system daemon.
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ -x "$project_dir/.venv/bin/python" ]] || { echo 'Falta .venv/bin/python'; exit 1; }
[[ -f "$project_dir/data/automation.json" ]] || { echo 'Executa primer python -m app.automation init'; exit 1; }
[[ "$project_dir" != *$'\n'* ]] || { echo 'Ruta no admesa'; exit 1; }
# Quote absolute paths for systemd, including its own % and $ expansion.
unit_quote() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//%/%%}"
    value="${value//\$/\$\$}"
    printf '"%s"' "$value"
}
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p -- "$unit_dir"
{
    printf '[Unit]\nDescription=Pomodoro Studio automatic render and upload tick\n\n[Service]\nType=oneshot\nWorkingDirectory='
    unit_quote "$project_dir"
    printf '\nExecStart='
    unit_quote "$project_dir/.venv/bin/python"
    printf ' -m app.automation tick\nTimeoutStartSec=1h\nUMask=0077\n'
} > "$unit_dir/pomodoro-automation.service"
cat > "$unit_dir/pomodoro-automation.timer" <<'TIMER'
[Unit]
Description=Check Pomodoro scheduled videos every five minutes

[Timer]
OnBootSec=2min
OnUnitInactiveSec=5min
Unit=pomodoro-automation.service

[Install]
WantedBy=timers.target
TIMER
systemctl --user daemon-reload
systemctl --user enable --now pomodoro-automation.timer
printf 'Timer instal·lat. Requerix la sessió iniciada, Pomodoro obert i enabled=true.\n'
printf 'Logs: journalctl --user -u pomodoro-automation.service\n'
printf 'Aturar: systemctl --user disable --now pomodoro-automation.timer\n'
