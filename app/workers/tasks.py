from __future__ import annotations

from typing import Any


async def process_github_event(ctx: dict[str, Any], payload: dict[str, Any]) -> None:
    """Worker entry point for GitHub events. Keep heavy work out of webhook requests."""
    # Agent/GitHub execution is deliberately delegated to existing code_agent components
    # until the V2 executor is migrated; this boundary prevents new coupling.
    return None
