"""Cua simple d'un únic renderitzat concurrent."""
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic

from app.database import SessionLocal
from app.models import Project, RenderConfig
from app.services.encoding import EncodingOptions, select_encoding
from app.services.renderer import RenderSpec, build_ffmpeg_command

STATUS_MAP = {"EN_CUA": "QUEUED", "GENERANT": "GENERATING", "COMPLETAT": "COMPLETED", "ERROR": "FAILED", "CANCEL·LAT": "CANCELLED"}


def _persist_status(project_id: int, status: str) -> None:
    mapped = STATUS_MAP.get(status)
    if not mapped:
        return
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if project and project.status != mapped:
            project.status = mapped
            db.commit()


def _persist_engine(project_id: int, engine: str) -> None:
    with SessionLocal() as db:
        config = db.query(RenderConfig).filter(RenderConfig.project_id == project_id).first()
        if config:
            config.actual_engine = engine
            db.commit()


def _cleanup_output(output: Path) -> None:
    output.unlink(missing_ok=True)
    folder = output.parent
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


@dataclass
class RenderJob:
    project_id: int
    status: str = "EN_CUA"
    progress: float = 0.0
    elapsed: float = 0.0
    eta: float | None = None
    error: str | None = None
    output: str | None = None
    engine: str | None = None
    fallback_used: bool = False
    cancel_requested: bool = False
    process: subprocess.Popen[str] | None = field(default=None, repr=False)


class RenderQueue:
    def __init__(self) -> None:
        self.jobs: dict[int, RenderJob] = {}
        self._queue: list[tuple[RenderJob, RenderSpec]] = []
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def enqueue(self, project_id: int, spec: RenderSpec) -> RenderJob:
        with self._lock:
            current = self.jobs.get(project_id)
            if current and current.status in {"EN_CUA", "GENERANT"}:
                return current
            job = RenderJob(project_id=project_id, output=str(spec.output))
            self.jobs[project_id] = job
            self._queue.append((job, spec))
            _persist_status(project_id, job.status)
            if not self._worker or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, daemon=True)
                self._worker.start()
            return job

    def cancel(self, project_id: int) -> bool:
        job = self.jobs.get(project_id)
        if not job or job.status not in {"EN_CUA", "GENERANT"}:
            return False
        job.cancel_requested = True
        if job.process and job.process.poll() is None:
            job.process.terminate()
        return True

    def _run(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    return
                job, spec = self._queue.pop(0)
            if job.cancel_requested:
                job.status = "CANCEL·LAT"
                _cleanup_output(Path(spec.output))
                _persist_status(job.project_id, job.status)
                continue
            self._execute(job, spec)

    def _run_ffmpeg(self, job: RenderJob, spec: RenderSpec, command: list[str], start: float) -> tuple[int, list[str]]:
        command[1:1] = ["-loglevel", "error"]
        job.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        assert job.process.stdout is not None
        log_tail: list[str] = []
        for raw in job.process.stdout:
            line = raw.strip()
            log_tail = (log_tail + [line])[-40:]
            key, _, value = line.partition("=")
            if key in {"out_time_us", "out_time_ms"}:
                try:
                    seconds = int(value) / 1_000_000
                    job.progress = min(100.0, seconds / spec.timeline.total_seconds * 100)
                    job.elapsed = monotonic() - start
                    if job.progress > 0:
                        job.eta = max(0.0, job.elapsed * (100 - job.progress) / job.progress)
                except ValueError:
                    pass
            if job.cancel_requested and job.process.poll() is None:
                job.process.terminate()
        return job.process.wait(), log_tail

    def _execute(self, job: RenderJob, spec: RenderSpec) -> None:
        start = monotonic()
        job.status = "GENERANT"
        _persist_status(job.project_id, job.status)
        try:
            plan = select_encoding(spec.encoding)
            job.engine = plan.engine
            _persist_engine(job.project_id, plan.engine)
            returncode, log_tail = self._run_ffmpeg(job, spec, build_ffmpeg_command(spec, plan=plan), start)

            if returncode != 0 and not job.cancel_requested and plan.engine == "nvenc":
                job.fallback_used = True
                job.engine = "cpu"
                job.progress = 0.0
                job.eta = None
                _persist_engine(job.project_id, "cpu")
                cpu_plan = select_encoding(EncodingOptions("cpu", spec.encoding.quality), has_nvenc=False)
                returncode, log_tail = self._run_ffmpeg(job, spec, build_ffmpeg_command(spec, plan=cpu_plan), start)

            job.elapsed = monotonic() - start
            if job.cancel_requested:
                job.status = "CANCEL·LAT"
                _cleanup_output(Path(spec.output))
            elif returncode == 0:
                job.status, job.progress, job.eta = "COMPLETAT", 100.0, 0.0
            else:
                job.status = "ERROR"
                job.error = "\n".join(log_tail)[-2000:] or f"FFmpeg ha finalitzat amb codi {returncode}"
                _cleanup_output(Path(spec.output))
        except Exception as exc:
            job.status, job.error = "ERROR", str(exc)
            _cleanup_output(Path(spec.output))
        finally:
            job.process = None
            _persist_status(job.project_id, job.status)


render_queue = RenderQueue()
