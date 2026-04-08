from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings


def _storage_dir() -> Path:
    path = Path(get_settings().ssh_key_storage_dir)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.strip()
    return suffix if suffix else ".key"


def _candidate_paths(stored_filename: str) -> list[Path]:
    raw = Path(stored_filename)
    storage_dir = _storage_dir()
    candidates: list[Path] = []

    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append((storage_dir / raw).resolve())
        candidates.append((Path.cwd() / raw).resolve())
        candidates.append((storage_dir / raw.name).resolve())

    seen: set[str] = set()
    unique_candidates: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)
    return unique_candidates


def store_private_key(
    upload: UploadFile,
    existing_stored_filename: str | None = None,
) -> tuple[str, str]:
    content = upload.file.read()
    if not content:
        raise ValueError("empty_private_key")

    storage_dir = _storage_dir()
    stored_filename = f"{uuid4().hex}{_safe_suffix(upload.filename)}"
    target = storage_dir / stored_filename
    target.write_bytes(content)

    if existing_stored_filename:
        delete_private_key(existing_stored_filename)

    return stored_filename, upload.filename or stored_filename


def delete_private_key(stored_filename: str | None) -> None:
    if not stored_filename:
        return
    for target in _candidate_paths(stored_filename):
        if target.exists():
            target.unlink()
            break


def resolve_private_key_path(stored_filename: str) -> str:
    for candidate in _candidate_paths(stored_filename):
        if candidate.exists():
            return str(candidate)
    return str(_candidate_paths(stored_filename)[-1])
