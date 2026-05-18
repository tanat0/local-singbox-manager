from __future__ import annotations
import os
import re
import subprocess
from typing import Literal

from app.logging_config import get_logger

HELPER_BIN = os.environ.get("HELPER_BIN", "/usr/local/bin/singbox-manager-helper")
SINGBOX_BIN = os.environ.get("SINGBOX_BIN", "/usr/bin/sing-box")

_log = get_logger(__name__)

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
    try:
        result = subprocess.run(
            ["sudo", HELPER_BIN, *args],
            capture_output=True, text=True, timeout=timeout,
        )
        out = (result.stdout + result.stderr).strip()
        return result.returncode == 0, out
    except subprocess.TimeoutExpired:
        return False, f"Helper timed out after {timeout}s"
    except FileNotFoundError:
        return False, f"Helper not found: {HELPER_BIN}"
    except Exception as e:
        return False, str(e)


def get_status() -> dict:
    try:
        r = subprocess.run(
            ["systemctl", "show", "sing-box.service", "--no-pager",
             "--property=ActiveState,SubState,MainPID,LoadState,ActiveEnterTimestamp"],
            capture_output=True, text=True, timeout=5,
        )
        props: dict[str, str] = {}
        for line in r.stdout.splitlines():
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
    except Exception as e:
        return {"active_state": "error", "sub_state": str(e), "pid": "0",
                "load_state": "error", "since": ""}


def get_logs(lines: int = 100, mode: LogFilter = "all", grep: str = "") -> str:
    try:
        result = subprocess.run(
            ["journalctl", "-u", "sing-box.service", "-n", str(lines),
             "--no-pager", "--output=short-iso"],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout or "(no log output)"
        return _filter_log_lines(output, mode=mode, grep=grep)
    except Exception as e:
        return f"Error fetching logs: {e}"


def get_recent_problems(lines: int = 300) -> str:
    return get_logs(lines=lines, mode="problems")


def get_failure_detail(lines: int = 200, since: str = "") -> str:
    cmd = ["journalctl", "-u", "sing-box.service", "-n", str(lines), "--no-pager", "--output=short-iso"]
    if since:
        cmd = ["journalctl", "-u", "sing-box.service", "--since", since, "--no-pager", "--output=short-iso"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = _filter_log_lines(result.stdout, mode="fatal")
        if output.startswith("(no matching"):
            return ""
        return output.splitlines()[-1][-500:]
    except Exception:
        return ""


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
        r = subprocess.run(
            [SINGBOX_BIN, "version"],
            capture_output=True, text=True, timeout=5,
        )
        # Output: "sing-box version 1.13.11\n..."
        m = re.search(r"sing-box version ([\d.]+)", r.stdout)
        return m.group(1) if m else r.stdout.splitlines()[0].strip()
    except Exception:
        return ""
