from __future__ import annotations

import asyncio
import base64
import random
from typing import Any
from urllib.parse import quote

import httpx

from code_agent.github_app import (
    GitHubAppError,
    github_app_get,
    installation_token,
    invalidate_installation_token,
)


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
        self._authorized = False

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

    async def _request_search(self, path: str) -> Any:
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
            client = await self._get_client()
            for attempt in range(4):
                response: httpx.Response | None = None
                try:
                    response = await client.get(f"https://api.github.com{path}", headers=headers)
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

    async def _authorize_repository(self) -> None:
        if self._authorized:
            return
        try:
            for page in range(1, 101):
                data = await github_app_get(
                    f"/installation/repositories?per_page=100&page={page}",
                    self.installation_id,
                )
                if not isinstance(data, dict):
                    raise GitHubRepoError("Invalid GitHub installation repository response")
                repositories = data.get("repositories")
                if not isinstance(repositories, list):
                    raise GitHubRepoError("Invalid GitHub installation repository response")
                target = self.full_name.casefold()
                if any(
                    isinstance(item, dict)
                    and isinstance(item.get("full_name"), str)
                    and item["full_name"].casefold() == target
                    for item in repositories
                ):
                    self._authorized = True
                    return
                if len(repositories) < 100:
                    break
        except GitHubAppError as exc:
            raise GitHubRepoError(f"Unable to verify repository access: {exc}") from exc
        raise GitHubRepoError("Repository is not accessible through this GitHub installation")

    async def repo(self) -> dict[str, Any]:
        await self._authorize_repository()
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

    async def branch_commits(self, branch: str, limit: int = 100) -> list[dict[str, Any]]:
        await self._authorize_repository()
        safe_limit = max(1, min(limit, 100))
        data = await self._request("GET", f"/commits?sha={quote(branch, safe='/')}&per_page={safe_limit}")
        if not isinstance(data, list):
            raise GitHubRepoError("Invalid GitHub branch commit response")
        return [item for item in data if isinstance(item, dict)]

    async def find_task_commit(self, marker: str, limit: int = 10) -> dict[str, Any] | None:
        await self._authorize_repository()
        safe_limit = max(1, min(limit, 20))
        query = quote(marker, safe="")
        repo_query = quote(f"repo:{self.full_name}", safe="")
        data = await self._request_search(f"/search/commits?q={query}%20{repo_query}&per_page={safe_limit}")
        if not isinstance(data, dict):
            raise GitHubRepoError("Invalid GitHub commit search response")
        items = data.get("items")
        if not isinstance(items, list):
            raise GitHubRepoError("Invalid GitHub commit search response")
        for item in items:
            if isinstance(item, dict) and item.get("sha") and marker in str((item.get("commit") or {}).get("message") or ""):
                return item
        return None

    async def workflow_runs_for_commit(self, commit_sha: str) -> list[dict[str, Any]]:
        await self._authorize_repository()
        data = await self._request("GET", f"/actions/runs?head_sha={quote(commit_sha, safe='')}&per_page=20")
        if not isinstance(data, dict):
            raise GitHubRepoError("Invalid GitHub Actions workflow response")
        runs = data.get("workflow_runs")
        if not isinstance(runs, list):
            raise GitHubRepoError("Invalid GitHub Actions workflow response")
        return [run for run in runs if isinstance(run, dict)]

    async def workflow_run_jobs(self, run_id: int) -> list[dict[str, Any]]:
        await self._authorize_repository()
        all_jobs: list[dict[str, Any]] = []
        for page in range(1, 11):
            data = await self._request("GET", f"/actions/runs/{int(run_id)}/jobs?per_page=100&page={page}")
            if not isinstance(data, dict):
                raise GitHubRepoError("Invalid GitHub Actions jobs response")
            jobs = data.get("jobs")
            if not isinstance(jobs, list):
                raise GitHubRepoError("Invalid GitHub Actions jobs response")
            all_jobs.extend(job for job in jobs if isinstance(job, dict))
            if len(jobs) < 100:
                break
        return all_jobs

    async def create_branch(self, name: str, base: str) -> None:
        await self._authorize_repository()
        source = await self.commit(base)
        try:
            await self._request("POST", "/git/refs", json={"ref": f"refs/heads/{name}", "sha": source["sha"]})
        except GitHubRepoError as exc:
            if "GitHub API 422" not in str(exc):
                raise
            existing = await self._request("GET", f"/git/ref/heads/{quote(name, safe='/')}")
            existing_sha = (existing.get("object") or {}).get("sha") if isinstance(existing, dict) else None
            if existing_sha != source["sha"]:
                raise GitHubRepoError("Task branch already exists at a different commit") from exc

    async def update_branch(self, branch: str, sha: str) -> None:
        await self._authorize_repository()
        await self._request("PATCH", f"/git/refs/heads/{quote(branch, safe='/')}", json={"sha": sha, "force": False})

    async def apply_changes(self, branch: str, changes: list[dict[str, Any]], message: str, idempotency_marker: str | None = None) -> str:
        await self._authorize_repository()
        head = await self.commit(branch)
        head_message = ((head.get("commit") or {}).get("message") or "") if isinstance(head, dict) else ""
        if idempotency_marker and idempotency_marker in head_message:
            return head["sha"]
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
        new_commit = await self._request("POST", "/git/commits", json={"message": message, "tree": tree["sha"], "parents": [head["sha"]]})
        new_sha = new_commit["sha"]
        ref_path = f"/git/refs/heads/{quote(branch, safe='/')}"
        ref_payload = {"sha": new_sha, "force": False}
        try:
            await self._request("PATCH", ref_path, json=ref_payload)
        except GitHubRepoError as first_error:
            current = await self._request("GET", f"/git/ref/heads/{quote(branch, safe='/')}")
            current_sha = (current.get("object") or {}).get("sha") if isinstance(current, dict) else None
            if current_sha == new_sha:
                return new_sha
            if current_sha != head["sha"]:
                raise GitHubRepoError("Branch changed while applying task commit; refusing unsafe overwrite") from first_error
            await self._request("PATCH", ref_path, json=ref_payload)
        return new_sha

    async def pull_request(self, branch: str, base: str, title: str, body: str) -> dict[str, Any]:
        await self._authorize_repository()
        owner = self.full_name.split("/", 1)[0]
        existing = await self._request("GET", f"/pulls?state=open&head={quote(owner + ':' + branch, safe='')}&base={quote(base, safe='')}&per_page=10")
        if isinstance(existing, list) and existing:
            candidate = existing[0]
            if isinstance(candidate, dict) and candidate.get("number"):
                return candidate
        return await self._request("POST", "/pulls", json={"title": title, "body": body, "head": branch, "base": base, "draft": True})
