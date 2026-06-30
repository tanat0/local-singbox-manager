from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from app.config import AppSettings, SystemPaths
from app.system_clients import CommandResult


def test_run_ops_checks_all_required_checks_pass():
    module = _load_check_ops()
    runner = _FakeRunner({
        ("sudo", "-n", "/helper", "list-backups"): CommandResult(True, "config_20260630.json", 0),
        ("/sing-box", "version"): CommandResult(True, "sing-box version 1.13.11\n", 0),
        ("systemctl", "is-active", "sing-box.service"): CommandResult(True, "active\n", 0),
        ("systemctl", "is-active", "singbox-manager.service"): CommandResult(True, "active\n", 0),
    })

    checks = module.run_ops_checks(
        _settings(),
        runner,
        exists=_paths_present,
        is_file=lambda path: path != module.SINGBOX_BACKUP_DIR,
        is_dir=lambda path: path == module.SINGBOX_BACKUP_DIR,
        is_executable=lambda path: str(path) in {"/helper", "/sing-box"},
    )

    assert all(check.ok or not check.required for check in checks)
    assert module.print_ops_report
    assert runner.actions == ["list-backups"]


def test_run_ops_checks_uses_only_read_only_helper_action():
    module = _load_check_ops()
    runner = _FakeRunner({
        ("sudo", "-n", "/helper", "list-backups"): CommandResult(True, "", 0),
        ("/sing-box", "version"): CommandResult(True, "sing-box version 1.13.11", 0),
        ("systemctl", "is-active", "sing-box.service"): CommandResult(True, "active", 0),
        ("systemctl", "is-active", "singbox-manager.service"): CommandResult(False, "inactive", 3),
    })

    module.run_ops_checks(
        _settings(),
        runner,
        exists=_paths_present,
        is_file=lambda path: path != module.SINGBOX_BACKUP_DIR,
        is_dir=lambda path: path == module.SINGBOX_BACKUP_DIR,
        is_executable=lambda path: str(path) in {"/helper", "/sing-box"},
    )

    dangerous = {"deploy", "restore", "restart", "start", "stop", "reload"}
    assert dangerous.isdisjoint(runner.actions)


def test_run_ops_checks_reports_helper_missing():
    module = _load_check_ops()
    runner = _FakeRunner({
        ("sudo", "-n", "/helper", "list-backups"): CommandResult(False, "sudo: no such file", 1),
        ("/sing-box", "version"): CommandResult(True, "sing-box version 1.13.11", 0),
        ("systemctl", "is-active", "sing-box.service"): CommandResult(True, "active", 0),
        ("systemctl", "is-active", "singbox-manager.service"): CommandResult(True, "active", 0),
    })

    checks = module.run_ops_checks(
        _settings(),
        runner,
        exists=lambda path: path != Path("/helper"),
        is_file=lambda path: True,
        is_dir=lambda path: True,
        is_executable=lambda path: True,
    )

    helper_check = next(check for check in checks if check.name == "Helper binary")
    sudo_check = next(check for check in checks if check.name == "sudo helper list-backups")
    assert helper_check.ok is False
    assert sudo_check.ok is False
    assert helper_check.required is True


def test_run_ops_checks_treats_manager_service_as_informational():
    module = _load_check_ops()
    runner = _FakeRunner({
        ("sudo", "-n", "/helper", "list-backups"): CommandResult(True, "", 0),
        ("/sing-box", "version"): CommandResult(True, "sing-box version 1.13.11", 0),
        ("systemctl", "is-active", "sing-box.service"): CommandResult(True, "active", 0),
        ("systemctl", "is-active", "singbox-manager.service"): CommandResult(False, "inactive", 3),
    })

    checks = module.run_ops_checks(
        _settings(),
        runner,
        exists=_paths_present,
        is_file=lambda path: path != module.SINGBOX_BACKUP_DIR,
        is_dir=lambda path: path == module.SINGBOX_BACKUP_DIR,
        is_executable=lambda path: str(path) in {"/helper", "/sing-box"},
    )

    manager_check = next(check for check in checks if check.name == "systemd singbox-manager.service")
    assert manager_check.ok is False
    assert manager_check.required is False


def test_load_ops_env_prefers_runtime_env_over_file(tmp_path):
    module = _load_check_ops()
    env_file = tmp_path / ".env"
    env_file.write_text("SINGBOX_BIN=/from-file\nHELPER_BIN='/helper-file'\nSESSION_SECRET=secret\n")

    env = module.load_ops_env(env_file, {"SINGBOX_BIN": "/from-env"})

    assert env["SINGBOX_BIN"] == "/from-env"
    assert env["HELPER_BIN"] == "/helper-file"
    assert "SESSION_SECRET" not in env


def test_safe_path_helpers_treat_permission_errors_as_missing():
    module = _load_check_ops()

    class DeniedPath:
        def exists(self):
            raise PermissionError("denied")

        def is_file(self):
            raise PermissionError("denied")

        def is_dir(self):
            raise PermissionError("denied")

    path = DeniedPath()
    assert module._path_exists(path) is False
    assert module._path_is_file(path) is False
    assert module._path_is_dir(path) is False


def test_optional_path_check_reports_not_readable_or_missing():
    module = _load_check_ops()

    check = module._simple_path_check(
        "Sudoers rule",
        Path("/etc/sudoers.d/singbox-manager"),
        exists=lambda path: False,
        kind_check=lambda path: False,
        required=False,
    )

    assert check.ok is False
    assert check.required is False
    assert check.detail == "not readable or missing: /etc/sudoers.d/singbox-manager"


def _settings() -> AppSettings:
    return AppSettings(system_paths=SystemPaths(singbox_bin="/sing-box", helper_bin="/helper"))


def _paths_present(path: Path) -> bool:
    return str(path) in {
        "/helper",
        "/sing-box",
        "/etc/sing-box/config.json",
        "/etc/sing-box/backups",
        "/etc/sudoers.d/singbox-manager",
    }


def _load_check_ops():
    path = Path(__file__).resolve().parents[1] / "scripts" / "check-ops.py"
    spec = importlib.util.spec_from_file_location("check_ops_script", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeRunner:
    def __init__(self, results):
        self._results = results
        self.calls = []
        self.actions = []

    def run(self, args, timeout=30):
        call = tuple(args)
        self.calls.append((list(args), timeout))
        if len(args) >= 4 and args[:2] == ["sudo", "-n"]:
            self.actions.append(args[3])
        return self._results.get(call, CommandResult(False, f"unexpected command: {list(args)}", 99))
