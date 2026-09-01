from __future__ import annotations

import json
import re
from typing import Any

from google import genai

from code_agent.github import GitHubRepo


class AgentError(RuntimeError):
    pass


TEXT_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".yml", ".yaml", ".toml", ".txt", ".html", ".css"}


def _safe_path(path: str) -> bool:
    return bool(path) and not path.startswith("/") and ".." not in path.split("/") and not path.startswith(".git/")


async def build_context(repo: GitHubRepo, ref: str, limit: int = 18) -> dict[str, str]:
    tree = await repo.tree(ref)
    files = [x["path"] for x in tree.get("tree", []) if x.get("type") == "blob" and any(x["path"].endswith(ext) for ext in TEXT_EXTENSIONS)]
    files = sorted(files, key=lambda p: (p.count("/"), len(p)))[:limit]
    context: dict[str, str] = {}
    total = 0
    for path in files:
        try:
            content = await repo.file(path, ref)
        except Exception:
            continue
        remaining = 120_000 - total
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
Rules: only propose concrete source changes needed for the request; never invent test results; preserve unrelated code; use full replacement content; max 8 changed files; never touch .git, secrets, credentials, or CI secrets. If no safe change is possible, return an empty changes array.
CONTEXT:
{json.dumps(context, ensure_ascii=False)}'''
    client = genai.Client(api_key=api_key)
    response = await client.aio.models.generate_content(model=model or "gemini-2.5-flash", contents=prompt)
    text = (response.text or "").strip().replace("```json", "").replace("```", "").strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentError("Gemini returned invalid JSON") from exc
    changes = result.get("changes", [])
    if not isinstance(changes, list) or len(changes) > 8:
        raise AgentError("Invalid change plan")
    for change in changes:
        if not isinstance(change, dict) or not _safe_path(str(change.get("path", ""))):
            raise AgentError("Gemini proposed an unsafe path")
        if change.get("action") not in {"create", "modify", "delete"}:
            raise AgentError("Gemini proposed an invalid action")
    return {"summary": str(result.get("summary", "")), "changes": changes}


async def execute_task(api_key: str, model: str, repository: str, request: str, create_pr: bool = True) -> dict[str, Any]:
    repo = GitHubRepo(repository)
    metadata = await repo.repo()
    base = metadata.get("default_branch", "main")
    context = await build_context(repo, base)
    plan = await plan_changes(api_key, model, request, context)
    if not plan["changes"]:
        return {"status": "no_changes", "summary": plan["summary"], "changes": []}
    branch = "xai-agent/" + re.sub(r"[^a-zA-Z0-9._-]+", "-", request.lower()).strip("-")[:45]
    branch = branch.rstrip("-") or "change"
    await repo.create_branch(branch, base)
    sha = await repo.apply_changes(branch, plan["changes"], f"feat(agent): {plan['summary'][:60] or 'apply requested changes'}")
    result: dict[str, Any] = {"status": "committed", "summary": plan["summary"], "changes": [c["path"] for c in plan["changes"]], "commit": sha, "branch": branch}
    if create_pr:
        pr = await repo.pull_request(branch, base, f"XAI Agent: {plan['summary'][:70] or request[:70]}", f"Automated coding-agent change.\n\nRequest: {request}\n\nSummary: {plan['summary']}")
        result["pull_request"] = {"number": pr.get("number"), "url": pr.get("html_url"), "draft": pr.get("draft", True)}
    return result
