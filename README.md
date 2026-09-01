# XAI Code Agent

Telegram-first AI coding agent for working with GitHub repositories.

## Architecture

- `bot/` — Telegram interface and bot lifecycle
- `code_agent/` — GitHub integration, AI analysis, and agent API
- `api/` — HTTP API and GitHub webhook entrypoint
- `core/` — shared configuration
- `database/` — persistence models and database session
- `tests/` — automated tests

## Core flow

Telegram → Code Agent → GitHub → repository analysis/changes → tests/CI → report or Pull Request

The repository intentionally contains only the foundation for the coding-agent product. Legacy group management, market data, dashboard, and Mini App code have been removed.
