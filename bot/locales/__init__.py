from __future__ import annotations

from bot.locales.en import TEXTS as EN
from bot.locales.hi import TEXTS as HI
from bot.locales.fa import TEXTS as FA

SUPPORTED_LANGUAGES = ("en", "hi", "fa")
TEXTS = {"en": EN, "hi": HI, "fa": FA}


def t(language: str, key: str, **kwargs: object) -> str:
    selected = language if language in TEXTS else "en"
    template = TEXTS[selected].get(key) or EN.get(key) or key
    return template.format(**kwargs)
