"""
Integration tests for the profile system.
Uses isolated SQLite DB + Alembic migrations + mocked system calls.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from contextlib import ExitStack
from unittest.mock import patch

import pytest

# ── Isolated DB — set BEFORE any app import ───────────────────────────────────
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ.setdefault("DATABASE_URL_PROFILES", f"sqlite:///{_db_path}")
# Use a unique env var so this doesn't clobber other test files' DATABASE_URL
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["HEALTH_CHECK_INTERVAL"] = "99999"

# ── Mock all privileged calls ─────────────────────────────────────────────────
def _mock_helper(*a, timeout=30):
    action = a[0] if a else ""
    if action == "deploy":
        return True, "Backup: config_20240101_120000.json"
    if action in ("reload", "restart", "start", "stop"):
        return True, "OK"
    if action == "list-backups":
        return True, '["config_20240101_120000.json"]'
    if action == "restore":
        return True, "Restored"
    return True, "OK"

_patches = [
    patch("app.singbox.deployer._run_helper",        side_effect=_mock_helper),
    patch("app.singbox.service._run_helper",          side_effect=_mock_helper),
    patch("app.singbox.deployer._service_is_active",  return_value=True),
    patch("app.singbox.deployer.validate_config",     return_value=(True, "ok")),
    patch("app.singbox.service.get_status", return_value={
        "active_state": "active", "sub_state": "running",
        "pid": "1", "load_state": "loaded", "since": "",
    }),
    patch("app.singbox.service.get_logs",    return_value=""),
    patch("app.singbox.service.get_version", return_value="1.13.11"),
    patch("app.health.subprocess.run",
          return_value=type("R", (), {"returncode": 0, "stdout": "state UP\n"})()),
]
for _p in _patches:
    _p.start()

# ── Run migrations ────────────────────────────────────────────────────────────
from pathlib import Path
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

_ini = Path(__file__).parent.parent / "alembic.ini"
_alembic_cfg = AlembicConfig(str(_ini))
alembic_command.upgrade(_alembic_cfg, "head")

# ── Import app ────────────────────────────────────────────────────────────────
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import Node, Profile, Settings

VLESS_URL = (
    "vless://12345678-abcd-0000-0000-aaaaaaaaaaaa@1.2.3.4:443"
    "?security=reality&sni=example.com&pbk=pubkey&sid=ab&fp=chrome&type=tcp"
    "#test-node"
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(scope="module")
def node_in_db():
    """Add a test node to the DB once for the whole module."""
    db = SessionLocal()
    try:
        from app.parsers import parse_url
        parsed = parse_url(VLESS_URL)
        existing = db.query(Node).filter(Node.tag == parsed.tag).first()
        if not existing:
            db.add(Node(
                tag=parsed.tag, protocol=parsed.protocol, raw_url=parsed.raw_url,
                parsed_json=json.dumps(parsed.to_dict()),
                schema_version=parsed.schema_version, active=False,
            ))
            db.commit()
        return parsed.tag
    finally:
        db.close()


def _get_profile(name: str):
    db = SessionLocal()
    try:
        return db.query(Profile).filter(Profile.name == name).first()
    finally:
        db.close()


def _get_node(tag: str):
    db = SessionLocal()
    try:
        return db.query(Node).filter(Node.tag == tag).first()
    finally:
        db.close()


def _get_setting(key: str):
    db = SessionLocal()
    try:
        s = db.query(Settings).filter(Settings.key == key).first()
        return s.value if s else None
    finally:
        db.close()


# ── Profiles page ─────────────────────────────────────────────────────────────

def test_profiles_page_loads(client):
    r = client.get("/profiles")
    assert r.status_code == 200
    assert b"Profiles" in r.content


def test_profiles_page_shows_create_form(client):
    r = client.get("/profiles")
    assert b"node_tag" in r.content
    assert b"dns_preset" in r.content
    assert b"route_preset" in r.content


# ── Create ────────────────────────────────────────────────────────────────────

def test_create_profile_success(client, node_in_db):
    r = client.post("/profiles", data={
        "name": "work",
        "description": "Work VPN",
        "node_tag": node_in_db,
        "dns_preset": "quad9_tls",
        "route_preset": "full_tunnel",
    })
    assert r.status_code in (200, 303)
    profile = _get_profile("work")
    assert profile is not None
    assert profile.node_tag == node_in_db
    assert profile.dns_preset == "quad9_tls"
    assert profile.route_preset == "full_tunnel"
    assert profile.active is False


def test_create_profile_no_node(client):
    r = client.post("/profiles", data={
        "name": "no-node-profile",
        "node_tag": "",
        "dns_preset": "cloudflare_tls",
        "route_preset": "bypass_lan",
    })
    assert r.status_code in (200, 303)
    profile = _get_profile("no-node-profile")
    assert profile is not None
    assert profile.node_tag is None


def test_create_profile_duplicate_name_shows_error(client, node_in_db):
    r = client.post("/profiles", data={
        "name": "work",   # already exists
        "node_tag": node_in_db,
        "dns_preset": "quad9_tls",
        "route_preset": "full_tunnel",
    }, follow_redirects=True)
    assert b"already exists" in r.content


def test_create_profile_empty_name_shows_error(client):
    r = client.post("/profiles", data={
        "name": "",
        "node_tag": "",
        "dns_preset": "quad9_tls",
        "route_preset": "full_tunnel",
    }, follow_redirects=True)
    assert b"required" in r.content or r.status_code == 422


def test_create_profile_invalid_dns_preset(client):
    r = client.post("/profiles", data={
        "name": "bad-dns",
        "node_tag": "",
        "dns_preset": "nonexistent",
        "route_preset": "full_tunnel",
    }, follow_redirects=True)
    assert b"Invalid" in r.content


# ── Activate ──────────────────────────────────────────────────────────────────

def test_activate_profile_success(client, node_in_db):
    profile = _get_profile("work")
    r = client.post(f"/profiles/{profile.id}/activate", follow_redirects=True)
    assert r.status_code == 200
    assert b"activated" in r.content.lower() or b"active" in r.content.lower()

    # Profile is now active
    updated = _get_profile("work")
    assert updated.active is True

    # Node is now active
    node = _get_node(node_in_db)
    assert node.active is True

    # Settings updated to profile's presets
    assert _get_setting("dns_preset") == "quad9_tls"
    assert _get_setting("route_preset") == "full_tunnel"


def test_activate_profile_no_node_shows_error(client):
    profile = _get_profile("no-node-profile")
    r = client.post(f"/profiles/{profile.id}/activate", follow_redirects=True)
    assert b"no node" in r.content.lower()

    # Profile must NOT be active
    p = _get_profile("no-node-profile")
    assert p.active is False


def test_activate_profile_missing_node_shows_error(client):
    # Create a profile pointing to a ghost node
    db = SessionLocal()
    try:
        ghost = Profile(
            name=f"ghost-profile-{uuid.uuid4().hex[:8]}", node_tag="nonexistent-node",
            dns_preset="quad9_tls", route_preset="full_tunnel", active=False,
        )
        db.add(ghost)
        db.commit()
        profile_id = ghost.id
    finally:
        db.close()

    r = client.post(f"/profiles/{profile_id}/activate", follow_redirects=True)
    assert b"no longer exists" in r.content or b"not found" in r.content.lower()


def test_activate_profile_nonexistent_id(client):
    r = client.post("/profiles/99999/activate", follow_redirects=True)
    assert b"not found" in r.content.lower()


def test_activate_profile_marks_others_inactive(client, node_in_db):
    # Create a second profile and activate it
    client.post("/profiles", data={
        "name": "gaming",
        "node_tag": node_in_db,
        "dns_preset": "cloudflare_tls",
        "route_preset": "bypass_lan",
    })
    gaming = _get_profile("gaming")
    client.post(f"/profiles/{gaming.id}/activate")

    # "work" should now be inactive
    work = _get_profile("work")
    assert work.active is False
    gaming_refreshed = _get_profile("gaming")
    assert gaming_refreshed.active is True


def test_activate_profile_updates_settings(client, node_in_db):
    gaming = _get_profile("gaming")
    client.post(f"/profiles/{gaming.id}/activate")
    assert _get_setting("dns_preset") == "cloudflare_tls"
    assert _get_setting("route_preset") == "bypass_lan"


# ── Direct node activation clears active profile ──────────────────────────────

def test_activate_node_directly_clears_active_profile(client, node_in_db):
    # Make sure "gaming" is active first
    gaming = _get_profile("gaming")
    client.post(f"/profiles/{gaming.id}/activate")
    assert _get_profile("gaming").active is True

    # Activate node directly (bypassing profile system)
    node = _get_node(node_in_db)
    client.post(f"/nodes/{node.id}/activate")

    # All profiles should be inactive now
    db = SessionLocal()
    try:
        active_profiles = db.query(Profile).filter(Profile.active.is_(True)).all()
    finally:
        db.close()
    assert active_profiles == []


# ── Manual settings change clears active profile ──────────────────────────────

def test_save_settings_clears_active_profile(client, node_in_db):
    # Activate "work" profile
    work = _get_profile("work")
    client.post(f"/profiles/{work.id}/activate")
    assert _get_profile("work").active is True

    # Change settings manually
    client.post("/settings", data={"dns_preset": "google_tls", "route_preset": "full_tunnel"})

    # Profile should be inactive
    assert _get_profile("work").active is False


# ── Delete ────────────────────────────────────────────────────────────────────

def test_delete_profile_success(client):
    client.post("/profiles", data={
        "name": "temp-profile",
        "node_tag": "",
        "dns_preset": "quad9_tls",
        "route_preset": "full_tunnel",
    })
    profile = _get_profile("temp-profile")
    assert profile is not None

    r = client.post(f"/profiles/{profile.id}/delete", follow_redirects=True)
    assert r.status_code == 200
    assert _get_profile("temp-profile") is None


def test_delete_nonexistent_profile(client):
    r = client.post("/profiles/99999/delete", follow_redirects=True)
    assert b"not found" in r.content.lower()


def test_delete_active_profile_does_not_affect_deployed_config(client, node_in_db):
    """Deleting the active profile doesn't roll back or touch the running sing-box."""
    work = _get_profile("work")
    client.post(f"/profiles/{work.id}/activate")

    node = _get_node(node_in_db)
    client.post(f"/profiles/{work.id}/delete")

    # Node still active even after profile deleted
    node_refreshed = _get_node(node_in_db)
    assert node_refreshed.active is True
