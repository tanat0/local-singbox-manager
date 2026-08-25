from __future__ import annotations

import json
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

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ConfigGroup, Node  # noqa: E402
from app.parsers import parse_url  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client


def _ensure_node(raw_url: str) -> str:
    parsed = parse_url(raw_url)
    db = SessionLocal()
    try:
        existing = db.query(Node).filter(Node.tag == parsed.tag).first()
        if not existing:
            db.add(Node(
                tag=parsed.tag,
                protocol=parsed.protocol,
                raw_url=parsed.raw_url,
                parsed_json=json.dumps(parsed.to_dict()),
                schema_version=parsed.schema_version,
                active=False,
            ))
            db.commit()
        return parsed.tag
    finally:
        db.close()


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


def test_log_insights_endpoint_groups_recent_problems(client):
    log_text = (
        "2026-06-07T00:42:13+03:00 host sing-box[1]: ERROR [1 4.5s] "
        "connection: open connection to 91.105.192.100:80 "
        "using outbound/hysteria2[hy kz]: timeout: no recent network activity"
    )
    with patch("app.singbox.service.get_logs", return_value=log_text):
        response = client.get("/api/log-insights")

    assert response.status_code == 200
    assert b"hysteria2" in response.content
    assert b"hy kz" in response.content
    assert b"no recent network activity" in response.content


def test_users_create_group_and_user(client):
    suffix = uuid.uuid4().hex[:8]
    node_tag = _ensure_node(
        "vless://12345678-abcd-0000-0000-000000000002@1.2.3.4:443"
        "?security=reality&sni=example.com&pbk=fakepubkey&sid=aabbcc&fp=chrome&type=tcp"
        f"#page-node-{suffix}"
    )
    group_name = f"family-{suffix}"
    telegram_id = f"123456789{suffix}"
    group_resp = client.post("/users/groups", data={
        "name": group_name,
        "description": "Family configs",
        "node_tags": [node_tag],
        "route_preset": "bypass_lan",
        "refresh_limit_per_hour": "3",
        "notes": "limited access",
        "enabled": "on",
    }, follow_redirects=True)
    assert group_resp.status_code == 200
    assert b"Created group" in group_resp.content
    assert group_name.encode() in group_resp.content
    assert node_tag.encode() in group_resp.content
    assert b"Bypass LAN" in group_resp.content
    assert b"Download config.json" in group_resp.content
    assert b"Download .sbclient" in group_resp.content

    user_resp = client.post("/users", data={
        "telegram_id": telegram_id,
        "display_name": "Alex",
        "config_group_id": "",
        "refresh_limit_per_hour": "2",
        "notes": "test user",
        "enabled": "on",
    }, follow_redirects=True)
    assert user_resp.status_code == 200
    assert b"Created user" in user_resp.content
    assert telegram_id.encode() in user_resp.content


