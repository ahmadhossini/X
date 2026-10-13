from code_agent.agent import _branch_name, _output_language, _safe_path


def test_safe_path_rejects_traversal_and_protected_files():
    assert _safe_path("code_agent/agent.py")
    assert not _safe_path("../secrets.txt")
    assert not _safe_path(".git/config")
    assert not _safe_path(".github/workflows/deploy.yml")
    assert not _safe_path(".env")
    assert not _safe_path("keys/private.pem")
    assert not _safe_path("config/.env")
    assert not _safe_path("config/.env.production")
    assert not _safe_path("secrets/credentials.json")
    assert not _safe_path("src/.github/workflows/deploy.yml")
    assert not _safe_path("config/id_rsa")
    assert not _safe_path("config/token.p12")
    assert not _safe_path("C:/repo/.env")
    assert not _safe_path("config/../app.py")
    assert _safe_path("src/configuration.py")
    assert _safe_path("docs/README.md")


def test_branch_name_is_stable_for_task_and_contains_request_digest():
    first = _branch_name("fix login bug", "task-123")
    second = _branch_name("fix login bug", "task-123")
    other_task = _branch_name("fix login bug", "task-456")

    assert first.startswith("xai-agent/fix-login-bug-")
    assert first == second
    assert first != other_task
    assert len(first.rsplit("-", 1)[-1]) == 12


def test_branch_name_without_task_id_remains_deterministic():
    assert _branch_name("fix login bug") == _branch_name("fix login bug")


def test_output_language_prefers_selected_telegram_language():
    assert _output_language("fix this code", "fa") == "Persian (Farsi)"
    assert _output_language("این کد را درست کن", "en") == "English"
    assert _output_language("fix this code", "hi") == "Hindi"
    assert _output_language("این کد را درست کن") == "Persian (Farsi)"
