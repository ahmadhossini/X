from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class Event:
    topic: str
    payload: dict[str, Any]


class EventBus:
    """Redis-backed event bus used to decouple webhooks from heavy workers."""

    def __init__(self, redis: Redis, stream: str = "xai:events") -> None:
        self.redis = redis
        self.stream = stream

    async def publish(self, event: Event) -> str:
        fields = {
            "topic": event.topic,
            "payload": json.dumps(event.payload, separators=(",", ":")),
        }
        result = await self.redis.xadd(self.stream, fields, maxlen=100_000, approximate=True)
        return result.decode() if isinstance(result, bytes) else str(result)