def test_users_reject_unknown_group_node_tag(client):
    response = client.post("/users/groups", data={
        "name": f"bad-family-{uuid.uuid4().hex[:8]}",
        "node_tags": ["missing-node-tag"],
        "enabled": "on",
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"Unknown node tag" in response.content


def test_users_reject_invalid_group_route_preset(client):
    response = client.post("/users/groups", data={
        "name": f"bad-route-{uuid.uuid4().hex[:8]}",
        "route_preset": "missing",
        "enabled": "on",
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"Invalid route preset" in response.content


def test_users_page_shows_delivery_log(client):
    from app.models import ConfigDeliveryLog

    db = SessionLocal()
    try:
        db.add(ConfigDeliveryLog(
            telegram_id="9001",
            action="/refresh",
            success=True,
            config_version=2,
            config_fingerprint="a" * 64,
            detail="1 config delivered",
        ))
        db.commit()
    finally:
        db.close()

    response = client.get("/users")
    assert response.status_code == 200
    assert b"Delivery Log" in response.content
    assert b"/refresh" in response.content
    assert b"aaaaaaaaaaaa" in response.content


def _create_group(client, *, name: str, node_tags=None, route_preset: str = "bypass_lan") -> int:
    data = {
        "name": name,
        "description": "Download test",
        "route_preset": route_preset,
        "refresh_limit_per_hour": "3",
        "notes": "",
        "enabled": "on",
    }
    if node_tags:
        data["node_tags"] = node_tags
    response = client.post("/users/groups", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Created group" in response.content
    db = SessionLocal()
    try:
        group = db.query(ConfigGroup).filter(ConfigGroup.name == name).one()
        return group.id
    finally:
        db.close()


def test_users_download_config_json(client):
    suffix = uuid.uuid4().hex[:8]
    node_tag = _ensure_node(
        "vless://12345678-abcd-0000-0000-000000000002@1.2.3.4:443"
        "?security=reality&sni=example.com&pbk=fakepubkey&sid=aabbcc&fp=chrome&type=tcp"
        f"#page-dl-config-{suffix}"
    )
    group_id = _create_group(client, name=f"dl-config-{suffix}", node_tags=[node_tag])

    response = client.get(f"/users/groups/{group_id}/download/config")

    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    assert "attachment" in response.headers.get("content-disposition", "")
    assert response.headers["content-disposition"].endswith(".json\"")
    payload = json.loads(response.content)
    assert any(outbound.get("tag") == node_tag for outbound in payload["outbounds"])


def test_users_download_sbclient_bundle(client):
    suffix = uuid.uuid4().hex[:8]
    node_tag = _ensure_node(
        "vless://12345678-abcd-0000-0000-000000000002@1.2.3.4:443"
        "?security=reality&sni=example.com&pbk=fakepubkey&sid=aabbcc&fp=chrome&type=tcp"
        f"#page-dl-sbclient-{suffix}"
    )
    group_id = _create_group(client, name=f"dl-sbclient-{suffix}", node_tags=[node_tag])

    response = client.get(f"/users/groups/{group_id}/download/sbclient")

    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    assert ".sbclient" in response.headers.get("content-disposition", "")
    payload = json.loads(response.content)
    assert payload["schema_version"] == 1
    assert payload["profiles"][0]["name"] == node_tag
    assert payload["profiles"][0]["route_preset"] == "bypass_lan"


def test_users_download_redirects_when_group_is_missing(client):
    response = client.get("/users/groups/999999/download/config", follow_redirects=True)

    assert response.status_code == 200
    assert b"Config group not found." in response.content
    assert b"vless://" not in response.content


def test_users_download_redirects_when_group_has_no_nodes(client):
    suffix = uuid.uuid4().hex[:8]
    group_id = _create_group(client, name=f"dl-empty-{suffix}")

    response = client.get(f"/users/groups/{group_id}/download/sbclient", follow_redirects=True)

    assert response.status_code == 200
    assert b"Assigned config group has no nodes." in response.content
    assert b"vless://" not in response.content


def test_users_download_redirects_when_transport_is_unsupported(client):
    suffix = uuid.uuid4().hex[:8]
    node_tag = _ensure_node(
        "vless://12345678-abcd-0000-0000-000000000002@1.2.3.4:443"
        "?security=reality&sni=example.com&pbk=fakepubkey&sid=aabbcc&fp=chrome&type=xhttp"
        f"#page-dl-xhttp-{suffix}"
    )
    group_id = _create_group(client, name=f"dl-xhttp-{suffix}", node_tags=[node_tag])

    response = client.get(f"/users/groups/{group_id}/download/config", follow_redirects=True)

    assert response.status_code == 200
    assert b"XHTTP" in response.content
    assert b"vless://" not in response.content


def _node_id(tag: str) -> int:
    db = SessionLocal()
    try:
        return db.query(Node).filter(Node.tag == tag).one().id
    finally:
        db.close()


def test_nodes_page_renders_topology_role_select(client):
    suffix = uuid.uuid4().hex[:8]
    _ensure_node(
        "vless://12345678-abcd-0000-0000-000000000002@1.2.3.4:443"
        "?security=reality&sni=example.com&pbk=fakepubkey&sid=aabbcc&fp=chrome&type=tcp"
        f"#page-role-select-{suffix}"
    )
    response = client.get("/nodes")
    assert response.status_code == 200
    assert b"Entry relay" in response.content
    assert b"Upstream exit" in response.content


def test_nodes_save_topology_role(client):
    suffix = uuid.uuid4().hex[:8]
    tag = _ensure_node(
        "vless://12345678-abcd-0000-0000-000000000002@1.2.3.4:443"
        "?security=reality&sni=example.com&pbk=fakepubkey&sid=aabbcc&fp=chrome&type=tcp"
        f"#page-role-{suffix}"
    )
    node_id = _node_id(tag)

    response = client.post(f"/nodes/{node_id}/metadata", data={
        "country_code": "",
        "country_name": "",
        "provider_name": "",
        "notes": "",
        "topology_role": "entry_relay",
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"Updated metadata" in response.content
    assert b"entry relay" in response.content
    payload = json.loads(client.get("/api/nodes/export").content)
    exported = next(item for item in payload if item["tag"] == tag)
    assert exported["topology_role"] == "entry_relay"


def test_nodes_reject_invalid_topology_role(client):
    suffix = uuid.uuid4().hex[:8]
    tag = _ensure_node(
        "vless://12345678-abcd-0000-0000-000000000002@1.2.3.4:443"
        "?security=reality&sni=example.com&pbk=fakepubkey&sid=aabbcc&fp=chrome&type=tcp"
        f"#page-role-bad-{suffix}"
    )
    node_id = _node_id(tag)

    response = client.post(f"/nodes/{node_id}/metadata", data={
        "topology_role": "panel",
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"Invalid topology role" in response.content
    payload = json.loads(client.get("/api/nodes/export").content)
    exported = next(item for item in payload if item["tag"] == tag)
    assert exported["topology_role"] is None


def test_nodes_import_roundtrip_topology_role(client):
    suffix = uuid.uuid4().hex[:8]
    tag = _ensure_node(
        "vless://12345678-abcd-0000-0000-000000000002@1.2.3.4:443"
        "?security=reality&sni=example.com&pbk=fakepubkey&sid=aabbcc&fp=chrome&type=tcp"
        f"#page-role-import-{suffix}"
    )
    node_id = _node_id(tag)
    client.post(f"/nodes/{node_id}/metadata", data={"topology_role": "upstream_exit"}, follow_redirects=True)
    export_json = client.get("/api/nodes/export").content.decode("utf-8")

    response = client.post("/api/nodes/import", data={"nodes_json": export_json}, follow_redirects=True)

    assert response.status_code == 200
    assert b"Imported" in response.content
    payload = json.loads(client.get("/api/nodes/export").content)
    exported = next(item for item in payload if item["tag"] == tag)
    assert exported["topology_role"] == "upstream_exit"
