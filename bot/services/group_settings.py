"""Compatibility facade for the canonical GroupSettingsStore.

All runtime code should use bot.services.group_settings_store. This module
remains only so older imports do not silently create a second configuration
format with different field names.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from bot.services.group_settings_store import GroupSettings, store


def get_group_settings(chat_id: int) -> dict[str, Any]:
    return asdict(store.get(chat_id))


def set_group_setting(chat_id: int, key: str, enabled: bool) -> dict[str, Any]:
    return asdict(store.set(chat_id, key, enabled))


DEFAULTS = asdict(GroupSettings())
