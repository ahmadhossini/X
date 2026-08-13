from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

DATA_FILE = Path(os.getenv("USER_LANGUAGE_FILE", "data/user_languages.json"))
_LOCK = Lock()


def _load() -> dict[str, str]:
    if not DATA_FILE.exists():
        return {}
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict[str, str]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_user_language(user_id: int) -> str | None:
    with _LOCK:
        return _load().get(str(user_id))


def set_user_language(user_id: int, language: str) -> None:
    if language not in {"fa", "en"}:
        raise ValueError("Unsupported language")
    with _LOCK:
        data = _load()
        data[str(user_id)] = language
        _save(data)
