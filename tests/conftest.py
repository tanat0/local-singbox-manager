from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx


def _is_e2e_target_arg(arg: str) -> bool:
    if arg.startswith("--"):
        return False

    normalized = arg.rstrip("/")
    return (
        normalized == "tests/e2e"
        or normalized.endswith("/tests/e2e")
        or normalized.startswith("tests/e2e/")
        or "/tests/e2e/" in normalized
    )


_IS_E2E_RUN = any(_is_e2e_target_arg(arg) for arg in sys.argv[1:])


if not _IS_E2E_RUN:
    _db_fd, _db_path = tempfile.mkstemp(suffix=".db")
    os.close(_db_fd)
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{_db_path}")
    os.environ.setdefault("MIGRATIONS_ENABLED", "0")
    os.environ.setdefault("BACKGROUND_TASKS_ENABLED", "0")
    os.environ.setdefault("HEALTH_CHECK_INTERVAL", "99999")
    os.environ.setdefault("SINGLE_ADMIN_PASSWORD", "")

    def _mock_helper(*args, timeout=30):
        action = args[0] if args else ""
        if action == "deploy":
            return True, "Config written. Backup: config_20240101_120000.json"
        if action == "list-backups":
            return True, '["config_20240101_120000.json"]'
        if action == "restore":
            return True, "Restored OK"
        return True, "ok"

    _patches = [
        patch("app.singbox.deployer._run_helper", side_effect=_mock_helper),
        patch("app.singbox.service._run_helper", side_effect=_mock_helper),
        patch("app.singbox.deployer._service_is_active", return_value=True),
        patch("app.singbox.deployer.validate_config", return_value=(True, "ok")),
        patch("app.singbox.service.get_status", return_value={
            "active_state": "active",
            "sub_state": "running",
            "pid": "1",
            "load_state": "loaded",
            "since": "",
        }),
        patch("app.singbox.service.get_logs", return_value=""),
        patch("app.singbox.service.get_version", return_value="1.13.11"),
        patch(
            "app.health.subprocess.run",
            return_value=type("R", (), {"returncode": 0, "stdout": "state UP\n"})(),
        ),
    ]
    for _patch in _patches:
        _patch.start()

    class _AsgiTestClient:
        __test__ = False

        def __init__(
            self,
            app,
            raise_server_exceptions: bool = True,
            follow_redirects: bool = True,
            base_url: str = "http://testserver",
            **_: object,
        ) -> None:
            self.app = app
            self.raise_server_exceptions = raise_server_exceptions
            self.follow_redirects = follow_redirects
            self.base_url = base_url
            self.cookies = httpx.Cookies()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.close()

        def close(self) -> None:
            return None

        def get(self, url: str, **kwargs):
            return self.request("GET", url, **kwargs)

        def post(self, url: str, **kwargs):
            return self.request("POST", url, **kwargs)

        def request(self, method: str, url: str, **kwargs):
            follow_redirects = kwargs.pop("follow_redirects", self.follow_redirects)
            return asyncio.run(self._request(method, url, follow_redirects=follow_redirects, **kwargs))

        async def _request(self, method: str, url: str, follow_redirects: bool, **kwargs):
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=self.raise_server_exceptions)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
                cookies=self.cookies,
                follow_redirects=follow_redirects,
            ) as client:
                response = await client.request(method, url, **kwargs)
                self.cookies.update(client.cookies)
                return response

    import fastapi.testclient  # noqa: E402
    import starlette.testclient  # noqa: E402

    fastapi.testclient.TestClient = _AsgiTestClient
    starlette.testclient.TestClient = _AsgiTestClient

    from alembic import command as alembic_command  # noqa: E402
    from alembic.config import Config as AlembicConfig  # noqa: E402

    _ini = Path(__file__).parent.parent / "alembic.ini"
    _alembic_cfg = AlembicConfig(str(_ini))
    alembic_command.upgrade(_alembic_cfg, "head")
