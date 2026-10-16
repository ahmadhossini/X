from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True, slots=True)
class TonPaymentIntent:
    payment_id: str
    amount_nano_ton: int
    destination: str
    memo: str


class TonPaymentService:
    """TON payment adapter. Verification is intentionally separate from invoice creation."""

    def __init__(self, wallet_address: str) -> None:
        self.wallet_address = wallet_address.strip()

    def create_intent(self, payment_id: str, amount_nano_ton: int) -> TonPaymentIntent:
        if not self.wallet_address:
            raise RuntimeError("TON wallet is not configured")
        if amount_nano_ton <= 0:
            raise ValueError("amount_nano_ton must be positive")
        if not payment_id.strip():
            raise ValueError("payment_id is required")
        return TonPaymentIntent(
            payment_id=payment_id,
            amount_nano_ton=amount_nano_ton,
            destination=self.wallet_address,
            memo=payment_id,
        )

    @staticmethod
    def to_transfer_uri(
        destination: str,
        amount_nano_ton: int,
        memo: str,
        network: str = "mainnet",
    ) -> str:
        if not destination.strip():
            raise ValueError("destination is required")
        if amount_nano_ton <= 0:
            raise ValueError("amount_nano_ton must be positive")
        if not memo.strip():
            raise ValueError("memo is required")
        if network not in {"mainnet", "testnet"}:
            raise ValueError("unsupported TON network")
        # ton:// URI is suitable for wallets that support TON transfer links.
        # The network is kept as metadata; wallet behavior is provider-specific.
        return (
            "ton://transfer/"
            f"{quote(destination, safe='')}"
            f"?amount={amount_nano_ton}"
            f"&text={quote(memo, safe='')}"
        )
