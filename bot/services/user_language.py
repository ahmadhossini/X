from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

# Keep the language file inside the project regardless of Railway's current working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = Path(os.getenv("USER_LANGUAGE_FILE", str(PROJECT_ROOT / "data" / "user_languages.json")))
_LOCK = Lock()
_CACHE: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not DATA_FILE.exists():
        _CACHE = {}
        return _CACHE
    try:
        value = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        _CACHE = value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        _CACHE = {}
    return _CACHE


def _save(data: dict[str, str]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = DATA_FILE.with_suffix(".tmp")
    temp_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_file.replace(DATA_FILE)


def get_user_language(user_id: int) -> str | None:
    with _LOCK:
        return _load().get(str(user_id))


def set_user_language(user_id: int, language: str) -> None:
    global _CACHE
    if language not in {"fa", "en"}:
        raise ValueError("Unsupported language")
    with _LOCK:
        data = _load()
        data[str(user_id)] = language
        _CACHE = data
        _save(data)
