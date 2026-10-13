import asyncio
from types import SimpleNamespace

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

    async def close(self):
        return None


def _pool_factory(pool):
    async def create_pool(_redis_settings):
        return pool
    return create_pool


def _configure_queue(monkeypatch, pool):
    monkeypatch.setattr(
        task_queue, "settings", SimpleNamespace(redis_url="redis://localhost:6379/0")
    )
    monkeypatch.setattr(task_queue, "create_pool", _pool_factory(pool))
    monkeypatch.setattr(task_queue.RedisSettings, "from_dsn", lambda _dsn: object())


def test_enqueue_coding_task_uses_deterministic_job_id(monkeypatch):
    pool = _FakePool(_FakeJob())
    _configure_queue(monkeypatch, pool)
    job_id = asyncio.run(task_queue.enqueue_coding_task("abc123"))
    assert job_id == "task:abc123"
    assert pool.calls[0][0] == ("process_coding_task", "abc123")
    assert pool.calls[0][1]["_job_id"] == "task:abc123"


def test_enqueue_coding_task_treats_duplicate_as_success(monkeypatch):
    pool = _FakePool(None)
    _configure_queue(monkeypatch, pool)
    assert asyncio.run(task_queue.enqueue_coding_task("abc123")) == "task:abc123"


from app.workers.github_events import _workflow_run_fields


def test_workflow_run_fields_extract_ci_identity():
    payload = {
        "repository": {"full_name": "goodahmad001o-lang/X"},
        "installation": {"id": 157669002},
        "workflow_run": {
            "id": 12345,
            "head_sha": "abc123",
            "status": "completed",
            "conclusion": "success",
            "html_url": "https://github.com/goodahmad001o-lang/X/actions/runs/12345",
        },
    }
    assert _workflow_run_fields(payload) == (
        "goodahmad001o-lang/X", "abc123", "completed", "success", 12345,
        "https://github.com/goodahmad001o-lang/X/actions/runs/12345", 157669002,
    )
