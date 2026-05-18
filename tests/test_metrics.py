"""
Tests for the /api/metrics/latency endpoint and HealthCheckLog storage.
Uses an isolated SQLite DB, runs migrations explicitly before tests.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

# ── Isolated DB — set BEFORE any app import ──────────────────────────────────
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["HEALTH_CHECK_INTERVAL"] = "99999"   # effectively disable background task

# ── Mock all privileged calls ─────────────────────────────────────────────────
def _mock_helper(*a, timeout=30): return True, "ok"
def _mock_validate(cfg): return True, "ok"

_patches = [
    patch("app.singbox.deployer._run_helper", side_effect=_mock_helper),
    patch("app.singbox.service._run_helper", side_effect=_mock_helper),
    patch("app.singbox.deployer._service_is_active", return_value=True),
    patch("app.singbox.deployer.validate_config", side_effect=_mock_validate),
    patch("app.singbox.service.get_status", return_value={
        "active_state": "active", "sub_state": "running",
        "pid": "1", "load_state": "loaded", "since": "",
    }),
    patch("app.singbox.service.get_logs", return_value=""),
    patch("app.singbox.service.get_version", return_value="1.13.11"),
    patch("app.health.subprocess.run",
          return_value=type("R", (), {"returncode": 0, "stdout": "state UP\n"})()),
]
for _p in _patches:
    _p.start()

# ── Run migrations against the temp DB before importing app ──────────────────
from pathlib import Path
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

_ini = Path(__file__).parent.parent / "alembic.ini"
_alembic_cfg = AlembicConfig(str(_ini))
alembic_command.upgrade(_alembic_cfg, "head")

# ── Now import app ────────────────────────────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app                   # noqa: E402
from app.db import SessionLocal            # noqa: E402
from app.models import HealthCheckLog      # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_health_logs():
    db = SessionLocal()
    try:
        db.query(HealthCheckLog).delete()
        db.commit()
        yield
        db.query(HealthCheckLog).delete()
        db.commit()
    finally:
        db.close()


def _seed(check_name: str, category: str = "connectivity",
          n: int = 5, ok: bool = True, latency: float = 42.0):
    db = SessionLocal()
    now = datetime.utcnow()
    try:
        for i in range(n):
            ts = now - timedelta(minutes=5 * (n - i))
            db.add(HealthCheckLog(
                checked_at=ts, check_name=check_name, category=category,
                ok=ok, latency_ms=latency if ok else None,
                detail="ok" if ok else "timeout",
            ))
        db.commit()
    finally:
        db.close()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_metrics_empty_db(client):
    resp = client.get("/api/metrics/latency")
    assert resp.status_code == 200
    data = resp.json()
    assert data["series"] == []
    assert data["hours"] == 24


def test_metrics_returns_series_after_seeding(client):
    _seed("DNS (google.com)", latency=50.0)
    resp = client.get("/api/metrics/latency")
    assert resp.status_code == 200
    data = resp.json()
    dns = next((s for s in data["series"] if "DNS" in s["name"]), None)
    assert dns is not None
    assert dns["uptime_pct"] == 100.0
    assert dns["avg_ms"] == 50.0
    assert dns["sample_count"] >= 5


def test_metrics_uptime_below_100_when_failures(client):
    db = SessionLocal()
    now = datetime.utcnow()
    try:
        for i, ok in enumerate([True, True, True, True, False]):
            db.add(HealthCheckLog(
                checked_at=now - timedelta(minutes=5 * (5 - i)),
                check_name="TCP 1.1.1.1:80", category="connectivity",
                ok=ok, latency_ms=30.0 if ok else None, detail="",
            ))
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/metrics/latency")
    tcp = next((s for s in resp.json()["series"] if "TCP" in s["name"]), None)
    assert tcp is not None
    assert tcp["uptime_pct"] < 100.0


def test_metrics_hours_param_clamp(client):
    resp = client.get("/api/metrics/latency?hours=9999")
    assert resp.status_code == 200
    assert resp.json()["hours"] == 168   # clamped to 7 days


def test_metrics_hours_param_min(client):
    resp = client.get("/api/metrics/latency?hours=0")
    assert resp.status_code == 200
    assert resp.json()["hours"] == 1    # clamped to 1h


def test_metrics_only_connectivity_category(client):
    _seed("Service (sing-box.service)", category="system", ok=True, latency=0.0)
    resp = client.get("/api/metrics/latency")
    names = [s["name"] for s in resp.json()["series"]]
    assert "Service (sing-box.service)" not in names


def test_metrics_points_have_required_keys(client):
    _seed("DNS (google.com)", latency=25.0)
    resp = client.get("/api/metrics/latency")
    dns = next((s for s in resp.json()["series"] if "DNS" in s["name"]), None)
    assert dns is not None
    for pt in dns["points"]:
        assert "t" in pt and "ms" in pt and "ok" in pt


def test_metrics_failed_points_have_null_ms(client):
    _seed("DNS (google.com)", ok=False, latency=0.0)
    resp = client.get("/api/metrics/latency")
    dns = next((s for s in resp.json()["series"] if "DNS" in s["name"]), None)
    assert dns is not None
    failed = [p for p in dns["points"] if not p["ok"]]
    assert all(p["ms"] is None for p in failed)
