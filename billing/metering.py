from __future__ import annotations

import threading
from dataclasses import dataclass

# Gemini 2.5 Flash standard pricing, USD per 1M tokens.
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
    return ApiCost(
        input_usd=round(input_usd, 8),
        output_usd=round(output_usd, 8),
        total_usd=round(input_usd + output_usd, 8),
    )


def usage_from_response(response: object) -> TokenUsage:
    """Read Google GenAI usage metadata and keep it available to the current task thread."""
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        usage = TokenUsage()
        _usage_local.last_usage = usage
        return usage

    def _count(*names: str) -> int:
        for name in names:
            value = getattr(metadata, name, None)
            if isinstance(value, int) and value >= 0:
                return value
        return 0

    input_tokens = _count("prompt_token_count", "prompt_tokens_details")
    output_tokens = _count("candidates_token_count")
    total_tokens = _count("total_token_count")
    usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens)
    _usage_local.last_usage = usage
    return usage


def consume_last_usage() -> TokenUsage | None:
    """Return and clear usage captured by the current worker thread."""
    usage = getattr(_usage_local, "last_usage", None)
    if hasattr(_usage_local, "last_usage"):
        del _usage_local.last_usage
    return usage
