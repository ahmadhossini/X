from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Plan:
    key: str
    monthly_credits: int
    max_repositories: int
    priority: int
    price_usd: int


PLANS: dict[str, Plan] = {
    "free": Plan("free", monthly_credits=15, max_repositories=1, priority=0, price_usd=0),
    "pro": Plan("pro", monthly_credits=500, max_repositories=10, priority=10, price_usd=12),
    "team": Plan("team", monthly_credits=2000, max_repositories=50, priority=20, price_usd=29),
}
