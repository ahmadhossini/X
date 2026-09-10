from pathlib import Path

from code_agent.test_runner import run_python_tests, run_tests_in_temp_copy


def test_temp_copy_runs_passing_tests():
    result = run_tests_in_temp_copy({
        "tests/test_sample.py": "def test_ok():\n    assert 2 + 2 == 4\n",
    })
    assert result.passed is True
    assert result.exit_code == 0


def test_temp_copy_reports_failure():
    result = run_tests_in_temp_copy({
        "tests/test_sample.py": "def test_bad():\n    assert 2 + 2 == 5\n",
    })
    assert result.passed is False
    assert result.exit_code != 0


def test_no_tests_is_safe(tmp_path: Path):
    result = run_python_tests(tmp_path)
    assert result.passed is True
    assert result.command == "no-tests"
