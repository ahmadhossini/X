from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from google import genai

from code_agent.github import GitHubRepo


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


def _branch_name(request: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", request.lower()).strip("-")[:45].rstrip("-") or "change"
    digest = hashlib.sha256(request.encode("utf-8")).hexdigest()[:8]
    unique = hashlib.sha1(str(time.time_ns()).encode()).hexdigest()[:6]
    return f"xai-agent/{slug}-{digest}-{unique}"


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


async def plan_changes(api_key: str, model: str, request: str, context: dict[str, str]) -> dict[str, Any]:
    if not api_key:
        raise AgentError("GEMINI_API_KEY is not configured")
    prompt = f'''You are XAI Code Agent. Work as a careful senior engineer.
User request: {request}
Repository context follows as JSON mapping file paths to source text.
Return ONLY valid JSON with this shape:
{{"summary":"...","changes":[{{"path":"...","action":"create|modify|delete","content":"full file content for create/modify"}}]}}
Rules: only propose concrete source changes needed for the request; never invent test results; preserve unrelated code; use full replacement content; max 8 changed files; never touch .git, secrets, credentials, private keys, or CI workflow files. Delete only when explicitly required by the user request. If no safe change is possible, return an empty changes array.
CONTEXT:
{json.dumps(context, ensure_ascii=False)}'''
    client = genai.Client(api_key=api_key)
    response = await client.aio.models.generate_content(model=model or "gemini-2.5-flash", contents=prompt)
    text = (response.text or "").strip().replace("```json", "").replace("```", "").strip()
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


async def execute_task(api_key: str, model: str, repository: str, request: str, installation_id: int, create_pr: bool = True) -> dict[str, Any]:
    repo = GitHubRepo(repository, installation_id)
    metadata = await repo.repo()
    base = metadata.get("default_branch", "main")
    context = await build_context(repo, base)
    plan = await plan_changes(api_key, model, request, context)
    if not plan["changes"]:
        return {"status": "no_changes", "summary": plan["summary"], "changes": []}

    branch = _branch_name(request)
    await repo.create_branch(branch, base)
    sha = await repo.apply_changes(branch, plan["changes"], f"feat(agent): {plan['summary'][:60] or 'apply requested changes'}")
    result: dict[str, Any] = {"status": "committed", "summary": plan["summary"], "changes": [c["path"] for c in plan["changes"]], "commit": sha, "branch": branch}
    if create_pr:
        pr = await repo.pull_request(
            branch,
            base,
            f"XAI Agent: {plan['summary'][:70] or request[:70]}",
            f"Automated coding-agent change.\n\nRequest: {request}\n\nSummary: {plan['summary']}",
        )
        result["pull_request"] = {"number": pr.get("number"), "url": pr.get("html_url"), "draft": pr.get("draft", True)}
    return result
