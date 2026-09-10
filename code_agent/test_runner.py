from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestResult:
    passed: bool
    command: str
    exit_code: int
    output: str
    timed_out: bool = False


_ALLOWED_COMMANDS = {
    "pytest": ("pytest",),
    "python -m pytest": ("python", "-m", "pytest"),
}


def _command_for(repo: Path) -> tuple[str, ...] | None:
    if (repo / "pytest.ini").exists() or (repo / "pyproject.toml").exists() or (repo / "setup.cfg").exists():
        return _ALLOWED_COMMANDS["python -m pytest"]
    if (repo / "tests").is_dir():
        return _ALLOWED_COMMANDS["python -m pytest"]
    return None


def run_python_tests(repo: Path, timeout_seconds: int = 120) -> TestResult:
    """Run the repository's Python test suite with a strict, non-shell command.

    This deliberately does not execute arbitrary commands supplied by the model/user.
    It is a first safety layer for the coding-agent fix loop.
    """
    command = _command_for(repo)
    if command is None:
        return TestResult(True, "no-tests", 0, "No supported Python test suite detected.")

    timeout_seconds = max(10, min(int(timeout_seconds), 300))
    env = os.environ.copy()
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    })
    try:
        completed = subprocess.run(
            command,
            cwd=repo,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=env,
        )
        output = completed.stdout[-20000:]
        return TestResult(completed.returncode == 0, " ".join(command), completed.returncode, output)
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "")[-20000:] if isinstance(exc.stdout, str) else ""
        return TestResult(False, " ".join(command), -1, output, timed_out=True)


def run_tests_in_temp_copy(files: dict[str, str], timeout_seconds: int = 120) -> TestResult:
    """Materialize text files into an isolated temporary directory and run tests."""
    with tempfile.TemporaryDirectory(prefix="xai-agent-test-") as tmp:
        root = Path(tmp).resolve()
        for relative, content in files.items():
            target = (root / relative).resolve()
            if root not in target.parents and target != root:
                raise ValueError(f"unsafe test path: {relative}")
            if target.name == ".env" or ".git" in target.parts:
                raise ValueError(f"blocked test path: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return run_python_tests(root, timeout_seconds=timeout_seconds)
