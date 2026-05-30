"""
Unit tests for app.health — structure and category tagging.

These tests do not make real network connections or system calls:
they mock subprocess/socket and verify CheckResult shape and HealthReport
computed properties.
"""
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.health import (
    CheckResult,
    HealthReport,
    check_service,
    check_tun_interface,
    run_health_checks,
)

# ── CheckResult ───────────────────────────────────────────────────────────────

def test_check_result_defaults_to_connectivity_category():
    c = CheckResult(name="test", ok=True, latency_ms=10.0, detail="ok")
    assert c.category == "connectivity"


def test_check_result_system_category():
    c = CheckResult(name="test", ok=True, latency_ms=None, detail="ok", category="system")
    assert c.category == "system"


# ── HealthReport properties ──────────────────────────────────────────────────

def _make_report(*checks):
    return HealthReport(overall="connected", checks=list(checks), external_ip=None)


def test_health_report_system_checks_filter():
    sys = CheckResult("svc", True, None, "ok", category="system")
    conn = CheckResult("dns", True, 10.0, "ok", category="connectivity")
    report = _make_report(sys, conn)
    assert report.system_checks == [sys]
    assert report.connectivity_checks == [conn]


def test_health_report_empty_checks():
    report = _make_report()
    assert report.system_checks == []
    assert report.connectivity_checks == []


# ── check_service ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_service_active():
    proc = MagicMock()
    proc.stdout = "active\n"
    proc.returncode = 0
    with patch("app.health.subprocess.run", return_value=proc):
        result = await check_service()
    assert result.ok is True
    assert result.category == "system"
    assert "active" in result.detail


@pytest.mark.asyncio
async def test_check_service_inactive():
    proc = MagicMock()
    proc.stdout = "inactive\n"
    proc.returncode = 3
    with patch("app.health.subprocess.run", return_value=proc):
        result = await check_service()
    assert result.ok is False
    assert result.category == "system"


@pytest.mark.asyncio
async def test_check_service_exception():
    with patch("app.health.subprocess.run", side_effect=FileNotFoundError("systemctl not found")):
        result = await check_service()
    assert result.ok is False
    assert "systemctl not found" in result.detail


# ── check_tun_interface ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_tun_up():
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = "2: singtun0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> state UP\n"
    with patch("app.health.subprocess.run", return_value=proc):
        result = await check_tun_interface()
    assert result.ok is True
    assert result.category == "system"


@pytest.mark.asyncio
async def test_check_tun_down():
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = "2: singtun0: <POINTOPOINT,MULTICAST,NOARP> state DOWN\n"
    with patch("app.health.subprocess.run", return_value=proc):
        result = await check_tun_interface()
    assert result.ok is False
    assert result.category == "system"


@pytest.mark.asyncio
async def test_check_tun_not_found():
    proc = MagicMock()
    proc.returncode = 1
    proc.stdout = ""
    with patch("app.health.subprocess.run", return_value=proc):
        result = await check_tun_interface()
    assert result.ok is False
    assert "not found" in result.detail


# ── run_health_checks — overall calculation ──────────────────────────────────

@pytest.mark.asyncio
async def test_run_health_checks_all_pass():
    """All system + connectivity checks pass → overall: connected."""
    ok_sys = CheckResult("svc", True, None, "ok", category="system")
    ok_conn = CheckResult("dns", True, 5.0, "ok", category="connectivity")

    async def _ok(*a, **kw):
        return ok_sys

    async def _ok_conn(*a, **kw):
        return ok_conn

    with ExitStack() as stack:
        stack.enter_context(patch("app.health.check_service", _ok))
        stack.enter_context(patch("app.health.check_tun_interface", _ok))
        stack.enter_context(patch("app.health.check_dns", _ok_conn))
        stack.enter_context(patch("app.health.check_tcp", _ok_conn))
        stack.enter_context(patch("app.health.check_https", _ok_conn))
        stack.enter_context(patch("app.health.check_external_ip", AsyncMock(return_value=("1.2.3.4", ""))))
        report = await run_health_checks()

    assert report.overall == "connected"
    assert report.external_ip == "1.2.3.4"


@pytest.mark.asyncio
async def test_run_health_checks_one_connectivity_fails():
    """One connectivity check fails → overall: degraded."""
    ok_sys = CheckResult("svc", True, None, "ok", category="system")
    ok_conn = CheckResult("dns", True, 5.0, "ok", category="connectivity")
    fail_conn = CheckResult("https", False, None, "timeout", category="connectivity")

    async def _sys(*a, **kw): return ok_sys
    async def _ok(*a, **kw): return ok_conn
    async def _fail(*a, **kw): return fail_conn

    with ExitStack() as stack:
        stack.enter_context(patch("app.health.check_service", _sys))
        stack.enter_context(patch("app.health.check_tun_interface", _sys))
        stack.enter_context(patch("app.health.check_dns", _ok))
        stack.enter_context(patch("app.health.check_tcp", _ok))
        stack.enter_context(patch("app.health.check_https", _fail))
        stack.enter_context(patch("app.health.check_external_ip", AsyncMock(return_value=(None, "err"))))
        report = await run_health_checks()

    assert report.overall == "degraded"


@pytest.mark.asyncio
async def test_run_health_checks_all_connectivity_fail():
    """All connectivity checks fail → overall: failed."""
    ok_sys = CheckResult("svc", True, None, "ok", category="system")
    fail = CheckResult("x", False, None, "err", category="connectivity")

    async def _sys(*a, **kw): return ok_sys
    async def _fail(*a, **kw): return fail

    with ExitStack() as stack:
        stack.enter_context(patch("app.health.check_service", _sys))
        stack.enter_context(patch("app.health.check_tun_interface", _sys))
        stack.enter_context(patch("app.health.check_dns", _fail))
        stack.enter_context(patch("app.health.check_tcp", _fail))
        stack.enter_context(patch("app.health.check_https", _fail))
        stack.enter_context(patch("app.health.check_external_ip", AsyncMock(return_value=(None, "err"))))
        report = await run_health_checks()

    assert report.overall == "failed"
