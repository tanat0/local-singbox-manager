from __future__ import annotations
import os
import re
import subprocess

HELPER_BIN = os.environ.get("HELPER_BIN", "/usr/local/bin/singbox-manager-helper")
SINGBOX_BIN = os.environ.get("SINGBOX_BIN", "/usr/bin/sing-box")


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


def get_logs(lines: int = 100) -> str:
    try:
        result = subprocess.run(
            ["journalctl", "-u", "sing-box.service", "-n", str(lines),
             "--no-pager", "--output=short-iso"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout or "(no log output)"
    except Exception as e:
        return f"Error fetching logs: {e}"


def reload() -> tuple[bool, str]:
    """Try systemctl reload (requires ExecReload in unit). Returns (ok, output)."""
    return _run_helper("reload")


def restart() -> tuple[bool, str]:
    return _run_helper("restart")


def stop() -> tuple[bool, str]:
    return _run_helper("stop")


def start() -> tuple[bool, str]:
    return _run_helper("start")


def reload_or_restart() -> tuple[bool, str]:
    ok, out = reload()
    if ok:
        return ok, out
    return restart()


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
