from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentPlan:
    task_type: str
    repository: str
    request: str


class Planner:
    def plan(self, repository: str, request: str) -> AgentPlan:
        text = request.lower()
        if any(token in text for token in ("pull request", "pr review", "review pr")):
            task_type = "code_review"
        elif any(token in text for token in ("github actions", "workflow", "ci", "build")):
            task_type = "ci_fix"
        elif any(token in text for token in ("dependency", "package", "requirements")):
            task_type = "dependency_fix"
        else:
            task_type = "code_change"
        return AgentPlan(task_type=task_type, repository=repository, request=request.strip())
