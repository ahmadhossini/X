from __future__ import annotations

import base64
import threading
import time
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from core.config import settings


class GitHubAppError(RuntimeError):
    pass


_TOKEN_CACHE: dict[int, tuple[str, float]] = {}
_TOKEN_CACHE_LOCK = threading.Lock()
_TOKEN_CACHE_TTL = 45 * 60


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def app_jwt() -> str:
    if not settings.github_app_id or not settings.github_app_private_key:
        raise GitHubAppError("GitHub App credentials are not configured")
    key = settings.github_app_private_key.replace("\\n", "\n").encode()
    private_key = serialization.load_pem_private_key(key, password=None)
    now = int(time.time())
    header = _b64url(b'{"alg":"RS256","typ":"JWT"}')
    payload = _b64url((f'{"iat":{now - 60},"exp":{now + 540},"iss":"{settings.github_app_id}"}').encode())
    signing_input = f"{header}.{payload}".encode()
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64url(signature)}"


async def installation_token(installation_id: int) -> str:
    if not installation_id:
        raise GitHubAppError("GitHub installation is not configured")

    now = time.time()
    with _TOKEN_CACHE_LOCK:
        cached = _TOKEN_CACHE.get(installation_id)
        if cached and cached[1] > now:
            return cached[0]

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {app_jwt()}",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers=headers,
        )
    if response.is_error:
        raise GitHubAppError(f"GitHub App installation token failed: {response.status_code}")

    token = response.json()["token"]
    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE[installation_id] = (token, time.time() + _TOKEN_CACHE_TTL)
    return token


async def github_app_get(path: str, installation_id: int) -> Any:
    token = await installation_token(installation_id)
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"https://api.github.com{path}", headers=headers)
    if response.is_error:
        raise GitHubAppError(f"GitHub API returned {response.status_code}")
    return response.json()


async def github_app_get_installation(installation_id: int) -> dict[str, Any]:
    if not installation_id:
        raise GitHubAppError("GitHub installation is not configured")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {app_jwt()}",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"https://api.github.com/app/installations/{installation_id}",
            headers=headers,
        )
    if response.is_error:
        raise GitHubAppError(f"GitHub installation lookup failed: {response.status_code}")
    return response.json()
