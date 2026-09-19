from __future__ import annotations

from typing import Any

from code_agent.github_app import github_app_get, github_app_get_installation


class GitHubServiceError(RuntimeError):
    pass


class GitHubService:
    """Application boundary for GitHub App installation operations."""

    async def get_installation(self, installation_id: int) -> dict[str, Any]:
        try:
            return await github_app_get_installation(installation_id)
        except Exception as exc:
            raise GitHubServiceError(str(exc)) from exc

    async def get(self, installation_id: int, path: str) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub API path must start with '/'")
        try:
            return await github_app_get(path, installation_id)
        except Exception as exc:
            raise GitHubServiceError(str(exc)) from exc

    async def list_repositories(self, installation_id: int) -> list[dict[str, Any]]:
        repositories: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self.get(
                installation_id,
                f"/installation/repositories?per_page=100&page={page}",
            )
            batch = data.get("repositories", []) if isinstance(data, dict) else []
            if not batch:
                break
            repositories.extend(item for item in batch if isinstance(item, dict))
            if len(batch) < 100:
                break
            page += 1
        return repositories
