from billing.service import estimate_task_credits


def test_estimate_task_credits_defaults_to_code_change():
    assert estimate_task_credits("add a login button") == 5


def test_estimate_task_credits_detects_analysis():
    assert estimate_task_credits("analyze the authentication flow") == 3
    assert estimate_task_credits("این کد را بررسی کن") == 3


def test_estimate_task_credits_detects_heavy_debugging():
    assert estimate_task_credits("fix the login error and debug the crash") == 10
    assert estimate_task_credits("این باگ را رفع کن") == 10
