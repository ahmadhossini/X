from code_agent.agent import _branch_name, _output_language, _safe_path


def test_safe_path_blocks_traversal_and_secrets():
    assert _safe_path("src/app.py")
    assert not _safe_path("../secrets.txt")
    assert not _safe_path(".env")
    assert not _safe_path("keys/private.pem")
    assert not _safe_path(".github/workflows/ci.yml")


def test_branch_name_is_deterministic_and_task_scoped():
    first = _branch_name("Fix login bug", "task-123")
    second = _branch_name("Fix login bug", "task-123")
    other = _branch_name("Fix login bug", "task-456")
    assert first == second
    assert first != other
    assert first.startswith("xai-agent/")


def test_output_language_prefers_saved_language():
    assert _output_language("Fix the bug", "fa") == "Persian (Farsi)"
    assert _output_language("Fix the bug", "hi") == "Hindi"
    assert _output_language("Fix the bug", "en") == "English"


def test_output_language_detects_request_language():
    assert _output_language("این خطا را اصلاح کن") == "Persian (Farsi)"
    assert _output_language("यह बग ठीक करो") == "Hindi"
    assert _output_language("Fix this bug") == "English"
