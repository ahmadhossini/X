import asyncio

import code_agent.agent as agent
from code_agent.agent import _branch_name, _output_language, _safe_path
from code_agent.github import GitHubRepoError


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


def test_requested_branch_name_is_preserved_exactly():
    request = "یک branch جدید با نام test/agent-file-write بساز"
    assert agent._requested_branch_name(request) == "test/agent-file-write"
    assert _branch_name(request, "task-123") == "test/agent-file-write"


def test_requested_branch_name_supports_english_and_ignores_unspecified_names():
    assert agent._requested_branch_name("create a branch named feature/fix-login") == "feature/fix-login"
    assert agent._requested_branch_name("fix the login bug") is None


def test_invalid_explicit_branch_name_is_rejected():
    import pytest
    request = "create branch named ../main"
    with pytest.raises(agent.AgentError, match="valid Git branch name"):
        agent._requested_branch_name(request)


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



def test_agent_marks_partial_github_side_effect_when_pr_creation_fails(monkeypatch):
    class FakeRepo:
        def __init__(self, repository, installation_id):
            self.branch_created = False
            self.closed = False

        async def repo(self):
            return {"default_branch": "main"}

        async def create_branch(self, branch, base):
            self.branch_created = True

        async def apply_changes(self, branch, changes, commit_message, idempotency_marker=None):
            return "commit-sha"

        async def pull_request(self, branch, base, title, body):
            raise GitHubRepoError("simulated pull request failure")

        async def aclose(self):
            self.closed = True

    async def fake_build_context(repo, base):
        return {}

    async def fake_plan_changes(api_key, model, request, context, language):
        return {"summary": "test change", "changes": [{"path": "sample.py", "content": "value = 1"}]}

    monkeypatch.setattr(agent, "GitHubRepo", FakeRepo)
    monkeypatch.setattr(agent, "build_context", fake_build_context)
    monkeypatch.setattr(agent, "plan_changes", fake_plan_changes)

    try:
        asyncio.run(
            agent.execute_task(
                "test-key",
                "test-model",
                "owner/repo",
                "make a test change",
                123,
                True,
                "en",
                None,
            )
        )
    except GitHubRepoError as exc:
        assert getattr(exc, "side_effects_applied", False) is True
    else:
        raise AssertionError("Expected simulated pull request failure")


def test_agent_marks_ambiguous_branch_creation_failure_as_side_effect(monkeypatch):
    class FakeRepo:
        def __init__(self, repository, installation_id):
            self.branch_created = False
            self.closed = False

        async def repo(self):
            return {"default_branch": "main"}

        async def create_branch(self, branch, base):
            # Simulate GitHub creating the branch, then the response being lost.
            self.branch_created = True
            raise GitHubRepoError("simulated timeout after branch creation")

        async def aclose(self):
            self.closed = True

    async def fake_build_context(repo, base):
        return {}

    async def fake_plan_changes(api_key, model, request, context, language):
        return {"summary": "test change", "changes": [{"path": "sample.py", "content": "value = 1"}]}

    monkeypatch.setattr(agent, "GitHubRepo", FakeRepo)
    monkeypatch.setattr(agent, "build_context", fake_build_context)
    monkeypatch.setattr(agent, "plan_changes", fake_plan_changes)

    try:
        asyncio.run(
            agent.execute_task(
                "test-key",
                "test-model",
                "owner/repo",
                "make a test change",
                123,
                True,
                "en",
                None,
            )
        )
    except GitHubRepoError as exc:
        assert getattr(exc, "side_effects_applied", False) is True
    else:
        raise AssertionError("Expected simulated branch-creation timeout")
