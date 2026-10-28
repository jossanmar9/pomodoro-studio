import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base
from app.models import Project
from app.services import ambience_web as web
from app.services.image_providers import GeneratedImage


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    with session() as db:
        db.add_all([Project(id=1, theme='Bosc'), Project(id=2, theme='Bosc')]); db.commit()
    monkeypatch.setattr(web, 'SessionLocal', session)
    monkeypatch.setattr(web.settings, 'image_generation_dir', tmp_path / 'staging')
    monkeypatch.setattr(web.settings, 'assets_dir', tmp_path / 'assets')
    def generate(*args, **kwargs):
        root = web.settings.image_generation_dir
        root.mkdir(exist_ok=True)
        path = root / 'generated.png'
        Image.new('RGB', (16, 16)).save(path)
        return GeneratedImage(path, 'fake', 'checkpoint', 'seed: 42')
    monkeypatch.setattr(web, 'generate_image', generate)
    with TestClient(app) as client:
        yield client
    engine.dispose()


def generate(client):
    response = client.post('/api/projects/1/ambience/generate', json={'provider':'fake', 'spec':{'subject':'quiet library'}})
    assert response.status_code == 201, response.text
    return response.json()


def test_generate_preview_accept_provenance(client):
    result = generate(client)
    assert not web.settings.assets_dir.exists()
    assert client.get(result['preview_url']).headers['content-type'] == 'image/png'
    endpoint = f"/api/projects/1/ambience/{result['id']}/accept"
    response = client.post(endpoint, json={'name':'My library','license':'own','source_notes':'reviewed'})
    assert response.status_code == 201
    root = web.settings.assets_dir / 'backgrounds'
    assert (root / 'my-library.png').is_file()
    data = json.loads((root / 'my-library.png.json').read_text())
    assert data['provider'] == 'fake' and data['model'] == 'checkpoint'
    assert 'quiet library' in data['prompt'] and data['negative_prompt']
    assert data['license'] == 'own' and 'seed: 42' in data['source_notes']
    assert data['generation']['width'] == 1344 and data['imported_at']
    assert client.post(endpoint, json={'name':'again'}).status_code == 404
    assert client.get(result['preview_url']).status_code == 404


def test_project_scope_and_paths(client):
    result = generate(client)
    assert client.get(result['preview_url'].replace('/1/', '/2/')).status_code == 404
    assert client.post(f"/api/projects/2/ambience/{result['id']}/accept",json={'name':'x'}).status_code == 404
    assert client.get('/api/projects/1/ambience/not-a-token/preview').status_code == 404
    assert client.post('/api/projects/999/ambience/generate',json={'provider':'x','spec':{'subject':'x'}}).status_code == 404
    assert client.post('/api/projects/1/ambience/generate',json={'provider':'x','spec':{'subject':'Hogwarts'}}).status_code == 400
    assert client.post('/api/projects/1/ambience/generate',json={'provider':'x','spec':{'subject':'x'},'width':99999}).status_code == 422


def test_conflict_keeps_preview(client):
    result = generate(client)
    root = web.settings.assets_dir / 'backgrounds'; root.mkdir(parents=True)
    (root / 'same.png').write_bytes(b'existing')
    response = client.post(f"/api/projects/1/ambience/{result['id']}/accept",json={'name':'same'})
    assert response.status_code == 409
    assert (root / 'same.png').read_bytes() == b'existing'
    assert client.get(result['preview_url']).status_code == 200
    assert not (root / 'same.png.json').exists()


def test_provider_failure_is_sanitized(client, monkeypatch):
    def fail(*args, **kwargs): raise RuntimeError('secret /private/path')
    monkeypatch.setattr(web, 'generate_image', fail)
    response = client.post('/api/projects/1/ambience/generate',json={'provider':'x','spec':{'subject':'x'}})
    assert response.status_code == 502
    assert 'secret' not in response.text and 'manual' in response.text
    assert not web.settings.assets_dir.exists()


def test_cross_origin_rejected(client):
    assert client.post('/api/projects/1/ambience/generate',headers={'Origin':'https://evil.example'},json={'provider':'x','spec':{'subject':'x'}}).status_code == 403


def test_symlink_preview_rejected(client, tmp_path):
    result = generate(client)
    image = web.settings.image_generation_dir / 'generated.png'
    outside = tmp_path / 'outside.png'; image.rename(outside); image.symlink_to(outside)
    assert client.get(result['preview_url']).status_code == 404


def test_discard_removes_staged_files_only(client):
    result = generate(client)
    response = client.delete(f"/api/projects/1/ambience/{result['id']}")
    assert response.status_code == 204
    assert not list(web.settings.image_generation_dir.iterdir())
    assert not web.settings.assets_dir.exists()
    assert client.get(result['preview_url']).status_code == 404


def test_name_cannot_escape_assets(client):
    result = generate(client)
    response = client.post(f"/api/projects/1/ambience/{result['id']}/accept", json={'name':'../../escape'})
    assert response.status_code == 201
    assert response.json()['asset'] == 'escape.png'
    assert (web.settings.assets_dir / 'backgrounds' / 'escape.png').is_file()


def test_empty_name_does_not_consume_preview(client):
    result = generate(client)
    assert client.post(f"/api/projects/1/ambience/{result['id']}/accept", json={'name':'...'}).status_code == 409
    assert client.get(result['preview_url']).status_code == 200
