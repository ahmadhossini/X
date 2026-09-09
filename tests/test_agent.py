from code_agent.agent import _branch_name, _output_language, _safe_path


def test_safe_path_rejects_traversal_and_protected_files():
    assert _safe_path("code_agent/agent.py")
    assert not _safe_path("../secrets.txt")
    assert not _safe_path(".git/config")
    assert not _safe_path(".github/workflows/deploy.yml")
    assert not _safe_path(".env")
    assert not _safe_path("keys/private.pem")


def test_branch_name_is_unique_and_contains_request_digest():
    first = _branch_name("fix login bug")
    second = _branch_name("fix login bug")
    other = _branch_name("add login tests")

    assert first.startswith("xai-agent/fix-login-bug-")
    assert second.startswith("xai-agent/fix-login-bug-")
    assert first != second
    assert first != other
    assert len(first.rsplit("-", 1)[-1]) == 6


def test_output_language_prefers_selected_telegram_language():
    assert _output_language("fix this code", "fa") == "Persian (Farsi)"
    assert _output_language("این کد را درست کن", "en") == "English"
    assert _output_language("fix this code", "hi") == "Hindi"
    assert _output_language("این کد را درست کن") == "Persian (Farsi)"
