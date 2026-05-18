from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    output: str
    returncode: Optional[int] = None


class CommandRunner:
    def run(self, args: Sequence[str], timeout: int = 30) -> CommandResult:
        raise NotImplementedError


class SubprocessCommandRunner(CommandRunner):
    def run(self, args: Sequence[str], timeout: int = 30) -> CommandResult:
        try:
            result = subprocess.run(
                list(args),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (result.stdout + result.stderr).strip()
            return CommandResult(result.returncode == 0, output, result.returncode)
        except subprocess.TimeoutExpired:
            return CommandResult(False, f"Command timed out after {timeout}s")
        except FileNotFoundError:
            executable = args[0] if args else "<empty>"
            return CommandResult(False, f"Command not found: {executable}")
        except OSError as exc:
            return CommandResult(False, str(exc))


class SystemServiceClient:
    def __init__(self, runner: CommandRunner, helper_bin: str, unit: str = "sing-box.service") -> None:
        self._runner = runner
        self._helper_bin = helper_bin
        self._unit = unit

    def helper(self, action: str, *args: str, timeout: int = 30) -> CommandResult:
        return self._runner.run(["sudo", self._helper_bin, action, *args], timeout=timeout)

    def systemctl_show(self) -> CommandResult:
        props = "ActiveState,SubState,MainPID,LoadState,ActiveEnterTimestamp"
        return self._runner.run([
            "systemctl",
            "show",
            self._unit,
            "--no-pager",
            f"--property={props}",
        ], timeout=5)

    def is_active(self) -> bool:
        result = self._runner.run(["systemctl", "is-active", self._unit], timeout=5)
        return result.output.strip() == "active"

    def journal(self, lines: int = 100, since: str = "") -> CommandResult:
        cmd: List[str]
        if since:
            cmd = ["journalctl", "-u", self._unit, "--since", since, "--no-pager", "--output=short-iso"]
        else:
            cmd = ["journalctl", "-u", self._unit, "-n", str(lines), "--no-pager", "--output=short-iso"]
        return self._runner.run(cmd, timeout=10)
