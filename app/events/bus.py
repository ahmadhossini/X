from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class Event:
    topic: str
    payload: dict[str, Any]


class EventBus:
    """Small Redis-backed event bus used to decouple webhooks from workers."""

    def __init__(self, redis: Redis, stream: str = "xai:events") -> None:
        self.redis = redis
        self.stream = stream

    async def publish(self, event: Event) -> str:
        fields = {"topic": event.topic, "payload": __import__("json").dumps(event.payload, separators=(",", ":"))}
        result = await self.redis.xadd(self.stream, fields, maxlen=100_000, approximate=True)
        return result.decode() if isinstance(result, bytes) else str(result)
