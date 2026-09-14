# XAI Code Agent

Telegram-first AI coding agent for working with GitHub repositories.

## Product scope

- GitHub repository connection through the GitHub App
- Repository analysis and coding tasks
- File creation and editing
- Bug and error diagnosis
- Changes isolated on a separate branch
- Commit creation and Pull Request workflow
- GitHub Actions, Pull Request, merge-conflict, dependency, and code-review tasks
- Validation before a task is reported as complete
- Telegram Mini App dashboard
- Persian, English, and Hindi support
- TON-only direct USDT billing

## Architecture

- `bot/` — Telegram interface and bot lifecycle
- `code_agent/` — GitHub integration, AI analysis, and agent services
- `api/` — HTTP API, Mini App endpoints, GitHub connection, and webhook entrypoint
- `dashboard/` — Telegram Mini App interface
- `core/` — shared configuration
- `database/` — persistence models and database session
- `billing/` — plans, credits, and TON payment verification
- `tests/` — automated tests

## Core flow

Telegram Mini App → authenticate Telegram user → select repository/task → Code Agent → analyze → fix → test/CI → verify → separate branch → commit → Pull Request → report result

The legacy group-management, generic chat, market-data, and Telegram Stars features are removed. The remaining code is focused on the GitHub coding-agent architecture.
