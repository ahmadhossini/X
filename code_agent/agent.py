from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from google import genai

from code_agent.github import GitHubRepo, GitHubRepoError


class AgentError(RuntimeError):
    pass


TEXT_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".yml", ".yaml", ".toml", ".txt", ".html", ".css"}
MAX_CONTEXT_CHARS = 120_000
MAX_CHANGED_FILES = 8
MAX_FILE_CHARS = 300_000
PROTECTED_PATHS = {".env", ".env.example", "credentials.json", "service-account.json"}
PROTECTED_PREFIXES = (".git/", ".github/workflows/")


def _safe_path(path: str) -> bool:
    if not path or path.startswith("/"):
        return False
    normalized = path.replace("\\", "/").strip("/")
    parts = normalized.split("/") if normalized else []
    if not normalized or ".." in parts or normalized.startswith(PROTECTED_PREFIXES):
        return False
    if normalized in PROTECTED_PATHS or normalized.endswith((".pem", ".key")):
        return False
    return True


def _branch_name(request: str, task_id: str | None = None) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", request.lower()).strip("-")[:45].rstrip("-") or "change"
    digest = hashlib.sha256(request.encode("utf-8")).hexdigest()[:8]
    suffix = hashlib.sha256((task_id or request).encode("utf-8")).hexdigest()[:12]
    return f"xai-agent/{slug}-{digest}-{suffix}"


def _request_language(request: str) -> str:
    if re.search(r"[\u0600-\u06ff]", request):
        return "Persian (Farsi)"
    if re.search(r"[\u0900-\u097f]", request):
        return "Hindi"
    return "English"


def _output_language(request: str, language: str | None = None) -> str:
    selected = {"fa": "Persian (Farsi)", "hi": "Hindi", "en": "English"}.get((language or "").lower())
    return selected or _request_language(request)


async def build_context(repo: GitHubRepo, ref: str, limit: int = 40) -> dict[str, str]:
    tree = await repo.tree(ref)
    files = [
        x["path"] for x in tree.get("tree", [])
        if x.get("type") == "blob"
        and any(x["path"].endswith(ext) for ext in TEXT_EXTENSIONS)
        and _safe_path(x["path"])
    ]
    files = sorted(files, key=lambda p: (p.count("/"), len(p)))[:limit]
    context: dict[str, str] = {}
    total = 0
    for path in files:
        try:
            content = await repo.file(path, ref)
        except Exception:
            continue
        remaining = MAX_CONTEXT_CHARS - total
        if remaining <= 0:
            break
        context[path] = content[:remaining]
        total += len(context[path])
    return context


async def plan_changes(
    api_key: str,
    model: str,
    request: str,
    context: dict[str, str],
    language: str | None = None,
) -> dict[str, Any]:
    if not api_key:
        raise AgentError("GEMINI_API_KEY is not configured")
    output_language = _output_language(request, language)
    prompt = f'''You are XAI Code Agent. Work as a careful senior engineer.
User request: {request}
Repository context follows as JSON mapping file paths to source text.
Output language: {output_language}.
The "summary" MUST be written entirely in the output language. Do not switch to English or another natural language in the summary. Keep code identifiers, filenames, repository names, commands, and unavoidable technical names unchanged when necessary.
Return ONLY valid JSON with this shape:
{{"summary":"...","changes":[{{"path":"...","action":"create|modify|delete","content":"full file content for create/modify"}}]}}
Rules: only propose concrete source changes needed for the request; never invent test results; preserve unrelated code; use full replacement content; max 8 changed files; never touch .git, secrets, credentials, private keys, or CI workflow files. Delete only when explicitly required by the user request. If no safe change is possible, return an empty changes array.
CONTEXT:
{json.dumps(context, ensure_ascii=False)}'''
    client = genai.Client(api_key=api_key)
    response = await client.aio.models.generate_content(model=model or "gemini-2.5-flash", contents=prompt)
    text = (response.text or "").strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text, count=1).strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentError("Gemini returned invalid JSON") from exc

    if not isinstance(result, dict):
        raise AgentError("Invalid change plan")
    summary = str(result.get("summary", "")).strip()
    changes = result.get("changes", [])
    if not isinstance(changes, list) or len(changes) > MAX_CHANGED_FILES:
        raise AgentError("Invalid change plan")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for change in changes:
        if not isinstance(change, dict):
            raise AgentError("Invalid change entry")
        path = str(change.get("path", "")).replace("\\", "/")
        action = change.get("action")
        if not _safe_path(path):
            raise AgentError(f"Gemini proposed a protected or unsafe path: {path}")
        if path in seen:
            raise AgentError(f"Duplicate change path: {path}")
        if action not in {"create", "modify", "delete"}:
            raise AgentError("Gemini proposed an invalid action")
        if action == "delete":
            normalized.append({"path": path, "action": action})
            seen.add(path)
            continue
        content = change.get("content")
        if not isinstance(content, str):
            raise AgentError(f"Missing content for {path}")
        if len(content) > MAX_FILE_CHARS:
            raise AgentError(f"Generated file is too large: {path}")
        normalized.append({"path": path, "action": action, "content": content})
        seen.add(path)
    return {"summary": summary, "changes": normalized}


