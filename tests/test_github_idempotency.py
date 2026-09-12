from __future__ import annotations

import asyncio

from code_agent.github import GitHubRepo, GitHubRepoError


def test_apply_changes_skips_duplicate_commit_when_marker_is_on_head(monkeypatch):
    repo = GitHubRepo("goodahmad001o-lang/X", 153037631)
    calls: list[tuple[str, str]] = []

    async def authorize():
        calls.append(("authorize", ""))

    async def request(method, path, **kwargs):
        calls.append((method, path))
        assert method == "GET"
        assert path == "/commits/xai-agent%2Ffix-login"
        return {
            "sha": "existing-commit",
            "commit": {
                "message": "feat(agent): fix [XAI-TASK:task-123]",
                "tree": {"sha": "tree-sha"},
            },
        }

    monkeypatch.setattr(repo, "_authorize_repository", authorize)
    monkeypatch.setattr(repo, "_request", request)

    result = asyncio.run(
        repo.apply_changes(
            "xai-agent/fix-login",
            [{"path": "app.py", "action": "modify", "content": "print('new')"}],
            "feat(agent): fix [XAI-TASK:task-123]",
            idempotency_marker="XAI-TASK:task-123",
        )
    )

    assert result == "existing-commit"
    assert calls == [("authorize", ""), ("GET", "/commits/xai-agent%2Ffix-login")]


def test_apply_changes_retries_same_ref_update_after_ambiguous_failure(monkeypatch):
    repo = GitHubRepo("goodahmad001o-lang/X", 153037631)
    patch_attempts = 0

    async def authorize():
        return None

    async def request(method, path, **kwargs):
        nonlocal patch_attempts
        if method == "GET" and path == "/commits/xai-agent%2Ffix-login":
            return {
                "sha": "parent-sha",
                "commit": {"message": "old", "tree": {"sha": "base-tree"}},
            }
        if method == "POST" and path == "/git/trees":
            return {"sha": "new-tree"}
        if method == "POST" and path == "/git/commits":
            return {"sha": "new-commit"}
        if method == "PATCH" and path == "/git/refs/heads/xai-agent/fix-login":
            patch_attempts += 1
            if patch_attempts == 1:
                raise GitHubRepoError("ambiguous network failure")
            assert kwargs["json"] == {"sha": "new-commit", "force": False}
            return {"ref": "refs/heads/xai-agent/fix-login"}
        raise AssertionError((method, path))

    monkeypatch.setattr(repo, "_authorize_repository", authorize)
    monkeypatch.setattr(repo, "_request", request)

    result = asyncio.run(
        repo.apply_changes(
            "xai-agent/fix-login",
            [{"path": "app.py", "action": "modify", "content": "print('new')"}],
            "feat(agent): fix [XAI-TASK:task-123]",
            idempotency_marker="XAI-TASK:task-123",
        )
    )

    assert result == "new-commit"
    assert patch_attempts == 2
