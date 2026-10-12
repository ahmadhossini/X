"""Regression tests for the production ARQ worker import path."""


def test_arq_task_module_imports_with_task_billing_functions():
    # Importing this module is part of ARQ startup. Keep this explicit so a
    # missing/misrouted billing symbol cannot pass compile-only CI again.
    from app.workers.tasks import process_coding_task, reconcile_coding_tasks

    assert callable(process_coding_task)
    assert callable(reconcile_coding_tasks)
