from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
LOCALES_DIR = BASE_DIR / "locales"


def load_language(language: str) -> dict[str, Any]:
    if language not in {"fa", "en"}:
        language = "fa"
    with (LOCALES_DIR / f"{language}.json").open("r", encoding="utf-8") as file:
        return json.load(file)


def get_text(language: str, key: str, **kwargs: Any) -> str:
    value = load_language(language).get(key, key)
    return value.format(**kwargs)
