from __future__ import annotations

import logging

from bot import main as bot_main


def test_enqueue_reserved_task_uses_coding_queue(monkeypatch):
    calls = []

    def fake_run_async(func, task_id):
        calls.append((func, task_id))
        return f"task:{task_id}"

    monkeypatch.setattr(bot_main, "_run_async", fake_run_async)

    assert bot_main._enqueue_reserved_task("abc123") is True
    assert calls == [(bot_main.enqueue_coding_task, "abc123")]


def test_enqueue_reserved_task_keeps_persisted_task_for_reconciliation(monkeypatch, caplog):
    def fail_to_enqueue(func, task_id):
        raise RuntimeError("Redis unavailable")

    monkeypatch.setattr(bot_main, "_run_async", fail_to_enqueue)

    with caplog.at_level(logging.ERROR, logger="bot.main"):
        assert bot_main._enqueue_reserved_task("abc123") is False

    assert "task remains queued for worker reconciliation" in caplog.text
    assert "abc123" in caplog.text
