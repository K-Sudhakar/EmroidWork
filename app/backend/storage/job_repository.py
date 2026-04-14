import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path

from app.backend.core.errors import NotFoundAppError, ValidationAppError
from app.backend.models.job import Job

_JOB_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


class JsonJobRepository:
    def __init__(self, jobs_dir: Path) -> None:
        self.jobs_dir = jobs_dir
        self._lock = threading.RLock()

    def ensure_directories(self) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def create(self, job: Job) -> Job:
        with self._lock:
            path = self._path_for(job.job_id)
            if path.exists():
                raise ValueError(f"Job already exists: {job.job_id}")
            self._write(job)
            return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            path = self._path_for(job_id)
            if not path.exists():
                raise NotFoundAppError("Job was not found.")
            return self._read(path)

    def update(self, job: Job) -> Job:
        with self._lock:
            job = job.model_copy(update={"updated_at": datetime.now(UTC)})
            self._write(job)
            return job

    def _path_for(self, job_id: str) -> Path:
        if not _JOB_ID_PATTERN.fullmatch(job_id):
            raise ValidationAppError("Job id is invalid.", code="invalid_job_id")
        return self.jobs_dir / f"{job_id}.json"

    def _read(self, path: Path) -> Job:
        with path.open("r", encoding="utf-8") as input_file:
            return Job.model_validate_json(input_file.read())

    def _write(self, job: Job) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        path = self._path_for(job.job_id)
        temp_path = path.with_suffix(".json.tmp")
        payload = job.model_dump(mode="json")
        with temp_path.open("w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")
        os.replace(temp_path, path)
