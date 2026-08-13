from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "locales"


def get_text(lang: str, key: str, **kwargs) -> str:
    file_path = BASE / f"{lang}.json"

    if not file_path.exists():
        file_path = BASE / "fa.json"

    with file_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return data.get(key, key).format(**kwargs)
