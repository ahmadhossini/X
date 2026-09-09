from __future__ import annotations

import asyncio
import base64
import json
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
    try:
        private_key = serialization.load_pem_private_key(key, password=None)
    except (ValueError, TypeError) as exc:
        raise GitHubAppError("GitHub App private key is invalid") from exc
    now = int(time.time())
    header = _b64url(b'{"alg":"RS256","typ":"JWT"}')
    payload = _b64url(
        json.dumps(
            {"iat": now - 60, "exp": now + 540, "iss": settings.github_app_id},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64url(signature)}"


def invalidate_installation_token(installation_id: int) -> None:
    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE.pop(installation_id, None)


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return min(max(float(value), 0.0), 10.0)
            except (TypeError, ValueError):
                pass
    return min(2**attempt, 8) + 0.25 * (attempt + 1)


async def _request(method: str, url: str, **kwargs: Any) -> httpx.Response:
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        for attempt in range(4):
            response: httpx.Response | None = None
            try:
                response = await client.request(method, url, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 3:
                        await asyncio.sleep(_retry_delay(response, attempt))
                        continue
                return response
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt >= 3:
                    break
                await asyncio.sleep(_retry_delay(response, attempt))
    raise GitHubAppError(f"GitHub network error: {last_error}") from last_error


async def installation_token(installation_id: int, force_refresh: bool = False) -> str:
    if not installation_id:
        raise GitHubAppError("GitHub installation is not configured")

    if not force_refresh:
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
    response = await _request(
        "POST",
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers=headers,
    )
    if response.is_error:
        detail = response.text[:500].replace("\n", " ")
        raise GitHubAppError(f"GitHub App installation token failed: {response.status_code}: {detail}")
    try:
        token = response.json()["token"]
    except (ValueError, KeyError, TypeError) as exc:
        raise GitHubAppError("GitHub returned an invalid installation token response") from exc

    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE[installation_id] = (token, time.time() + _TOKEN_CACHE_TTL)
    return token


async def github_app_get(path: str, installation_id: int) -> Any:
    for attempt in range(2):
        token = await installation_token(installation_id, force_refresh=attempt == 1)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {token}",
        }
        response = await _request("GET", f"https://api.github.com{path}", headers=headers)
        if response.status_code == 401 and attempt == 0:
            invalidate_installation_token(installation_id)
            continue
        if response.is_error:
            detail = response.text[:500].replace("\n", " ")
            raise GitHubAppError(f"GitHub API returned {response.status_code}: {detail}")
        try:
            return response.json()
        except ValueError as exc:
            raise GitHubAppError("GitHub returned invalid JSON") from exc
    raise GitHubAppError("GitHub API authentication failed after token refresh")


async def github_app_get_installation(installation_id: int) -> dict[str, Any]:
    if not installation_id:
        raise GitHubAppError("GitHub installation is not configured")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {app_jwt()}",
    }
    response = await _request(
        "GET",
        f"https://api.github.com/app/installations/{installation_id}",
        headers=headers,
    )
    if response.is_error:
        detail = response.text[:500].replace("\n", " ")
        raise GitHubAppError(f"GitHub installation lookup failed: {response.status_code}: {detail}")
    try:
        return response.json()
    except ValueError as exc:
        raise GitHubAppError("GitHub returned invalid JSON") from exc
