from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_miniapp_order_details_requires_telegram_authentication():
    text = (ROOT / "api" / "miniapp_billing.py").read_text(encoding="utf-8")
    assert 'def order_details(' in text
    assert 'authorization: str | None = Header(default=None)' in text
    assert 'x_telegram_init_data: str | None = Header(default=None)' in text
    assert '_require_user(authorization, x_telegram_init_data)' in text
    assert 'get_usdt_order(order_id, telegram_id=user.telegram_id)' in text


def test_ton_transfer_query_has_bounded_time_window():
    text = (ROOT / "billing" / "ton.py").read_text(encoding="utf-8")
    assert '"start_utime": max(0, created_at - 120)' in text
    assert '"end_utime": min(now, created_at + expiry)' in text
    assert 'transfer_time < created_at - 120' in text
    assert 'transfer_time > created_at + expiry' in text


def test_ton_transfer_match_requires_exact_integer_amount_and_comment():
    text = (ROOT / "billing" / "ton.py").read_text(encoding="utf-8")
    assert 'transfer_amount = int(transfer.get("amount"))' in text
    assert 'if transfer_amount != amount_units:' in text
    assert 'if _transfer_comment(transfer) != comment:' in text
