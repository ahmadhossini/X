from __future__ import annotations

import base64
import time
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from core.config import settings


class GitHubAppError(RuntimeError):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def app_jwt() -> str:
    if not settings.github_app_id or not settings.github_app_private_key:
        raise GitHubAppError("GitHub App credentials are not configured")
    key = settings.github_app_private_key.replace("\\n", "\n").encode()
    try:
        private_key = serialization.load_pem_private_key(key, password=None)
    except (ValueError, TypeError) as exc:
        raise GitHubAppError("GitHub App private key is invalid") from exc

    now = int(time.time())
    header = _b64url(b'{"alg":"RS256","typ":"JWT"}')
    payload = _b64url((f'{{"iat":{now - 60},"exp":{now + 540},"iss":"{settings.github_app_id}"}}').encode())
    signing_input = f"{header}.{payload}".encode()
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64url(signature)}"


def _github_error(response: httpx.Response, operation: str) -> GitHubAppError:
    detail = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = str(payload.get("message") or "").strip()
    except ValueError:
        pass
    suffix = f": {detail[:300]}" if detail else ""
    return GitHubAppError(f"{operation} failed: HTTP {response.status_code}{suffix}")


async def installation_token(installation_id: int) -> str:
    if not installation_id:
        raise GitHubAppError("GitHub installation is not configured")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {app_jwt()}",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise GitHubAppError(f"GitHub installation token request failed: {type(exc).__name__}") from exc
    if response.is_error:
        raise _github_error(response, "GitHub App installation token")
    try:
        return response.json()["token"]
    except (KeyError, TypeError, ValueError) as exc:
        raise GitHubAppError("GitHub returned an invalid installation token response") from exc


async def github_app_get(path: str, installation_id: int) -> Any:
    token = await installation_token(installation_id)
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"https://api.github.com{path}", headers=headers)
    except httpx.HTTPError as exc:
        raise GitHubAppError(f"GitHub API request failed: {type(exc).__name__}") from exc
    if response.is_error:
        raise _github_error(response, "GitHub API")
    try:
        return response.json()
    except ValueError as exc:
        raise GitHubAppError("GitHub returned invalid JSON") from exc


async def github_app_get_installation(installation_id: int) -> dict[str, Any]:
    if not installation_id:
        raise GitHubAppError("GitHub installation is not configured")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {app_jwt()}",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"https://api.github.com/app/installations/{installation_id}",
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise GitHubAppError(f"GitHub installation lookup request failed: {type(exc).__name__}") from exc
    if response.is_error:
        raise _github_error(response, "GitHub installation lookup")
    try:
        data = response.json()
    except ValueError as exc:
        raise GitHubAppError("GitHub returned invalid installation JSON") from exc
    if not isinstance(data, dict):
        raise GitHubAppError("GitHub returned an invalid installation payload")
    return data
