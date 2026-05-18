from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["HEALTH_CHECK_INTERVAL"] = "99999"
os.environ["SINGLE_ADMIN_PASSWORD"] = ""


def _mock_helper(*args, timeout=30):
    action = args[0] if args else ""
    if action == "list-backups":
        return True, "[]"
    return True, "ok"


_patches = [
    patch("app.singbox.service._run_helper", side_effect=_mock_helper),
    patch("app.singbox.deployer._run_helper", side_effect=_mock_helper),
    patch("app.singbox.service.get_status", return_value={
        "active_state": "active",
        "sub_state": "running",
        "pid": "1",
        "load_state": "loaded",
        "since": "",
    }),
    patch("app.singbox.service.get_logs", return_value=""),
    patch("app.singbox.service.get_version", return_value="1.13.11"),
]
for _patch in _patches:
    _patch.start()

_ini = Path(__file__).parent.parent / "alembic.ini"
_alembic_cfg = AlembicConfig(str(_ini))
alembic_command.upgrade(_alembic_cfg, "head")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client


@pytest.mark.parametrize(
    ("path", "needle"),
    [
        ("/", b"Dashboard"),
        ("/nodes", b"Nodes"),
        ("/logs", b"Service Logs"),
        ("/settings", b"Settings"),
        ("/profiles", b"Profiles"),
        ("/users", b"Users"),
        ("/diagnostics", b"Diagnostics"),
        ("/backups", b"Backups"),
    ],
)
def test_page_renders(client, path, needle):
    response = client.get(path)
    assert response.status_code == 200
    assert needle in response.content


def test_health_and_version_probes(client):
    assert client.get("/health").status_code == 200
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json()["app"]


def test_users_create_group_and_user(client):
    suffix = uuid.uuid4().hex[:8]
    group_name = f"family-{suffix}"
    telegram_id = f"123456789{suffix}"
    group_resp = client.post("/users/groups", data={
        "name": group_name,
        "description": "Family configs",
        "node_tags": "node-a, node-b",
        "notes": "limited access",
        "enabled": "on",
    }, follow_redirects=True)
    assert group_resp.status_code == 200
    assert b"Created group" in group_resp.content
    assert group_name.encode() in group_resp.content

    user_resp = client.post("/users", data={
        "telegram_id": telegram_id,
        "display_name": "Alex",
        "config_group_id": "",
        "notes": "test user",
        "enabled": "on",
    }, follow_redirects=True)
    assert user_resp.status_code == 200
    assert b"Created user" in user_resp.content
    assert telegram_id.encode() in user_resp.content
