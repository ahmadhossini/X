import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.workers import queue


def _patch_pool(pool):
    return (
        patch.object(queue, "settings", SimpleNamespace(redis_url="redis://localhost:6379/0")),
        patch.object(queue.RedisSettings, "from_dsn", return_value=object()),
        patch.object(queue, "create_pool", new=AsyncMock(return_value=pool)),
    )


def test_enqueue_closes_its_pool_after_success():
    pool = SimpleNamespace(
        enqueue_job=AsyncMock(return_value=SimpleNamespace(job_id="task:abc")),
        close=AsyncMock(),
    )
    with (
        patch.object(queue, "settings", SimpleNamespace(redis_url="redis://localhost:6379/0")),
        patch.object(queue.RedisSettings, "from_dsn", return_value=object()),
        patch.object(queue, "create_pool", new=AsyncMock(return_value=pool)) as create_pool,
    ):
        result = asyncio.run(queue._enqueue("process_coding_task", "task:abc", "abc"))

    assert result == "task:abc"
    create_pool.assert_awaited_once()
    pool.enqueue_job.assert_awaited_once_with("process_coding_task", "abc", _job_id="task:abc")
    pool.close.assert_awaited_once()


def test_enqueue_closes_its_pool_when_redis_enqueue_fails():
    pool = SimpleNamespace(
        enqueue_job=AsyncMock(side_effect=ConnectionError("redis unavailable")),
        close=AsyncMock(),
    )
    with (
        patch.object(queue, "settings", SimpleNamespace(redis_url="redis://localhost:6379/0")),
        patch.object(queue.RedisSettings, "from_dsn", return_value=object()),
        patch.object(queue, "create_pool", new=AsyncMock(return_value=pool)),
    ):
        try:
            asyncio.run(queue._enqueue("process_coding_task", "task:abc", "abc"))
        except ConnectionError as exc:
            assert str(exc) == "redis unavailable"
        else:
            raise AssertionError("Expected Redis enqueue failure to propagate")

    pool.close.assert_awaited_once()


def test_pool_close_failure_does_not_mask_enqueue_failure(caplog):
    pool = SimpleNamespace(
        enqueue_job=AsyncMock(side_effect=ConnectionError("redis unavailable")),
        close=AsyncMock(side_effect=RuntimeError("close failed")),
    )
    with (
        patch.object(queue, "settings", SimpleNamespace(redis_url="redis://localhost:6379/0")),
        patch.object(queue.RedisSettings, "from_dsn", return_value=object()),
        patch.object(queue, "create_pool", new=AsyncMock(return_value=pool)),
        caplog.at_level(logging.ERROR, logger="app.workers.queue"),
    ):
        try:
            asyncio.run(queue._enqueue("process_coding_task", "task:abc", "abc"))
        except ConnectionError as exc:
            assert str(exc) == "redis unavailable"
        else:
            raise AssertionError("Expected the original enqueue failure to propagate")

    pool.close.assert_awaited_once()
    assert "Failed to close Redis queue pool" in caplog.text
    assert "close failed" in caplog.text


def test_pool_close_failure_is_logged_without_changing_success(caplog):
    pool = SimpleNamespace(
        enqueue_job=AsyncMock(return_value=SimpleNamespace(job_id="task:abc")),
        close=AsyncMock(side_effect=RuntimeError("close failed")),
    )
    with (
        patch.object(queue, "settings", SimpleNamespace(redis_url="redis://localhost:6379/0")),
        patch.object(queue.RedisSettings, "from_dsn", return_value=object()),
        patch.object(queue, "create_pool", new=AsyncMock(return_value=pool)),
        caplog.at_level(logging.ERROR, logger="app.workers.queue"),
    ):
        result = asyncio.run(queue._enqueue("process_coding_task", "task:abc", "abc"))

    assert result == "task:abc"
    pool.close.assert_awaited_once()
    assert "Failed to close Redis queue pool" in caplog.text
    assert "close failed" in caplog.text
