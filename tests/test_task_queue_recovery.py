from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bot.task_queue as task_queue


def test_stale_task_recovery_requeues_side_effected_work(monkeypatch):
    class FakeTask:
        def __init__(self, task_id: str, status: str):
            self.id = task_id
            self.status = status
            self.worker_id = "dead-worker"
            self.locked_at = datetime.now(timezone.utc) - timedelta(seconds=task_queue.CLAIM_LEASE_SECONDS + 1)
            self.error = "old error"

    task = FakeTask("task-1", "committed")

    class FakeScalars:
        def __init__(self, value):
            self.value = value

        def __iter__(self):
            return iter([self.value])

    class FakeResult:
        def __init__(self, value):
            self.value = value

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def scalars(self, statement):
            return FakeScalars(task)

        def commit(self):
            return None

        def rollback(self):
            return None

    monkeypatch.setattr(task_queue, "SessionLocal", FakeDB)

    recovered = task_queue.recover_stale_tasks()

    assert recovered == 1
    assert task.status == "queued"
    assert task.worker_id is None
    assert task.locked_at is None
    assert task.error is None


def test_active_statuses_include_changes_applied_for_recovery():
    assert "changes_applied" in task_queue._ACTIVE_STATUSES
