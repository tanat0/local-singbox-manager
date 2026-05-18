from __future__ import annotations
import re
from typing import Literal

from app.config import settings
from app.logging_config import get_logger
from app.system_clients import SubprocessCommandRunner, SystemServiceClient

HELPER_BIN = settings.system_paths.helper_bin
SINGBOX_BIN = settings.system_paths.singbox_bin

_log = get_logger(__name__)
_runner = SubprocessCommandRunner()
_system = SystemServiceClient(_runner, HELPER_BIN)

LogFilter = Literal["all", "problems", "fatal"]

_PROBLEM_RE = re.compile(r"(warning|error|fatal|failed|invalid|panic|TUNSETIFF)", re.IGNORECASE)
_FATAL_RE = re.compile(r"(error|fatal|failed|invalid|panic|TUNSETIFF)", re.IGNORECASE)


def _filter_log_lines(text: str, mode: LogFilter = "all", grep: str = "") -> str:
    lines = text.splitlines()
    if mode == "problems":
        lines = [line for line in lines if _PROBLEM_RE.search(line)]
    elif mode == "fatal":
        lines = [line for line in lines if _FATAL_RE.search(line)]
    if grep:
        needle = grep.lower()
        lines = [line for line in lines if needle in line.lower()]
    return "\n".join(lines) or "(no matching log output)"


def _run_helper(*args: str, timeout: int = 30) -> tuple[bool, str]:
    if not args:
        return False, "Helper action is required"
    result = _system.helper(args[0], *args[1:], timeout=timeout)
    if not result.ok and result.output.startswith("Command not found"):
        return False, f"Helper not found: {HELPER_BIN}"
    return result.ok, result.output


def get_status() -> dict:
    result = _system.systemctl_show()
    if not result.ok and not result.output:
        return {"active_state": "error", "sub_state": "systemctl show failed", "pid": "0",
                "load_state": "error", "since": ""}
    props: dict[str, str] = {}
    for line in result.output.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()
    return {
        "active_state": props.get("ActiveState", "unknown"),
        "sub_state": props.get("SubState", "unknown"),
        "pid": props.get("MainPID", "0"),
        "load_state": props.get("LoadState", "unknown"),
        "since": props.get("ActiveEnterTimestamp", ""),
    }


def get_logs(lines: int = 100, mode: LogFilter = "all", grep: str = "") -> str:
    result = _system.journal(lines=lines)
    output = result.output or "(no log output)"
    if not result.ok and result.output:
        return f"Error fetching logs: {result.output}"
    return _filter_log_lines(output, mode=mode, grep=grep)


def get_recent_problems(lines: int = 300) -> str:
    return get_logs(lines=lines, mode="problems")


def get_failure_detail(lines: int = 200, since: str = "") -> str:
    result = _system.journal(lines=lines, since=since)
    if not result.output:
        return ""
    output = _filter_log_lines(result.output, mode="fatal")
    if output.startswith("(no matching"):
        return ""
    return output.splitlines()[-1][-500:]


def _log_action(action: str, ok: bool, out: str) -> None:
    if ok:
        _log.info("Service %s: OK", action)
    else:
        _log.warning("Service %s failed: %s", action, out)


def reload() -> tuple[bool, str]:
    """Try systemctl reload (requires ExecReload in unit). Returns (ok, output)."""
    ok, out = _run_helper("reload")
    _log_action("reload", ok, out)
    return ok, out


def restart() -> tuple[bool, str]:
    ok, out = _run_helper("restart")
    _log_action("restart", ok, out)
    return ok, out


def stop() -> tuple[bool, str]:
    ok, out = _run_helper("stop")
    _log_action("stop", ok, out)
    return ok, out


def start() -> tuple[bool, str]:
    ok, out = _run_helper("start")
    _log_action("start", ok, out)
    return ok, out


def reload_or_restart() -> tuple[bool, str]:
    ok, out = _run_helper("reload")
    if ok:
        _log_action("reload", ok, out)
        return ok, out
    ok, out = _run_helper("restart")
    _log_action("restart", ok, out)
    return ok, out


def get_version() -> str:
    """Return sing-box version string, e.g. '1.13.11'. Empty string on failure."""
    try:
        r = _runner.run([SINGBOX_BIN, "version"], timeout=5)
        # Output: "sing-box version 1.13.11\n..."
        m = re.search(r"sing-box version ([\d.]+)", r.output)
        if m:
            return m.group(1)
        return r.output.splitlines()[0].strip() if r.output.splitlines() else ""
    except Exception as exc:
        _log.debug("sing-box version check failed: %s", exc)
        return ""
