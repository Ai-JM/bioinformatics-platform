from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.config import RESULTS_DIR


def create_job_id(prefix: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"{prefix}_{timestamp}_{short_uuid}"


def create_job_dir(job_id: str) -> Path:
    job_dir = RESULTS_DIR / job_id
    (job_dir / "inputs").mkdir(parents=True, exist_ok=False)
    (job_dir / "outputs").mkdir(parents=True, exist_ok=True)
    (job_dir / "logs").mkdir(parents=True, exist_ok=True)
    return job_dir


def save_uploaded_files(uploaded_files: list[Any], job_dir: Path) -> list[str]:
    saved_paths: list[str] = []
    input_dir = job_dir / "inputs"

    for uploaded_file in uploaded_files:
        destination = input_dir / uploaded_file.name
        destination.write_bytes(uploaded_file.getbuffer())
        saved_paths.append(str(destination))

    return saved_paths


def save_json(payload: dict[str, Any], path: Path) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_job_manifest(
    job_dir: Path,
    *,
    job_id: str,
    module_key: str,
    module_label: str,
    parameters: dict[str, str],
    input_files: list[str],
) -> Path:
    manifest = {
        "job_id": job_id,
        "module_key": module_key,
        "module_label": module_label,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "parameters": parameters,
        "input_files": input_files,
        "status": "created",
    }
    manifest_path = job_dir / "job_manifest.json"
    save_json(manifest, manifest_path)
    return manifest_path
