from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from app.system_clients import CommandResult, SubprocessCommandRunner, SystemServiceClient


def test_subprocess_runner_merges_stdout_and_stderr():
    proc = MagicMock(returncode=1, stdout="out\n", stderr="err\n")

    with patch("app.system_clients.subprocess.run", return_value=proc):
        result = SubprocessCommandRunner().run(["cmd"], timeout=3)

    assert result.ok is False
    assert result.returncode == 1
    assert result.output == "out\nerr"


def test_subprocess_runner_maps_timeout():
    with patch("app.system_clients.subprocess.run", side_effect=subprocess.TimeoutExpired(["cmd"], 7)):
        result = SubprocessCommandRunner().run(["cmd"], timeout=7)

    assert result.ok is False
    assert result.output == "Command timed out after 7s"


def test_subprocess_runner_maps_missing_binary():
    with patch("app.system_clients.subprocess.run", side_effect=FileNotFoundError):
        result = SubprocessCommandRunner().run(["missing"], timeout=1)

    assert result.ok is False
    assert result.output == "Command not found: missing"


def test_system_service_client_builds_helper_command():
    runner = _FakeRunner(CommandResult(True, "ok", 0))
    client = SystemServiceClient(runner, "/opt/helper")

    result = client.helper("restart", timeout=9)

    assert result.ok is True
    assert runner.calls == [(["sudo", "/opt/helper", "restart"], 9)]


def test_system_service_client_is_active_checks_text_output():
    assert SystemServiceClient(_FakeRunner(CommandResult(True, "active\n", 0)), "/h").is_active() is True
    assert SystemServiceClient(_FakeRunner(CommandResult(False, "inactive\n", 3)), "/h").is_active() is False


class _FakeRunner:
    def __init__(self, result: CommandResult) -> None:
        self._result = result
        self.calls = []

    def run(self, args, timeout=30):
        self.calls.append((list(args), timeout))
        return self._result
