from __future__ import annotations

import asyncio

import pytest

import code_agent.agent as agent
from code_agent.github import GitHubRepoError


def run(coro):
    return asyncio.run(coro)


class FakeRepo:
    def __init__(self, branch_head=None, marker_commit=None, marker_details=None, base_details=None):
        self.branch_head = branch_head
        self.marker_commit = marker_commit
        self.marker_details = marker_details or {"sha": "marker", "parents": [{"sha": "base"}]}
        self.base_details = base_details or {"sha": "base"}
        self.updated = None
        self.created = None

    async def find_task_commit(self, marker):
        return self.marker_commit

    async def commit(self, ref):
        if ref == "main":
            return self.base_details
        if ref == "xai-agent/request-digest-taskdigest":
            if self.branch_head is None:
                raise GitHubRepoError("GitHub API 404: Not Found")
            return self.branch_head
        if ref == "marker":
            return self.marker_details
        raise AssertionError(ref)

    async def update_branch(self, branch, sha):
        self.updated = (branch, sha)

    async def create_branch(self, branch, sha):
        self.created = (branch, sha)


def setup_branch_name(monkeypatch):
    monkeypatch.setattr(agent, "_branch_name", lambda request, task_id=None: "xai-agent/request-digest-taskdigest")


def test_reconcile_returns_when_marker_is_branch_head(monkeypatch):
    setup_branch_name(monkeypatch)
    repo = FakeRepo(branch_head={"sha": "marker"}, marker_commit={"sha": "marker", "parents": [{"sha": "base"}]})
    result = run(agent.reconcile_task(repo, "main", "request", "task-1"))
    assert result["commit"] == "marker"
    assert result["branch"] == "xai-agent/request-digest-taskdigest"
    assert repo.updated is None


def test_reconcile_fast_forwards_when_marker_parent_is_branch_head(monkeypatch):
    setup_branch_name(monkeypatch)
    repo = FakeRepo(
        branch_head={"sha": "base"},
        marker_commit={"sha": "marker", "parents": [{"sha": "base"}]},
    )
    result = run(agent.reconcile_task(repo, "main", "request", "task-1"))
    assert result["commit"] == "marker"
    assert repo.updated == ("xai-agent/request-digest-taskdigest", "marker")


def test_reconcile_does_not_attach_unrelated_marker_commit(monkeypatch):
    setup_branch_name(monkeypatch)
    repo = FakeRepo(
        branch_head={"sha": "other"},
        marker_commit={"sha": "marker", "parents": [{"sha": "different"}]},
    )
    assert run(agent.reconcile_task(repo, "main", "request", "task-1")) is None
    assert repo.updated is None
    assert repo.created is None


def test_reconcile_reattaches_orphan_commit_only_from_base(monkeypatch):
    setup_branch_name(monkeypatch)
    repo = FakeRepo(
        branch_head=None,
        marker_commit={"sha": "marker", "parents": [{"sha": "base"}]},
    )
    result = run(agent.reconcile_task(repo, "main", "request", "task-1"))
    assert result["commit"] == "marker"
    assert repo.created == ("xai-agent/request-digest-taskdigest", "marker")


def test_reconcile_rejects_orphan_commit_with_wrong_parent(monkeypatch):
    setup_branch_name(monkeypatch)
    repo = FakeRepo(
        branch_head=None,
        marker_commit={"sha": "marker", "parents": [{"sha": "different"}]},
    )
    assert run(agent.reconcile_task(repo, "main", "request", "task-1")) is None
    assert repo.created is None
