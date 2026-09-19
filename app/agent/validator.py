from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidationResult:
    passed: bool
    summary: str


class Validator:
    """Validation policy boundary. Concrete CI/test execution is supplied by workers."""

    def result(self, passed: bool, summary: str) -> ValidationResult:
        return ValidationResult(passed=passed, summary=summary.strip())
