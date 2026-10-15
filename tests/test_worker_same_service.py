from __future__ import annotations

import subprocess

import pytest

import main
from main import run_worker_supervisor, start_worker_process, stop_worker_process


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



def test_worker_supervisor_restarts_exited_arq_process(monkeypatch):
    class StopAfterWait:
        def __init__(self):
            self.calls = 0
            self.stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, timeout=None):
            self.calls += 1
            if self.calls >= 3:
                self.stopped = True
                return True
            return False

    initial = FakeProcess(return_code=1)
    replacement = FakeProcess()
    stop_event = StopAfterWait()
    starts = []

    def fake_start_worker_process():
        starts.append(True)
        return replacement

    monkeypatch.setattr(main, "_stop_event", stop_event)
    monkeypatch.setattr(main, "start_worker_process", fake_start_worker_process)
    monkeypatch.setattr(main, "_worker_process", initial)

    run_worker_supervisor(initial)

    assert starts == [True]
    assert main._worker_process is replacement
