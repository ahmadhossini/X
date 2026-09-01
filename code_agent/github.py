from __future__ import annotations

from typing import Any

import httpx

from code_agent.github_app import GitHubAppError, installation_token


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

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            token = await installation_token(self.installation_id)
        except GitHubAppError as exc:
            raise GitHubRepoError(str(exc)) from exc
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {token}",
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.request(method, f"https://api.github.com/repos/{self.full_name}{path}", headers=headers, **kwargs)
        if response.is_error:
            raise GitHubRepoError(f"GitHub API {response.status_code}: {response.text[:500]}")
        return response.json()

    async def repo(self) -> dict[str, Any]:
        return await self._request("GET", "")

    async def commit(self, ref: str) -> dict[str, Any]:
        return await self._request("GET", f"/commits/{ref}")

    async def tree(self, ref: str) -> dict[str, Any]:
        commit = await self.commit(ref)
        return await self._request("GET", f"/git/trees/{commit['commit']['tree']['sha']}?recursive=1")

    async def file(self, path: str, ref: str) -> str:
        data = await self._request("GET", f"/contents/{path}?ref={ref}")
        if data.get("type") != "file":
            raise GitHubRepoError(f"{path} is not a file")
        import base64
        return base64.b64decode(data["content"]).decode("utf-8")

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
        await self._request("PATCH", f"/git/refs/heads/{branch}", json={"sha": new_commit["sha"], "force": False})
        return new_commit["sha"]

    async def pull_request(self, branch: str, base: str, title: str, body: str) -> dict[str, Any]:
        return await self._request("POST", "/pulls", json={"title": title, "body": body, "head": branch, "base": base, "draft": True})
