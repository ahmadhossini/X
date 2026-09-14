import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_telegram_stars_are_not_present_in_payment_code():
    payment_files = [
        ROOT / "api" / "miniapp_billing.py",
        ROOT / "api" / "payments.py",
        ROOT / "billing" / "payments.py",
        ROOT / "billing" / "ton.py",
        ROOT / "bot" / "payments.py",
        ROOT / "bot" / "main.py",
        ROOT / "dashboard" / "app.js",
    ]
    for path in payment_files:
        text = path.read_text(encoding="utf-8").lower()
        assert "telegram stars" not in text
        assert not re.search(r"\bxtr\b", text)
        assert "/stars" not in text


def test_stars_billing_module_is_removed():
    assert not (ROOT / "billing" / "stars.py").exists()
