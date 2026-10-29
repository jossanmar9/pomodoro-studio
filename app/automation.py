"""Opt-in local scheduler. One durable transition per tick; private trial first."""
import argparse
from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from time import sleep
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.database import SessionLocal
from app.models import Project
from app.services.assets import catalog, resolve_asset
from app.services.metadata import PublicationDraft, default_publication, validate_publication
from app.services.timer import build_timeline
from app.services.youtube import (UPLOAD_MARKER, YOUTUBE_UPLOAD_SCOPE, YouTubeUploadSpec,
                                  credentials, google_libraries, upload_video)
from app.themes import THEMES

UTC = timezone.utc
SCOPES = [YOUTUBE_UPLOAD_SCOPE, 'https://www.googleapis.com/auth/youtube.readonly']
TERMINAL = {'UPLOADED', 'ERROR', 'UNCERTAIN', 'MISSED'}


class Scene(BaseModel):
    model_config = ConfigDict(extra='forbid')
    theme: str
    title: str = Field(min_length=1, max_length=55)
    background: str
    ambience: list[str] = Field(default_factory=list, max_length=8)
    music: str = ''
    credits: str = Field(default='', max_length=2000)
    ambience_volume: float = Field(default=.22, ge=0, le=1)
    music_volume: float = Field(default=.10, ge=0, le=1)


