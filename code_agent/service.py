from __future__ import annotations

import json
import re
from typing import Any

import httpx
from google import genai


class CodeAgentError(RuntimeError):
    pass


async def github_get(token: str, path: str) -> Any:
    if not token:
        raise CodeAgentError("GITHUB_TOKEN is not configured")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"https://api.github.com{path}", headers=headers)
    if response.is_error:
        raise CodeAgentError(f"GitHub API returned {response.status_code}")
    return response.json()


async def analyze_code(api_key: str, model: str, filename: str, content: str) -> dict[str, Any]:
    if not api_key:
        raise CodeAgentError("GEMINI_API_KEY is not configured")
    if not model:
        model = "gemini-2.5-flash"
    client = genai.Client(api_key=api_key)
    prompt = f'''You are XAI Code Agent, a senior software engineer. Analyze this source file.
Return ONLY JSON with keys summary, findings, suggestions.
Do not invent errors or test results.
Filename: {filename}
Source:\n\n{content}\n'''
    response = await client.aio.models.generate_content(model=model, contents=prompt)
    text = (response.text or "").strip()

    # Accept plain JSON as well as JSON wrapped in a markdown code fence.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text, count=1).strip()
    json_str = text

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise CodeAgentError("Gemini returned invalid JSON") from exc
    return {
        "summary": str(data.get("summary", "")),
        "findings": [str(x) for x in data.get("findings", [])],
        "suggestions": [str(x) for x in data.get("suggestions", [])],
    }
