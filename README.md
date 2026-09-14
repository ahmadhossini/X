# XAI Code Agent

Telegram-first AI coding agent for working with GitHub repositories.

## Architecture

- `bot/` — Telegram interface, billing entrypoints, and task worker
- `code_agent/` — GitHub App integration, AI planning, repository changes, branches, and pull requests
- `api/` — HTTP API, Telegram Mini App, GitHub connection, webhook, and TON checkout
- `dashboard/` — Telegram Mini App frontend
- `billing/` — plans, credit accounting, and TON/USDT verification
- `core/` — shared configuration
- `database/` — persistence models and database session/migrations
- `tests/` — automated regression and billing/security tests

## Core flow

Telegram Mini App or bot → authenticate Telegram user → connect GitHub App → select an installed repository → reserve credits → analyze repository with Gemini → create a dedicated XAI Agent branch → apply the requested changes → commit → open a draft Pull Request → report the result to Telegram.

## Safety boundaries

The agent rejects unsafe paths, secrets, private keys, `.git` content, and GitHub Actions workflow changes. Repository access is revalidated through the GitHub App installation before a task is charged and before repository operations are performed.

Billing currently uses USDT on TON. Telegram Stars are not part of the current billing flow.