class Config(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = False
    timezone: str = 'Europe/Madrid'
    weekdays: list[int] = Field(default_factory=lambda: [0, 2, 4], min_length=1, max_length=7)
    hour: int = Field(default=18, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    lead_hours: int = Field(default=48, ge=1, le=168)
    duration_minutes: int = Field(default=120, ge=1, le=720)
    focus_minutes: int = Field(default=25, ge=1, le=180)
    break_minutes: int = Field(default=5, ge=0, le=60)
    resolution: str = '1920x1080'
    engine: str = 'auto'
    quality: str = 'balanced'
    expected_channel_id: str = ''
    scenes: list[Scene] = Field(min_length=1, max_length=30)

    def checked(self):
        ZoneInfo(self.timezone)
        if any(d not in range(7) for d in self.weekdays) or len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError('Els dies han de ser únics, de 0 (dilluns) a 6 (diumenge)')
        if self.resolution not in {'1920x1080', '2560x1440'}:
            raise ValueError('Resolució no admesa')
        if self.engine not in {'auto', 'cpu', 'nvenc'} or self.quality not in {'fast', 'balanced', 'quality'}:
            raise ValueError('Motor o qualitat no vàlids')
        if any(s.theme not in THEMES for s in self.scenes):
            raise ValueError('Ambientació no vàlida')
        return self


def slots(config, now):
    """UTC keys survive restarts and DST; only a short future window is prepared."""
    zone = ZoneInfo(config.timezone)
    start = now.astimezone(zone).date()
    result = []
    for offset in range(9):
        day = start + timedelta(days=offset)
        if day.weekday() not in config.weekdays:
            continue
        local = datetime.combine(day, time(config.hour, config.minute), zone)
        stamp = local.astimezone(UTC)
        if stamp.astimezone(zone).replace(tzinfo=None) != local.replace(tzinfo=None):
            continue  # Nonexistent local time at a DST jump.
        if now < stamp <= now + timedelta(hours=config.lead_hours):
            result.append(stamp)
    return result


@contextmanager
def locked_state(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Ja hi ha un programador en execució') from None
        with sqlite3.connect(root / 'runs.sqlite3') as db:
            db.row_factory = sqlite3.Row
            db.execute('CREATE TABLE IF NOT EXISTS runs (slot TEXT PRIMARY KEY, status TEXT NOT NULL, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS approvals (video_id TEXT PRIMARY KEY)')
            db.commit()
            yield db


def save(db, key, status, data):
    db.execute('INSERT INTO runs VALUES (?, ?, ?) ON CONFLICT(slot) DO UPDATE SET status=excluded.status,payload=excluded.payload',
               (key, status, json.dumps(data, ensure_ascii=False)))
    db.commit()  # Persist intent before a side effect.


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def publication(config, scene):
    names = [('backgrounds', scene.background)] + [('ambience', x) for x in scene.ambience]
    if scene.music:
        names.append(('music', scene.music))
    rows = json.loads((Path(__file__).resolve().parents[1] / 'assets/audio-catalog.json').read_text())
    known = {r['file']: r for r in rows}
    credits = [scene.credits.strip()] if scene.credits.strip() else []
    hashes = {}
    for kind, name in names:
        path = resolve_asset(kind, name)
        key = f'assets/{kind}/{name}'
        digest = fingerprint(path)
        hashes[key] = digest
        if kind == 'backgrounds':
            metadata = path.with_suffix(path.suffix + '.json')
            if not metadata.is_file() and not scene.credits.strip():
                raise ValueError('Cal procedència del fons: JSON lateral o credits en la configuració')
            if metadata.is_file():
                if metadata.is_symlink():
                    raise ValueError('Metadades de fons no vàlides')
                record = json.loads(metadata.read_text())
                if not isinstance(record, dict):
                    raise ValueError('Metadades de fons no vàlides')
                visual = 'Visual provenance: ' + str(record.get('provider', 'manual'))
                if record.get('model'):
                    visual += '; model: ' + str(record['model'])
                if record.get('license'):
                    visual += '\nLicense notes: ' + str(record['license'])
                if record.get('source_notes'):
                    visual += '\n' + str(record['source_notes'])
                credits.append(visual)
        elif key in known:
            row = known[key]
            if digest != row['sha256']:
                raise ValueError(f'El fitxer {name} no coincidix amb el catàleg; revisa la procedència')
            note = f"{row['title']} — {row['author']}. {row['license']}.\n{row['source_url']}\n{row['license_url']}"
            if row['license'].startswith('CC BY'):
                note += '\nChanges: looped to match the video duration; volume adjusted and fades applied.'
            credits.append(note)
        elif not scene.credits.strip():
            raise ValueError(f'Falten crèdits/procedència per a {name}')
    timeline = build_timeline(config.focus_minutes, config.break_minutes, config.duration_minutes)
    base = default_publication(theme=scene.theme, focus=config.focus_minutes, pause=config.break_minutes,
                               duration=config.duration_minutes, timeline=timeline)
    title = f'{config.duration_minutes / 60:g}H {scene.title} | {config.focus_minutes}/{config.break_minutes} Pomodoro'
    description = ('Welcome to The Amber Window — a little light to come home to.\n\n'
                   + base.description + '\nCredits & provenance:\n' + '\n\n'.join(dict.fromkeys(credits)))
    draft = PublicationDraft(title, description, base.chapters, base.tags, 'en')
    errors = validate_publication(draft)
    if errors or len(description.encode('utf-8')) > 5000:
        raise ValueError('; '.join(errors) or 'Descripció massa llarga en UTF-8')
    return draft, hashes


def channel(interactive=False, require_long_uploads=False):
    creds = credentials(interactive=interactive, scopes=SCOPES, force_login=interactive)
    _, _, _, build, _ = google_libraries()
    service = build('youtube', 'v3', credentials=creds, cache_discovery=False)
    items = service.channels().list(part='id,snippet,status', mine=True).execute().get('items', [])
    if len(items) != 1:
        raise ValueError('No s’ha pogut identificar un únic canal; revisa l’autorització')
    if require_long_uploads and items[0].get('status', {}).get('longUploadsStatus') != 'allowed':
        raise ValueError('Activa les pujades de més de 15 minuts en youtube.com/verify abans de renderitzar')
    return items[0]['id'], items[0]['snippet']['title']


def check_channel(config):
    if not config.expected_channel_id:
        raise ValueError('Falta expected_channel_id; executa authorize i confirma el canal')
    actual, _ = channel(require_long_uploads=config.duration_minutes > 15)
    if actual != config.expected_channel_id:
        raise ValueError('El canal autoritzat no coincidix amb expected_channel_id')


def tick(config, db, client, *, test=False, now=None):
    now = now or datetime.now(UTC)
    rows = db.execute('SELECT * FROM runs ORDER BY slot').fetchall()
    if not test:
        if not config.enabled:
            return 'Desactivat: només es permet la prova privada explícita'
        approved = db.execute("SELECT r.payload FROM runs r JOIN approvals a ON json_extract(r.payload, '$.video_id')=a.video_id WHERE r.slot='private-test' AND r.status='UPLOADED'").fetchone()
        if not approved or json.loads(approved[0])['config']['expected_channel_id'] != config.expected_channel_id:
            raise ValueError('Primer puja, revisa i aprova la prova privada per al canal configurat')
        if any(r['status'] == 'UNCERTAIN' for r in rows):
            raise ValueError('Hi ha una pujada incerta: revisa Studio i usa resolve-upload o skip abans de continuar')
    # Preserve all in-flight work regardless of schedule edits; a disabled worker pauses it.
    active = next((r for r in rows if r['status'] not in TERMINAL and (r['slot'] == 'private-test') == test), None)
    if active is None:
        if test:
            if any(r['slot'] == 'private-test' for r in rows):
                return 'La prova ja té registre; consulta status abans de repetir-la'
            key = 'private-test'
        else:
            existing = {r['slot'] for r in rows}
            upcoming = next((s for s in slots(config, now) if s.isoformat() not in existing), None)
            if upcoming is None:
                return 'No hi ha cap vídeo nou pendent en la finestra de preparació'
            key = upcoming.isoformat()
        check_channel(config)  # No interactive login from the timer, and no renders before auth.
        client.get('/health').raise_for_status()
        index = len([r for r in rows if r['slot'] != 'private-test']) % len(config.scenes)
        scene = config.scenes[index]
        draft, hashes = publication(config, scene)
        data = {'scene': scene.model_dump(), 'config': config.model_dump(), 'hashes': hashes,
                'publication': draft.__dict__}
        save(db, key, 'PLANNED', data)
        active = db.execute('SELECT * FROM runs WHERE slot=?', (key,)).fetchone()
    key = active['slot']; state = active['status']; data = json.loads(active['payload'])
    if not test and state != 'UPLOADING' and datetime.fromisoformat(key) <= now + timedelta(minutes=10):
        save(db, key, 'MISSED', data | {'error': 'No hi ha marge per publicar; no es publica tard automàticament'})
        return 'MISSED'
    if state == 'PLANNED':
        scene = Scene(**data['scene']); cfg = Config(**data['config'])
        response = client.post('/projects', data={'theme': scene.theme, 'focus_minutes': cfg.focus_minutes,
            'break_minutes': cfg.break_minutes, 'duration_minutes': cfg.duration_minutes, 'resolution': cfg.resolution})
        if response.status_code != 303:
            response.raise_for_status(); raise RuntimeError('No s’ha creat el projecte')
        match = re.fullmatch(r'/projects/(\d+)', response.headers.get('location', ''))
        if not match:
            raise RuntimeError('Resposta de projecte no vàlida')
        data['project_id'] = int(match[1])
        save(db, key, 'PREPARED', data)
        return 'PREPARED'
    if state == 'PREPARED':
        cfg = Config(**data['config']); scene = Scene(**data['scene']); pid = data['project_id']
        response = client.post(f'/projects/{pid}/publication', data=data['publication'])
        if response.status_code != 303:
            response.raise_for_status(); raise RuntimeError('No s’han guardat les metadades')
        save(db, key, 'RENDERING', data)
        try:
            response = client.post(f'/projects/{pid}/render', data={'background': scene.background,
                'ambience': scene.ambience, 'music': scene.music, 'ambience_volume': scene.ambience_volume,
                'music_volume': scene.music_volume, 'engine': cfg.engine, 'quality': cfg.quality})
            if response.status_code != 303:
                response.raise_for_status(); raise RuntimeError('No s’ha iniciat el renderitzat')
        except Exception:
            save(db, key, 'ERROR', data | {'error': 'Revisa el projecte: no s’ha confirmat l’inici del renderitzat'})
            raise
        return 'RENDERING'
    if state == 'RENDERING':
        with SessionLocal() as projects:
            project = projects.get(Project, data['project_id'])
            status = project.status if project else 'FAILED'
            folder = project.output_path if project else None
        if status in {'FAILED', 'CANCELLED', 'DRAFT'}:
            save(db, key, 'ERROR', data | {'error': 'Renderitzat interromput, cancel·lat o fallit'})
            return 'ERROR'
        if status != 'COMPLETED':
            return 'RENDERING'
        if not folder or not (Path(folder) / 'video.mp4').is_file():
            raise ValueError('Falta el vídeo final')
        data['output'] = folder
        save(db, key, 'RENDERED', data)
        return 'RENDERED'
    if state == 'RENDERED':
        check_channel(Config(**data['config']))
        for key_path, expected in data['hashes'].items():
            _, kind, name = key_path.split('/', 2)
            if fingerprint(resolve_asset(kind, name)) != expected:
                save(db, key, 'ERROR', data | {'error': 'Els recursos han canviat després de preparar el vídeo'})
                return 'ERROR'
        folder = Path(data['output']); draft = data['publication']
        spec = YouTubeUploadSpec(folder / 'video.mp4', draft['title'], draft['description'],
            [s.strip() for s in draft['tags'].split(',') if s.strip()], privacy='private',
            thumbnail=(folder / 'thumbnail.jpg') if (folder / 'thumbnail.jpg').is_file() else None,
            publish_at=None if test else datetime.fromisoformat(key), interactive_auth=False)
        save(db, key, 'UPLOADING', data)
        try:
            video_id = upload_video(spec)
        except Exception:
            # A server may have accepted the video even when the response was lost.
            # NEVER blindly retry an insert, including after process death.
            save(db, key, 'UNCERTAIN', data | {'error': 'Pujada no confirmada; revisa YouTube Studio abans de reintentar'})
            raise
        save(db, key, 'UPLOADED', data | {'video_id': video_id})
        return 'UPLOADED: ' + video_id
    if state == 'UPLOADING':
        marker = Path(data['output']) / UPLOAD_MARKER
        if marker.is_file() and marker.read_text().strip():
            save(db, key, 'UPLOADED', data | {'video_id': marker.read_text().strip()})
            return 'UPLOADED (recuperat del marcador)'
        save(db, key, 'UNCERTAIN', data | {'error': 'Procés interromput durant la pujada; revisa YouTube Studio'})
        return 'UNCERTAIN'
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'authorize', 'test', 'tick', 'status', 'approve-test', 'resolve-upload', 'skip', 'retry-render'])
    parser.add_argument('--config', type=Path, default=Path('data/automation.json'))
    parser.add_argument('--state-dir', type=Path, default=Path('data/automation'))
    parser.add_argument('--video-id', default='')
    parser.add_argument('--slot', default='')
    parser.add_argument('--watch', action='store_true', help='Seguix la prova privada fins que acabe')
    args = parser.parse_args(argv)
    if args.watch and args.command != 'test':
        parser.error('--watch només és per a la prova privada')
    if args.command == 'init':
        assets = catalog()
        if not assets.backgrounds:
            parser.error('Accepta primer almenys un fons des de la web')
        scenes = [Scene(theme='Cabana amb pluja', title=f'Warm Retreat {i+1}', background=name,
                        ambience=assets.ambience[:1], music=assets.music[0] if assets.music else '')
                  for i, name in enumerate(assets.backgrounds[:3])]
        config = Config(scenes=scenes)
        args.config.parent.mkdir(parents=True, exist_ok=True)
        with args.config.open('x') as target:
            target.write(config.model_dump_json(indent=2) + '\n')
        print('Configuració creada i desactivada. Revisa escenes i crèdits abans de la prova.')
        return
    config = Config.model_validate_json(args.config.read_text()).checked()
    if args.command == 'authorize':
        identity, title = channel(interactive=True)
        print(f'Canal autoritzat: {title} ({identity}). Posa este ID en expected_channel_id si és el canal correcte.')
        return
    with locked_state(args.state_dir) as db:
        if args.command == 'status':
            for row in db.execute('SELECT * FROM runs ORDER BY slot'):
                data = json.loads(row['payload'])
                print(row['slot'], row['status'], data.get('project_id', ''), data.get('video_id', ''), data.get('error', ''))
            return
        if args.command in {'resolve-upload', 'skip', 'retry-render'}:
            row = db.execute('SELECT * FROM runs WHERE slot=?', (args.slot,)).fetchone()
            if not row:
                parser.error('Indica un --slot existent de status')
            data = json.loads(row['payload'])
            if args.command == 'resolve-upload':
                if row['status'] != 'UNCERTAIN' or not re.fullmatch(r'[A-Za-z0-9_-]{11}', args.video_id):
                    parser.error('Cal una pujada UNCERTAIN i l’ID de 11 caràcters comprovat en Studio')
                if data.get('output'):
                    (Path(data['output']) / UPLOAD_MARKER).write_text(args.video_id + '\n')
                save(db, args.slot, 'UPLOADED', data | {'video_id': args.video_id, 'resolved_manually': True})
            elif args.command == 'skip':
                if row['status'] not in {'UNCERTAIN', 'ERROR', 'MISSED'}:
                    parser.error('Només es poden ometre registres incerts, fallits o fora de termini')
                save(db, args.slot, 'ERROR', data | {'error': 'Omés manualment; no reintentar la pujada'})
            else:
                if row['status'] != 'ERROR' or data.get('output') or 'project_id' not in data:
                    parser.error('Només es pot reintentar un render fallit abans d’una pujada')
                with SessionLocal() as projects:
                    project = projects.get(Project, data['project_id'])
                    if not project or project.status in {'QUEUED', 'GENERATING', 'COMPLETED'}:
                        parser.error('El projecte no permet reintentar el render')
                _, hashes = publication(Config(**data['config']), Scene(**data['scene']))
                if hashes != data['hashes']:
                    parser.error('Els recursos han canviat; revisa el projecte manualment')
                save(db, args.slot, 'PREPARED', data)
            print('Estat actualitzat. No s’ha fet cap pujada en esta ordre.')
            return
        if args.command == 'approve-test':
            row = db.execute("SELECT payload FROM runs WHERE slot='private-test' AND status='UPLOADED'").fetchone()
            if not row or not args.video_id or json.loads(row[0]).get('video_id') != args.video_id:
                parser.error('L’ID ha de coincidir amb la prova privada pujada i revisada')
            db.execute('INSERT OR IGNORE INTO approvals VALUES (?)', (args.video_id,)); db.commit()
            print('Prova aprovada. Per activar el calendari, posa enabled=true i instal·la el timer.')
            return
        with httpx.Client(base_url='http://127.0.0.1:8000', timeout=30, follow_redirects=False) as client:
            while True:
                print(tick(config, db, client, test=args.command == 'test'), flush=True)
                if not args.watch:
                    break
                row = db.execute("SELECT status FROM runs WHERE slot='private-test'").fetchone()
                if row and row[0] in TERMINAL:
                    break
                sleep(10)


if __name__ == '__main__':
    main()
