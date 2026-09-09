from __future__ import annotations

import asyncio
import base64
import random
from typing import Any
from urllib.parse import quote

import httpx

from code_agent.github_app import GitHubAppError, installation_token, invalidate_installation_token


class GitHubRepoError(RuntimeError):
    pass


class GitHubRepo:
    def __init__(self, full_name: str, installation_id: int):
        if full_name.count("/") != 1 or any(part in full_name for part in ("..", " ")):
            raise GitHubRepoError("Invalid repository name")
        if not installation_id:
            raise GitHubRepoError("GitHub installation is required")
        self.full_name = full_name
        self.installation_id = installation_id
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(45.0, connect=10.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=30),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            value = response.headers.get("Retry-After")
            if value:
                try:
                    return min(max(float(value), 0.0), 10.0)
                except (TypeError, ValueError):
                    pass
        return min(2**attempt, 8) + random.random()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        for token_attempt in range(2):
            try:
                token = await installation_token(self.installation_id, force_refresh=token_attempt == 1)
            except GitHubAppError as exc:
                raise GitHubRepoError(str(exc)) from exc

            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Authorization": f"Bearer {token}",
            }
            url = f"https://api.github.com/repos/{self.full_name}{path}"
            client = await self._get_client()

            for attempt in range(4):
                response: httpx.Response | None = None
                try:
                    response = await client.request(method, url, headers=headers, **kwargs)
                    if response.status_code == 401 and token_attempt == 0:
                        invalidate_installation_token(self.installation_id)
                        break
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < 3:
                            await asyncio.sleep(self._retry_delay(response, attempt))
                            continue
                    if response.is_error:
                        detail = response.text[:500].replace("\n", " ")
                        raise GitHubRepoError(f"GitHub API {response.status_code}: {detail}")
                    return response.json()
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_error = exc
                    if attempt >= 3:
                        break
                    await asyncio.sleep(self._retry_delay(response, attempt))

            if last_error is not None and token_attempt == 1:
                raise GitHubRepoError(f"GitHub network error: {last_error}") from last_error

        if last_error is not None:
            raise GitHubRepoError(f"GitHub network error: {last_error}") from last_error
        raise GitHubRepoError("GitHub authentication failed after token refresh")

    async def repo(self) -> dict[str, Any]:
        return await self._request("GET", "")

    async def commit(self, ref: str) -> dict[str, Any]:
        return await self._request("GET", f"/commits/{quote(ref, safe='')}")

    async def tree(self, ref: str) -> dict[str, Any]:
        commit = await self.commit(ref)
        return await self._request("GET", f"/git/trees/{commit['commit']['tree']['sha']}?recursive=1")

    async def file(self, path: str, ref: str) -> str:
        data = await self._request("GET", f"/contents/{quote(path, safe='/')}?ref={quote(ref, safe='')}")
        if data.get("type") != "file":
            raise GitHubRepoError(f"{path} is not a file")
        try:
            return base64.b64decode(data["content"], validate=True).decode("utf-8")
        except (KeyError, ValueError, UnicodeDecodeError) as exc:
            raise GitHubRepoError(f"Unable to decode GitHub file: {path}") from exc

    async def create_branch(self, name: str, base: str) -> None:
        source = await self.commit(base)
        await self._request("POST", "/git/refs", json={"ref": f"refs/heads/{name}", "sha": source["sha"]})

    async def apply_changes(self, branch: str, changes: list[dict[str, Any]], message: str) -> str:
        head = await self.commit(branch)
        base_tree = head["commit"]["tree"]["sha"]
        tree_entries: list[dict[str, Any]] = []
        for change in changes:
            path = change["path"]
            action = change.get("action", "modify")
            if action == "delete":
                tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
                continue
            content = change.get("content")
            if not isinstance(content, str):
                raise GitHubRepoError(f"Missing content for {path}")
            tree_entries.append({"path": path, "mode": "100644", "type": "blob", "content": content})
        tree = await self._request("POST", "/git/trees", json={"base_tree": base_tree, "tree": tree_entries})
        new_commit = await self._request(
            "POST", "/git/commits", json={"message": message, "tree": tree["sha"], "parents": [head["sha"]]}
        )
        await self._request(
            "PATCH",
            f"/git/refs/heads/{quote(branch, safe='/')}",
            json={"sha": new_commit["sha"], "force": False},
        )
        return new_commit["sha"]

    async def pull_request(self, branch: str, base: str, title: str, body: str) -> dict[str, Any]:
        return await self._request(
            "POST", "/pulls", json={"title": title, "body": body, "head": branch, "base": base, "draft": True}
        )
