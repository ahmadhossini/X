from bot.task_queue import _failure_reason


def test_failure_reason_explains_common_github_permission_error():
    reason = _failure_reason("HTTP 403: Resource not accessible by integration", "en")
    assert "permission" in reason.lower()
    assert "GitHub App" in reason


def test_failure_reason_redacts_secret_assignments():
    reason = _failure_reason("request failed token=super-secret-token", "en")
    assert "super-secret-token" not in reason
    assert "[redacted]" in reason


def test_failure_reason_reports_no_changes_in_persian():
    reason = _failure_reason("no_changes", "fa")
    assert "تغییر" in reason


def test_failure_reason_limits_raw_exception_length():
    reason = _failure_reason("x" * 1000, "en")
    assert len(reason) <= 520
