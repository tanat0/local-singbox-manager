#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import AppSettings, load_settings
from app.system_clients import CommandResult, CommandRunner, SubprocessCommandRunner

CONFIG_KEYS = (
    "DATABASE_URL",
    "SINGBOX_BIN",
    "HELPER_BIN",
)
SINGBOX_CONFIG_PATH = Path("/etc/sing-box/config.json")
SINGBOX_BACKUP_DIR = Path("/etc/sing-box/backups")
SUDOERS_PATH = Path("/etc/sudoers.d/singbox-manager")


@dataclass(frozen=True)
class OpsCheck:
    name: str
    ok: bool
    detail: str
    required: bool = True


PathPredicate = Callable[[Path], bool]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only operational checks for Sing-Box Manager.")
    parser.add_argument("--env-file", default=".env", help="Environment file to read before process env.")
    args = parser.parse_args()

    env = load_ops_env(Path(args.env_file))
    settings = load_settings(env)
    checks = run_ops_checks(settings, SubprocessCommandRunner())
    print_ops_report(checks)
    return 0 if all(check.ok or not check.required for check in checks) else 1


def load_ops_env(env_file: Path, env: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    source = parse_env_file(env_file)
    runtime_env = os.environ if env is None else env
    for key in CONFIG_KEYS:
        if key in runtime_env:
            source[key] = runtime_env[key]
    return source


def parse_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in CONFIG_KEYS:
            values[key] = _strip_quotes(value.strip())
    return values


def run_ops_checks(
    settings: AppSettings,
    runner: CommandRunner,
    *,
    exists: Optional[PathPredicate] = None,
    is_file: Optional[PathPredicate] = None,
    is_dir: Optional[PathPredicate] = None,
    is_executable: Optional[PathPredicate] = None,
) -> list[OpsCheck]:
    exists = exists or _path_exists
    is_file = is_file or _path_is_file
    is_dir = is_dir or _path_is_dir
    executable = is_executable or _is_executable
    helper = Path(settings.system_paths.helper_bin)
    singbox = Path(settings.system_paths.singbox_bin)

    return [
        _path_check("Helper binary", helper, exists, is_file, executable, executable_required=True),
        _sudo_helper_check(settings.system_paths.helper_bin, runner),
        _singbox_version_check(settings.system_paths.singbox_bin, runner),
        _systemd_active_check("sing-box.service", runner, required=True),
        _systemd_active_check("singbox-manager.service", runner, required=False),
        _simple_path_check("Deployed config", SINGBOX_CONFIG_PATH, exists, is_file, required=False),
        _simple_path_check("Backup directory", SINGBOX_BACKUP_DIR, exists, is_dir, required=False),
        _simple_path_check("Sudoers rule", SUDOERS_PATH, exists, is_file, required=False),
        _path_check("sing-box binary", singbox, exists, is_file, executable, executable_required=True),
    ]


def print_ops_report(checks: list[OpsCheck]) -> None:
    print("Operations smoke check:")
    for check in checks:
        status = "OK" if check.ok else ("WARN" if not check.required else "FAIL")
        print(f"  [{status}] {check.name}: {check.detail}")


def _path_check(
    name: str,
    path: Path,
    exists: PathPredicate,
    is_file: PathPredicate,
    is_executable: PathPredicate,
    *,
    executable_required: bool,
) -> OpsCheck:
    if not exists(path):
        return OpsCheck(name, False, f"missing: {path}")
    if not is_file(path):
        return OpsCheck(name, False, f"not a file: {path}")
    if executable_required and not is_executable(path):
        return OpsCheck(name, False, f"not executable: {path}")
    return OpsCheck(name, True, str(path))


def _simple_path_check(
    name: str,
    path: Path,
    exists: PathPredicate,
    kind_check: PathPredicate,
    *,
    required: bool,
) -> OpsCheck:
    if not exists(path):
        detail = f"missing: {path}" if required else f"not readable or missing: {path}"
        return OpsCheck(name, False, detail, required=required)
    if not kind_check(path):
        return OpsCheck(name, False, f"unexpected file type: {path}", required=required)
    return OpsCheck(name, True, str(path), required=required)


def _sudo_helper_check(helper_bin: str, runner: CommandRunner) -> OpsCheck:
    result = runner.run(["sudo", "-n", helper_bin, "list-backups"], timeout=10)
    if result.ok:
        return OpsCheck("sudo helper list-backups", True, "read-only helper probe succeeded")
    return OpsCheck("sudo helper list-backups", False, _short_output(result))


def _singbox_version_check(singbox_bin: str, runner: CommandRunner) -> OpsCheck:
    result = runner.run([singbox_bin, "version"], timeout=5)
    if result.ok:
        first_line = result.output.splitlines()[0] if result.output else "version command succeeded"
        return OpsCheck("sing-box version", True, first_line)
    return OpsCheck("sing-box version", False, _short_output(result))


def _systemd_active_check(unit: str, runner: CommandRunner, *, required: bool) -> OpsCheck:
    result = runner.run(["systemctl", "is-active", unit], timeout=5)
    output = result.output.strip() or f"exit {result.returncode}"
    return OpsCheck(f"systemd {unit}", output == "active", output, required=required)


def _is_executable(path: Path) -> bool:
    try:
        return os.access(path, os.X_OK)
    except OSError:
        return False


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _path_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _path_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _short_output(result: CommandResult) -> str:
    text = result.output.strip() or f"exit {result.returncode}"
    return text[:300]


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
