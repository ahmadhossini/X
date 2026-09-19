from __future__ import annotations

from typing import Any

import httpx


class GitHubServiceError(RuntimeError):
    pass


class GitHubService:
    """Application-level GitHub boundary; handlers/workers should depend on this API."""

    def __init__(self, token: str, base_url: str = "https://api.github.com") -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(20.0, connect=10.0),
            headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"},
        )

    async def get_repository(self, full_name: str) -> dict[str, Any]:
        response = await self._client.get(f"/repos/{full_name}")
        if response.status_code >= 400:
            raise GitHubServiceError(f"GitHub repository lookup failed: {response.status_code}")
        return response.json()

    async def close(self) -> None:
        await self._client.aclose()
