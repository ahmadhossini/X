from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Plan:
    key: str
    title: str
    price_usd: Decimal
    duration_days: int
    credits: int
    subscription: bool = True

    @property
    def price_usd_cents(self) -> int:
        return int(self.price_usd * 100)


PLANS = {
    "starter": Plan("starter", "Starter", Decimal("9.99"), 30, 50),
    "pro": Plan("pro", "Pro", Decimal("29.99"), 30, 200),
    "team": Plan("team", "Team", Decimal("79.99"), 30, 600),
    "topup": Plan("topup", "Top-Up", Decimal("4.99"), 0, 20, subscription=False),
}


def get_plan(key: str) -> Plan:
    try:
        return PLANS[key]
    except KeyError as exc:
        raise ValueError("Unknown plan") from exc
