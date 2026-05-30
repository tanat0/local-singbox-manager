"""
E2E test infrastructure.

Starts a real uvicorn server on 127.0.0.1:19090 with:
  - isolated SQLite in a temp file
  - all system/helper calls mocked (no sing-box, no sudo, no journalctl)
  - Alembic migrations run against temp DB on startup
"""
from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
from unittest.mock import patch

import pytest

# ── 1. Temp DB — must be set BEFORE any app import ──────────────────────────
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

# ── 2. Mock all privileged / external system calls ──────────────────────────

def _mock_helper(*args, timeout=30):
    action = args[0] if args else ""
    if action == "deploy":
        return True, "Config written. Backup: config_20240101_120000.json"
    if action in ("reload", "restart", "start", "stop"):
        return True, f"sing-box {action} OK"
    if action == "list-backups":
        return True, json.dumps(["config_20240101_120000.json"])
    if action == "restore":
        return True, "Restored OK"
    return True, "OK"

def _mock_status():
    return {
        "active_state": "active", "sub_state": "running",
        "pid": "42", "load_state": "loaded",
        "since": "Mon 2024-01-01 12:00:00 UTC",
    }

def _mock_logs(lines=100, mode="all", grep=""):
    return "Jan 01 12:00:00 sing-box[42]: INFO sing-box started\n"

def _mock_validate(config):
    return True, "Configuration is valid"

def _mock_version():
    return "1.13.11"

_patches = [
    patch("app.singbox.deployer._run_helper", side_effect=_mock_helper),
    patch("app.singbox.service._run_helper", side_effect=_mock_helper),
    patch("app.singbox.deployer._service_is_active", return_value=True),
    patch("app.singbox.deployer.validate_config", side_effect=_mock_validate),
    patch("app.services.dashboard.validate_config", side_effect=_mock_validate),
    patch("app.singbox.service.get_status", side_effect=_mock_status),
    patch("app.singbox.service.get_logs", side_effect=_mock_logs),
    patch("app.singbox.service.get_version", side_effect=_mock_version),
    patch("app.health.subprocess.run", return_value=type("R", (), {"returncode": 0, "stdout": "state UP\n"})()),
]
for _p in _patches:
    _p.start()

# ── 3. Import app AFTER env + patches are in place ──────────────────────────
import uvicorn  # noqa: E402

from app.main import app  # noqa: E402  (triggers _run_migrations on import)

# ── 4. Server lifecycle ──────────────────────────────────────────────────────
_PORT = 19090
_server = uvicorn.Server(uvicorn.Config(
    app, host="127.0.0.1", port=_PORT,
    log_level="error", loop="asyncio",
))
_thread = threading.Thread(target=_server.run, daemon=True)


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"Server on {host}:{port} did not start within {timeout}s")


@pytest.fixture(scope="session", autouse=True)
def _live_server():
    _thread.start()
    _wait_for_port("127.0.0.1", _PORT)
    yield
    _server.should_exit = True
    _thread.join(timeout=5)
    # Clean up temp DB
    try:
        os.unlink(_db_path)
    except OSError:
        pass


@pytest.fixture(scope="session")
def base_url():
    return f"http://127.0.0.1:{_PORT}"
