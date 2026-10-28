"""Cua simple d'un únic renderitzat concurrent."""
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from app.services.renderer import RenderSpec, build_ffmpeg_command

@dataclass
class RenderJob:
    project_id: int
    status: str = "EN_CUA"
    progress: float = 0.0
    elapsed: float = 0.0
    eta: float | None = None
    error: str | None = None
    output: str | None = None
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
            if current and current.status in {"EN_CUA", "GENERANT"}: return current
            job = RenderJob(project_id=project_id, output=str(spec.output)); self.jobs[project_id] = job; self._queue.append((job, spec))
            if not self._worker or not self._worker.is_alive(): self._worker = threading.Thread(target=self._run, daemon=True); self._worker.start()
            return job

    def cancel(self, project_id: int) -> bool:
        job = self.jobs.get(project_id)
        if not job: return False
        job.cancel_requested = True
        if job.process and job.process.poll() is None: job.process.terminate()
        return True

    def _run(self) -> None:
        while True:
            with self._lock:
                if not self._queue: return
                job, spec = self._queue.pop(0)
            if job.cancel_requested: job.status = "CANCEL·LAT"; continue
            self._execute(job, spec)

    def _execute(self, job: RenderJob, spec: RenderSpec) -> None:
        start = monotonic(); job.status = "GENERANT"
        try:
            command = build_ffmpeg_command(spec); command[1:1] = ["-loglevel", "error"]
            job.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            assert job.process.stdout is not None
            log_tail: list[str] = []
            for raw in job.process.stdout:
                line = raw.strip(); log_tail.append(line); log_tail = log_tail[-40:]
                key, _, value = line.partition("=")
                if key in {"out_time_us", "out_time_ms"}:
                    try:
                        seconds = int(value) / 1_000_000; job.progress = min(100.0, seconds / spec.timeline.total_seconds * 100); job.elapsed = monotonic() - start
                        if job.progress > 0: job.eta = max(0.0, job.elapsed * (100 - job.progress) / job.progress)
                    except ValueError: pass
                if job.cancel_requested and job.process.poll() is None: job.process.terminate()
            returncode = job.process.wait(); job.elapsed = monotonic() - start
            if job.cancel_requested: job.status = "CANCEL·LAT"; Path(spec.output).unlink(missing_ok=True)
            elif returncode == 0: job.status, job.progress, job.eta = "COMPLETAT", 100.0, 0.0
            else: job.status, job.error = "ERROR", "\n".join(log_tail)[-2000:] or f"FFmpeg ha finalitzat amb codi {returncode}"
        except Exception as exc: job.status, job.error = "ERROR", str(exc)

render_queue = RenderQueue()
