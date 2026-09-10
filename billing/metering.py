from __future__ import annotations

import threading
from dataclasses import dataclass

GEMINI_FLASH_INPUT_USD_PER_1M = 0.30
GEMINI_FLASH_OUTPUT_USD_PER_1M = 2.50

_usage_local = threading.local()


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if min(self.input_tokens, self.output_tokens, self.total_tokens) < 0:
            raise ValueError("Token counts cannot be negative")

    @property
    def normalized_total(self) -> int:
        return self.total_tokens or self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ApiCost:
    input_usd: float
    output_usd: float
    total_usd: float


def gemini_flash_cost(usage: TokenUsage) -> ApiCost:
    input_usd = usage.input_tokens / 1_000_000 * GEMINI_FLASH_INPUT_USD_PER_1M
    output_usd = usage.output_tokens / 1_000_000 * GEMINI_FLASH_OUTPUT_USD_PER_1M
    return ApiCost(round(input_usd, 8), round(output_usd, 8), round(input_usd + output_usd, 8))


def usage_from_response(response: object) -> TokenUsage:
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        usage = TokenUsage()
        _usage_local.last_usage = usage
        return usage

    def _count(name: str) -> int:
        value = getattr(metadata, name, 0)
        return value if isinstance(value, int) and value >= 0 else 0

    usage = TokenUsage(
        input_tokens=_count("prompt_token_count"),
        output_tokens=_count("candidates_token_count"),
        total_tokens=_count("total_token_count"),
    )
    _usage_local.last_usage = usage
    return usage


def consume_last_usage() -> TokenUsage | None:
    usage = getattr(_usage_local, "last_usage", None)
    if hasattr(_usage_local, "last_usage"):
        del _usage_local.last_usage
    return usage
