import hashlib

import pytest
from fastapi import HTTPException

from api.main import app, telegram_webhook
from core.config import settings


class FakeBot:
    def __init__(self):
        self.updates = []

    def process_new_updates(self, updates):
        self.updates.extend(updates)


def test_webhook_rejects_missing_or_invalid_secret(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", "test-token")
    bot = FakeBot()
    app.state.telegram_bot = bot
    app.state.telegram_webhook_secret = hashlib.sha256(
        b"test-token:xai-telegram-webhook"
    ).hexdigest()

    with pytest.raises(HTTPException) as exc:
        telegram_webhook({}, None)
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        telegram_webhook({}, "wrong")
    assert exc.value.status_code == 401


def test_webhook_accepts_valid_secret_and_dispatches_update(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", "test-token")
    bot = FakeBot()
    secret = hashlib.sha256(b"test-token:xai-telegram-webhook").hexdigest()
    app.state.telegram_bot = bot
    app.state.telegram_webhook_secret = secret

    class ParsedUpdate:
        pass

    parsed = ParsedUpdate()
    monkeypatch.setattr(
        "api.main.types.Update.de_json",
        staticmethod(lambda update: parsed),
    )

    assert telegram_webhook({"update_id": 1}, secret) == {"ok": True}
    assert bot.updates == [parsed]
