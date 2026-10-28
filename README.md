# Pomodoro Studio

Private, self-hosted studio for generating original long-form Pomodoro / Study With Me videos.

## Status

Early development (v0.1).

## Goals

- Configure focus/break cycles and total duration.
- Build exact timelines and YouTube chapters.
- Use original/licensed backgrounds, ambience and music.
- Render videos with FFmpeg.
- Generate thumbnails and metadata.
- Keep a local project/render history.
- Run locally or with Docker.

## Stack

Python 3.12 · FastAPI · Jinja2 · SQLAlchemy · SQLite · FFmpeg · Docker

## Development

The first milestone builds the application shell, project model, Pomodoro timeline engine, web UI, Docker setup and tests. Rendering is introduced incrementally after the timeline layer is stable.

## Copyright

Pomodoro Studio is designed for original or properly licensed assets. It does not download or republish third-party YouTube videos or protected music.
