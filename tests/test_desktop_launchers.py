"""Exercise the installer without a desktop, GPU, or writes to user directories."""
import os
from pathlib import Path
import shlex
import subprocess

import pytest

INSTALLER = Path(__file__).resolve().parents[1] / 'scripts/install-desktop-launchers.sh'


def executable(path, content='#!/usr/bin/env bash\nexit 0\n'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o700)


@pytest.fixture
def installation(tmp_path):
    project = tmp_path / 'project with spaces $(touch INJECTED)'
    (project / 'app').mkdir(parents=True)
    (project / 'app/main.py').touch()
    executable(project / '.venv/bin/python')
    mock_bin = tmp_path / 'bin'; mock_bin.mkdir()
    desktop = tmp_path / 'Desktop with spaces'
    executable(mock_bin / 'xdg-user-dir', '#!/usr/bin/env bash\nprintf "%s\\n" "$TEST_DESKTOP"\n')
    executable(mock_bin / 'gio')
    executable(mock_bin / 'curl')
    executable(mock_bin / 'xdg-open', '#!/usr/bin/env bash\nprintf "%s\\n" "$1" >> "$TEST_OPEN_LOG"\n')
    executable(mock_bin / 'x-terminal-emulator', '#!/usr/bin/env bash\n[[ "$1" == "-e" ]] || exit 3\nshift\nexec "$@"\n')
    env = dict(os.environ, PATH=str(mock_bin) + os.pathsep + os.environ['PATH'],
               XDG_DATA_HOME=str(tmp_path / 'data with spaces'),
               TEST_DESKTOP=str(desktop), TEST_OPEN_LOG=str(tmp_path / 'opened.log'))
    return project, desktop, env


def install(installation):
    project, _, env = installation
    return subprocess.run(['bash', str(INSTALLER), str(project)],
                          env=env, capture_output=True, text=True, timeout=10)


def test_install_handles_spaces_and_opens_existing_services(installation):
    project, desktop, env = installation
    old = desktop / 'pomodoro-forge.desktop'
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text('[Desktop Entry]\n')
    result = install(installation)
    assert result.returncode == 0, result.stderr
    runner = Path(env['XDG_DATA_HOME']) / 'pomodoro-studio-launchers/obrir.sh'
    subprocess.run(['bash', '-n', str(runner)], check=True)
    for filename in ('pomodoro-studio.desktop',):
        entry = desktop / filename
        assert entry.is_file() and os.access(entry, os.X_OK)
        command = next(line[5:] for line in entry.read_text().splitlines() if line.startswith('Exec='))
        launch = subprocess.run(shlex.split(command), env=env, capture_output=True, text=True, timeout=10)
        assert launch.returncode == 0, launch.stderr
    assert Path(env['TEST_OPEN_LOG']).read_text().splitlines() == ['http://127.0.0.1:8000']
    assert not old.exists()
    assert not (project / 'INJECTED').exists()
    assert not (project.parent / 'INJECTED').exists()


def test_invalid_project_does_not_create_launchers(installation):
    project, desktop, env = installation
    (project / 'app/main.py').unlink()
    result = install(installation)
    assert result.returncode != 0
    assert 'app/main.py' in result.stderr
    assert not desktop.exists()
    assert not Path(env['XDG_DATA_HOME']).exists()


def test_installer_can_be_run_again(installation):
    assert install(installation).returncode == 0
    assert install(installation).returncode == 0
    assert len(list(installation[2].glob('*.desktop'))) == 1
