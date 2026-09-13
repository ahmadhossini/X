from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    key: str
    title: str
    price_usd: int
    duration_days: int
    credits: int


PLANS = {
    "pro_monthly": Plan("pro_monthly", "Pro 1 Month", 10, 30, 100),
    "pro_quarterly": Plan("pro_quarterly", "Pro 3 Months", 20, 90, 350),
}


def get_plan(key: str) -> Plan:
    try:
        return PLANS[key]
    except KeyError as exc:
        raise ValueError("Unknown plan") from exc
