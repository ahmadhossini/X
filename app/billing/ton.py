from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TonPaymentIntent:
    payment_id: str
    amount_nano_ton: int
    destination: str
    memo: str


class TonPaymentService:
    """Payment adapter boundary. Blockchain verification stays outside Telegram handlers."""

    def __init__(self, wallet_address: str) -> None:
        self.wallet_address = wallet_address

    def create_intent(self, payment_id: str, amount_nano_ton: int) -> TonPaymentIntent:
        if not self.wallet_address:
            raise RuntimeError("TON wallet is not configured")
        if amount_nano_ton <= 0:
            raise ValueError("amount_nano_ton must be positive")
        return TonPaymentIntent(payment_id, amount_nano_ton, self.wallet_address, payment_id)
