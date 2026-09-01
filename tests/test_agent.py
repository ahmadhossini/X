from code_agent.agent import _branch_name, _safe_path


def test_safe_path_rejects_traversal_and_protected_files():
    assert _safe_path("code_agent/agent.py")
    assert not _safe_path("../secrets.txt")
    assert not _safe_path(".git/config")
    assert not _safe_path(".github/workflows/deploy.yml")
    assert not _safe_path(".env")
    assert not _safe_path("keys/private.pem")


def test_branch_name_is_deterministic_and_unique_for_different_requests():
    first = _branch_name("fix login bug")
    second = _branch_name("fix login bug")
    other = _branch_name("add login tests")

    assert first == second
    assert first.startswith("xai-agent/fix-login-bug-")
    assert first != other
    assert len(first.rsplit("-", 1)[-1]) == 8
