# XAI Code Agent

Telegram-first AI coding agent for working with GitHub repositories.

## Architecture

- `bot/` — Telegram interface and bot lifecycle
- `code_agent/` — GitHub integration, AI analysis, and agent execution
- `api/` — HTTP API, GitHub webhooks, Mini App, and payments
- `app/billing/` — plans, subscriptions, TON payment intents, and blockchain verification
- `core/` — shared configuration
- `database/` — persistence models and database session
- `dashboard/` — Telegram Mini App
- `tests/` — automated tests

## Core flow

Telegram → Mini App → Code Agent → GitHub → repository analysis/changes → tests/CI → report or Pull Request

## TON Pro subscription

1. The user selects Pro in the Mini App.
2. The backend creates a unique payment intent with a unique memo.
3. The Mini App opens the TON transfer URI in the user's wallet.
4. The backend checks Toncenter for an exact incoming amount and exact payment memo.
5. Only a blockchain-verified transfer can confirm the payment.
6. The payment is marked confirmed and the Pro subscription is activated for 30 days.
7. Repeated verification is idempotent and an already-used transaction cannot activate another payment.

Required deployment variables:

- `TON_WALLET_ADDRESS`
- `TON_PRO_PRICE_NANO_TON`
- `TON_NETWORK=mainnet`
- `TONCENTER_API_KEY` (or `TON_API_KEY`)

The Toncenter API key is used only by the backend for blockchain verification. Wallet private keys are never stored by XAI Code Agent.

The repository intentionally keeps the coding-agent product separate from legacy Telegram group-management functionality.