async def reconcile_task(repo: GitHubRepo, base: str, request: str, task_id: str) -> dict[str, Any] | None:
    """Recover the latest agent branch state after a worker crash or restart."""
    marker = f"XAI-TASK:{task_id}"
    branch = _branch_name(request, task_id)
    try:
        branch_head = await repo.commit(branch)
    except GitHubRepoError:
        branch_head = None

    if branch_head is not None:
        head_sha = str(branch_head.get("sha") or "")
        head_message = str(((branch_head.get("commit") or {}).get("message") or ""))
        if marker in head_message:
            return {"status": "committed", "summary": "Recovered existing task branch.", "changes": [], "commit": head_sha, "branch": branch}

        # Preserve the original crash-recovery fast-forward case: if the
        # original task commit was created but the branch ref update was lost,
        # attaching it is safe only when its parent is the current branch head.
        marker_commit = await repo.find_task_commit(marker)
        if marker_commit is not None:
            marker_sha = str(marker_commit.get("sha") or "")
            parents = marker_commit.get("parents")
            parent_sha = parents[0].get("sha") if isinstance(parents, list) and parents and isinstance(parents[0], dict) else None
            if marker_sha and parent_sha == head_sha:
                await repo.update_branch(branch, marker_sha)
                return {"status": "committed", "summary": "Recovered existing task commit.", "changes": [], "commit": marker_sha, "branch": branch}

            # A retry commit can be ahead of the original marker. Walk recent
            # commits when the GitHub client supports it and recover the branch
            # head without rewriting history.
            branch_commits = getattr(repo, "branch_commits", None)
            if branch_commits is not None:
                try:
                    commits = await branch_commits(branch, limit=20)
                except Exception:
                    commits = []
                for commit in commits:
                    message = str(((commit.get("commit") or {}).get("message") or ""))
                    if marker in message:
                        return {"status": "committed", "summary": "Recovered existing task branch.", "changes": [], "commit": head_sha, "branch": branch}
        return None

    marker_commit = await repo.find_task_commit(marker)
    if marker_commit is None:
        return None
    marker_sha = str(marker_commit.get("sha") or "")
    if not marker_sha:
        return None
    marker_details = await repo.commit(marker_sha)
    parents = marker_details.get("parents")
    parent_sha = parents[0].get("sha") if isinstance(parents, list) and parents and isinstance(parents[0], dict) else None
    base_details = await repo.commit(base)
    base_sha = str(base_details.get("sha") or "")
    if parent_sha != base_sha:
        return None
    await repo.create_branch(branch, marker_sha)
    return {"status": "committed", "summary": "Recovered existing task commit.", "changes": [], "commit": marker_sha, "branch": branch}


async def execute_task(
    api_key: str,
    model: str,
    repository: str,
    request: str,
    installation_id: int,
    create_pr: bool = True,
    language: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    repo = GitHubRepo(repository, installation_id)
    marker = f"XAI-TASK:{task_id}" if task_id else None
    try:
        metadata = await repo.repo()
        base = metadata.get("default_branch", "main")
        if task_id:
            recovered = await reconcile_task(repo, base, request, task_id)
            if recovered is not None:
                result = recovered
                if create_pr:
                    pr = await repo.pull_request(result["branch"], base, f"XAI Agent: recovered task {task_id[:12]}", f"Recovered automated coding-agent change.\n\nRequest: {request}")
                    result["pull_request"] = {"number": pr.get("number"), "url": pr.get("html_url"), "draft": pr.get("draft", True)}
                return result
        context = await build_context(repo, base)
        plan = await plan_changes(api_key, model, request, context, language)
        if not plan["changes"]:
            return {"status": "no_changes", "summary": plan["summary"], "changes": []}
        branch = _branch_name(request, task_id)
        await repo.create_branch(branch, base)
        commit_message = f"feat(agent): {plan['summary'][:60] or 'apply requested changes'}"
        if marker:
            commit_message = f"{commit_message} [{marker}]"
        sha = await repo.apply_changes(branch, plan["changes"], commit_message, idempotency_marker=marker)
        result: dict[str, Any] = {"status": "committed", "summary": plan["summary"], "changes": [c["path"] for c in plan["changes"]], "commit": sha, "branch": branch}
        if create_pr:
            pr = await repo.pull_request(branch, base, f"XAI Agent: {plan['summary'][:70] or request[:70]}", f"Automated coding-agent change.\n\nRequest: {request}\n\nSummary: {plan['summary']}")
            result["pull_request"] = {"number": pr.get("number"), "url": pr.get("html_url"), "draft": pr.get("draft", True)}
        return result
    finally:
        await repo.aclose()


async def repair_task(
    api_key: str,
    model: str,
    repository: str,
    branch: str,
    request: str,
    validation_failure: str,
    installation_id: int,
    language: str | None = None,
    task_id: str | None = None,
    attempt: int = 1,
) -> dict[str, Any]:
    """Generate and apply one repair commit on the existing agent branch."""
    repo = GitHubRepo(repository, installation_id)
    try:
        context = await build_context(repo, branch)
        repair_request = (
            f"Original user request: {request}\n\n"
            f"Validation attempt {attempt} failed. Fix the implementation so the repository passes validation.\n"
            f"Validation failure:\n{validation_failure[:12000]}\n\n"
            "Inspect the current branch context and make the smallest safe fix. Do not change CI workflow files, secrets, credentials, or private keys."
        )
        plan = await plan_changes(api_key, model, repair_request, context, language)
        if not plan["changes"]:
            raise AgentError("Agent could not produce a repair for the validation failure")
        marker = f"XAI-TASK:{task_id}" if task_id else "XAI-REPAIR"
        message = f"fix(agent): validation retry {attempt} [{marker} RETRY:{attempt}]"
        sha = await repo.apply_changes(branch, plan["changes"], message)
        return {"status": "committed", "summary": plan["summary"], "changes": [c["path"] for c in plan["changes"]], "commit": sha, "branch": branch}
    finally:
        await repo.aclose()
