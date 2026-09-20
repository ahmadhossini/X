import pytest

from app.workers import queue as task_queue


class _FakeJob:
    job_id = "task:abc123"


class _FakePool:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def enqueue_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


@pytest.mark.asyncio
async def test_enqueue_coding_task_uses_deterministic_job_id(monkeypatch):
    pool = _FakePool(_FakeJob())
    monkeypatch.setattr(task_queue, "get_pool", lambda: _async_return(pool))
    job_id = await task_queue.enqueue_coding_task("abc123")
    assert job_id == "task:abc123"
    assert pool.calls[0][0] == ("process_coding_task", "abc123")
    assert pool.calls[0][1]["_job_id"] == "task:abc123"


@pytest.mark.asyncio
async def test_enqueue_coding_task_treats_duplicate_as_success(monkeypatch):
    pool = _FakePool(None)
    monkeypatch.setattr(task_queue, "get_pool", lambda: _async_return(pool))
    assert await task_queue.enqueue_coding_task("abc123") == "task:abc123"


async def _async_return(value):
    return value
