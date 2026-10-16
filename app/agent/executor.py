from __future__ import annotations

from dataclasses import dataclass

from app.agent.planner import AgentPlan


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    plan: AgentPlan
    dry_run: bool = False


class Executor:
    """Safety boundary for code-changing operations."""

    protected_prefixes = (".git/",)

    def prepare(self, plan: AgentPlan, dry_run: bool = False) -> ExecutionRequest:
        return ExecutionRequest(plan=plan, dry_run=dry_run)
