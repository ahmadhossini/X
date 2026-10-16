from __future__ import annotations

import logging

from bot import main as bot_main


def test_enqueue_reserved_task_returns_none_on_success(monkeypatch):
    calls = []

    def fake_run_async(func, task_id):
        calls.append((func, task_id))
        return f"task:{task_id}"

    monkeypatch.setattr(bot_main, "_run_async", fake_run_async)

    assert bot_main._enqueue_reserved_task("abc123", "fa") is None
    assert calls == [(bot_main.enqueue_coding_task, "abc123")]


def test_enqueue_reserved_task_returns_diagnostic_and_keeps_task_for_reconciliation(monkeypatch, caplog):
    def fail_to_enqueue(func, task_id):
        raise RuntimeError("Redis unavailable")

    monkeypatch.setattr(bot_main, "_run_async", fail_to_enqueue)

    with caplog.at_level(logging.ERROR, logger="bot.main"):
        reason = bot_main._enqueue_reserved_task("abc123", "fa")

    assert reason
    assert "Redis" in reason or "صف" in reason
    assert "task remains queued for worker reconciliation" in caplog.text
    assert "abc123" in caplog.text


def test_enqueue_diagnostic_identifies_missing_redis_url():
    reason = bot_main._safe_enqueue_reason(RuntimeError("REDIS_URL is required for the event queue"), "fa")
    assert "REDIS_URL" in reason
    assert "تنظیم" in reason


def test_enqueue_diagnostic_identifies_connection_refused():
    reason = bot_main._safe_enqueue_reason(ConnectionError("Error 111 connecting to redis-host:6379. Connection refused."), "fa")
    assert "رد شد" in reason


def test_enqueue_diagnostic_redacts_redis_credentials():
    error = RuntimeError("Connection failed redis://user:super-secret@redis.example:6379/0")
    reason = bot_main._safe_enqueue_reason(error, "en")
    assert "super-secret" not in reason
    assert "credentials-redacted" in reason or "[redacted]" in reason
