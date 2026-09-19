from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Plan:
    key: str
    monthly_credits: int
    max_repositories: int
    priority: int


PLANS: dict[str, Plan] = {
    "free": Plan("free", monthly_credits=5, max_repositories=1, priority=0),
    "pro": Plan("pro", monthly_credits=500, max_repositories=10, priority=10),
}
