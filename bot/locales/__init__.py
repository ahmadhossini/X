from __future__ import annotations

from bot.locales.en import TEXTS as EN
from bot.locales.hi import TEXTS as HI

SUPPORTED_LANGUAGES = ("en", "hi")
TEXTS = {"en": EN, "hi": HI}


def t(language: str, key: str, **kwargs: object) -> str:
    selected = language if language in TEXTS else "en"
    template = TEXTS[selected].get(key) or EN.get(key) or key
    return template.format(**kwargs)
