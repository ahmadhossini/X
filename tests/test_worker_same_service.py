from __future__ import annotations

import subprocess

import pytest

from main import start_worker_process, stop_worker_process


class FakeProcess:
    def __init__(self, return_code=None):
        self.return_code = return_code
        self.pid = 1234
        self.terminated = False
        self.killed = False
        self.wait_calls = []

    def poll(self):
        return self.return_code

    def terminate(self):
        self.terminated = True
        self.return_code = 0

    def kill(self):
        self.killed = True
        self.return_code = -9

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if timeout is not None and timeout <= 10 and self.return_code is None:
            raise subprocess.TimeoutExpired("arq", timeout)
        return self.return_code


def test_start_worker_uses_arq_settings_and_checks_startup(monkeypatch):
    process = FakeProcess()
    calls = []

    def fake_popen(command):
        calls.append(command)
        return process

    monkeypatch.setattr("main.subprocess.Popen", fake_popen)
    monkeypatch.setattr("main.time.sleep", lambda _: None)

    assert start_worker_process() is process
    assert calls == [["arq", "app.workers.arq_worker.WorkerSettings"]]


def test_start_worker_fails_if_child_exits_during_startup(monkeypatch):
    process = FakeProcess(return_code=1)
    monkeypatch.setattr("main.subprocess.Popen", lambda command: process)
    monkeypatch.setattr("main.time.sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="ARQ worker exited during startup with code 1"):
        start_worker_process()


def test_stop_worker_terminates_running_child():
    process = FakeProcess()

    stop_worker_process(process)

    assert process.terminated is True
    assert process.killed is False
    assert process.wait_calls == [10]
