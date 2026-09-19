from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RepositoryContext:
    repository: str
    files: tuple[str, ...]
    request: str


class ContextEngine:
    """Small, deterministic context boundary; repository retrieval stays in GitHubService."""

    def select(self, repository: str, request: str, files: list[str]) -> RepositoryContext:
        normalized = tuple(dict.fromkeys(path for path in files if path))
        return RepositoryContext(repository=repository, files=normalized, request=request.strip())
