from __future__ import annotations

import asyncio
import re
from typing import Any

from sqlalchemy import select
from telebot import TeleBot
from telebot.types import Message

from bot.locales import t
from code_agent.github import GitHubRepo, GitHubRepoError
from code_agent.github_app import github_app_get
from database.models import GitHubInstallation, User
from database.session import SessionLocal


_COUNT_PATTERNS = (
    "چند فایل", "تعداد فایل", "تعداد فایل‌ها", "تعداد فایل ها",
    "how many files", "number of files", "file count", "count files",
    "कितनी फाइल", "कितनी फ़ाइल", "फाइलों की संख्या",
)
_TREE_PATTERNS = (
    "ساختار مخزن", "ساختار پروژه", "فایل های مخزن", "فایل‌های مخزن",
    "repository structure", "repo structure", "project structure", "list files",
    "لیست فایل", "فهرست فایل", "show files", "show repository",
)
_REPO_INFO_PATTERNS = (
    "اطلاعات مخزن", "مشخصات مخزن", "repo info", "repository info",
    "درباره مخزن", "about repository",
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def _installation(telegram_id: int) -> GitHubInstallation | None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            return None
        return db.scalar(
            select(GitHubInstallation)
            .where(
                GitHubInstallation.user_id == user.id,
                GitHubInstallation.active.is_(True),
            )
            .order_by(GitHubInstallation.updated_at.desc())
        )


def _contains(text: str, patterns: tuple[str, ...]) -> bool:
    value = text.casefold()
    return any(pattern.casefold() in value for pattern in patterns)


def is_read_only_github_query(text: str) -> bool:
    value = text.strip()
    if not value or value.startswith("/"):
        return False
    return _contains(value, _COUNT_PATTERNS + _TREE_PATTERNS + _REPO_INFO_PATTERNS)


def _extract_repo_hint(text: str) -> str | None:
    direct = re.search(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b", text)
    if direct:
        return direct.group(1)
    hint = re.search(r"(?:مخزن|مخزنِ|repo|repository)\s+([A-Za-z0-9_.-]+)", text, re.IGNORECASE)
    return hint.group(1) if hint else None


def _resolve_repo(text: str, repositories: list[dict[str, Any]]) -> dict[str, Any] | None:
    hint = _extract_repo_hint(text)
    if hint:
        normalized = hint.casefold()
        exact = [r for r in repositories if str(r.get("full_name", "")).casefold() == normalized]
        if exact:
            return exact[0]
        by_name = [r for r in repositories if str(r.get("name", "")).casefold() == normalized]
        if len(by_name) == 1:
            return by_name[0]
        return None
    return repositories[0] if len(repositories) == 1 else None


def _repo_list(installation_id: int) -> list[dict[str, Any]]:
    data = _run(github_app_get("/installation/repositories?per_page=100&page=1", installation_id))
    repositories = data.get("repositories", [])
    if not isinstance(repositories, list):
        raise GitHubRepoError("Invalid GitHub installation repository response")
    return [item for item in repositories if isinstance(item, dict) and isinstance(item.get("full_name"), str)]


def _format_tree(tree: dict[str, Any], limit: int = 80) -> tuple[int, str, bool]:
    entries = tree.get("tree", [])
    files = [item.get("path") for item in entries if item.get("type") == "blob" and item.get("path")]
    truncated = bool(tree.get("truncated"))
    shown = files[:limit]
    listing = "\n".join(f"• {path}" for path in shown)
    if len(files) > limit or truncated:
        listing += "\n• ..."
    return len(files), listing, truncated


def handle_read_only_github_query(bot: TeleBot, message: Message, language: str) -> bool:
    text = (message.text or "").strip()
    if not is_read_only_github_query(text):
        return False

    installation = _installation(message.from_user.id) if message.from_user else None
    if not installation:
        bot.reply_to(message, t(language, "connect_first"))
        return True

    try:
        repositories = _repo_list(installation.installation_id)
        selected = _resolve_repo(text, repositories)
        if not selected:
            if len(repositories) > 1:
                names = "\n".join(f"• {item['full_name']}" for item in repositories[:20])
                bot.reply_to(message, f"{t(language, 'repo_selection_needed')}\n\n{names}")
            else:
                bot.reply_to(message, t(language, "repo_not_found"))
            return True

        repository = selected["full_name"]
        default_branch = selected.get("default_branch") or "main"
        repo = GitHubRepo(repository, installation.installation_id)
        try:
            if _contains(text, _REPO_INFO_PATTERNS):
                metadata = _run(repo.repo())
                description = metadata.get("description") or "-"
                branch = metadata.get("default_branch") or default_branch
                stars = metadata.get("stargazers_count", 0)
                bot.reply_to(message, t(language, "repo_info", repository=repository, branch=branch, stars=stars, description=description))
                return True

            tree = _run(repo.tree(default_branch))
            count, listing, truncated = _format_tree(tree)
            if _contains(text, _COUNT_PATTERNS):
                key = "repo_file_count_partial" if truncated else "repo_file_count"
                bot.reply_to(message, t(language, key, repository=repository, count=count))
                return True

            suffix = t(language, "repo_tree_truncated") if truncated else ""
            bot.reply_to(message, t(language, "repo_tree", repository=repository, count=count, listing=listing) + suffix)
            return True
        finally:
            _run(repo.aclose())
    except GitHubRepoError:
        bot.reply_to(message, t(language, "github_error"))
        return True
    except Exception:
        bot.reply_to(message, t(language, "github_error"))
        return True
