"""
Tests for app/auth.py.

IMPORTANT: auth constants (ADMIN_PASSWORD, SESSION_SECRET, AUTH_ENABLED) are
patched via patch.object rather than env vars, so this file does NOT pollute
the auth state seen by other test modules.
"""
from __future__ import annotations

import time
from contextlib import ExitStack
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

import app.auth as auth
from app.auth import (
    SESSION_COOKIE,
    create_session_token,
    verify_session_token,
    verify_password,
    rate_limit_ok,
    is_authenticated,
    check_csrf,
)

_TEST_PASSWORD = "s3cr3t-test-pw"
_TEST_SECRET   = "test-session-secret-abc123"


# ── Autouse: patch auth constants for the whole module ────────────────────────
# Tests that need auth disabled override locally with their own patch.

@pytest.fixture(autouse=True, scope="module")
def _enable_auth():
    with ExitStack() as stack:
        stack.enter_context(patch.object(auth, "ADMIN_PASSWORD", _TEST_PASSWORD))
        stack.enter_context(patch.object(auth, "SESSION_SECRET",  _TEST_SECRET))
        stack.enter_context(patch.object(auth, "AUTH_ENABLED",    True))
        yield


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_request(cookie: str = "", origin: str = "", referer: str = "",
                  method: str = "POST") -> MagicMock:
    req = MagicMock()
    req.cookies = {SESSION_COOKIE: cookie} if cookie else {}
    headers: dict = {}
    if origin:
        headers["origin"] = origin
    if referer:
        headers["referer"] = referer
    req.headers = headers
    req.method = method
    return req


# ── Session token ─────────────────────────────────────────────────────────────

def test_session_token_roundtrip():
    token = create_session_token()
    assert verify_session_token(token)


def test_session_token_wrong_secret():
    token = create_session_token()
    with patch.object(auth, "SESSION_SECRET", "different-secret"):
        assert not verify_session_token(token)


def test_session_token_tampered_sig():
    token = create_session_token()
    ts, sig = token.split(".", 1)
    assert not verify_session_token(f"{ts}.{'x' * len(sig)}")


def test_session_token_expired():
    past_ts = int(time.time()) - auth.SESSION_MAX_AGE - 1
    sig = auth._sign_session(past_ts)
    assert not verify_session_token(f"{past_ts}.{sig}")


def test_session_token_future_ts_rejected():
    future_ts = int(time.time()) + 7200
    sig = auth._sign_session(future_ts)
    assert not verify_session_token(f"{future_ts}.{sig}")


def test_session_token_garbage():
    assert not verify_session_token("garbage")
    assert not verify_session_token("")
    assert not verify_session_token("no.dot.parts.four")


# ── Password verification ─────────────────────────────────────────────────────

def test_verify_password_correct():
    assert verify_password(_TEST_PASSWORD)


def test_verify_password_wrong():
    assert not verify_password("wrong-password")


def test_verify_password_empty():
    assert not verify_password("")


def test_verify_password_returns_false_when_no_admin_pw():
    with patch.object(auth, "ADMIN_PASSWORD", ""):
        assert not verify_password("anything")


# ── Rate limiting ─────────────────────────────────────────────────────────────

def test_rate_limit_allows_under_threshold():
    ip = "192.168.99.10"
    auth._login_attempts.pop(ip, None)
    for _ in range(auth._RATE_MAX - 1):
        assert rate_limit_ok(ip)


def test_rate_limit_blocks_after_max():
    ip = "192.168.99.11"
    auth._login_attempts.pop(ip, None)
    for _ in range(auth._RATE_MAX):
        rate_limit_ok(ip)
    assert not rate_limit_ok(ip)


def test_rate_limit_window_expires():
    ip = "192.168.99.12"
    # Fill with old timestamps beyond the window
    old = time.monotonic() - auth._RATE_WINDOW - 1
    auth._login_attempts[ip] = [old] * auth._RATE_MAX
    assert rate_limit_ok(ip)   # old entries cleaned → allowed


def test_rate_limit_independent_ips():
    ip_a, ip_b = "10.0.0.10", "10.0.0.11"
    auth._login_attempts.pop(ip_a, None)
    auth._login_attempts.pop(ip_b, None)
    for _ in range(auth._RATE_MAX):
        rate_limit_ok(ip_a)
    assert not rate_limit_ok(ip_a)
    assert rate_limit_ok(ip_b)


# ── is_authenticated ──────────────────────────────────────────────────────────

def test_is_authenticated_valid_cookie():
    token = create_session_token()
    req = _fake_request(cookie=token)
    assert is_authenticated(req)


def test_is_authenticated_no_cookie():
    req = _fake_request()
    assert not is_authenticated(req)


def test_is_authenticated_bad_cookie():
    req = _fake_request(cookie="garbage.token")
    assert not is_authenticated(req)


def test_is_authenticated_open_when_auth_disabled():
    with patch.object(auth, "AUTH_ENABLED", False):
        assert is_authenticated(_fake_request())  # no cookie needed


# ── CSRF ──────────────────────────────────────────────────────────────────────

def test_csrf_passes_for_get():
    assert check_csrf(_fake_request(method="GET"))


def test_csrf_passes_correct_origin():
    assert check_csrf(_fake_request(origin="http://127.0.0.1:9090"))


def test_csrf_passes_localhost_origin():
    assert check_csrf(_fake_request(origin="http://localhost:9090"))


def test_csrf_passes_referer_fallback():
    assert check_csrf(_fake_request(referer="http://127.0.0.1:9090/nodes"))


def test_csrf_blocks_wrong_origin():
    assert not check_csrf(_fake_request(origin="http://evil.com"))


def test_csrf_blocks_missing_origin_and_referer():
    assert not check_csrf(_fake_request())  # no origin, no referer


def test_csrf_open_when_auth_disabled():
    with patch.object(auth, "AUTH_ENABLED", False):
        assert check_csrf(_fake_request())   # no origin needed


# ── Middleware via HTTP (TestClient) ──────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_client():
    """TestClient with auth-related module constants patched."""
    with ExitStack() as stack:
        stack.enter_context(patch("app.singbox.deployer._run_helper", return_value=(True, "")))
        stack.enter_context(patch("app.singbox.service._run_helper",  return_value=(True, "")))
        stack.enter_context(patch("app.singbox.deployer._service_is_active", return_value=True))
        stack.enter_context(patch("app.singbox.deployer.validate_config", return_value=(True, "ok")))
        stack.enter_context(patch("app.singbox.service.get_status", return_value={
            "active_state": "active", "sub_state": "running",
            "pid": "1", "load_state": "loaded", "since": "",
        }))
        stack.enter_context(patch("app.singbox.service.get_logs",    return_value=""))
        stack.enter_context(patch("app.singbox.service.get_version", return_value="1.13.11"))
        stack.enter_context(patch("app.health.subprocess.run",
                                  return_value=type("R", (), {
                                      "returncode": 0, "stdout": "state UP\n"})()))
        # Re-apply auth patches so the middleware sees them (module fixture ordering)
        stack.enter_context(patch.object(auth, "ADMIN_PASSWORD", _TEST_PASSWORD))
        stack.enter_context(patch.object(auth, "SESSION_SECRET",  _TEST_SECRET))
        stack.enter_context(patch.object(auth, "AUTH_ENABLED",    True))

        from app.main import app as _app
        with TestClient(_app, raise_server_exceptions=True, follow_redirects=False) as c:
            yield c


def test_health_open_without_cookie(auth_client):
    r = auth_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_version_open_without_cookie(auth_client):
    r = auth_client.get("/version")
    assert r.status_code == 200
    assert "app" in r.json()


def test_static_open_without_cookie(auth_client):
    r = auth_client.get("/static/style.css")
    assert r.status_code == 200


def test_dashboard_redirects_without_cookie(auth_client):
    r = auth_client.get("/")
    assert r.status_code == 302
    assert "/login" in r.headers["location"]


def test_api_returns_401_json_without_cookie(auth_client):
    r = auth_client.get("/api/metrics/latency")
    assert r.status_code == 401
    assert r.json()["error"] == "Unauthorized"


def test_login_page_loads(auth_client):
    r = auth_client.get("/login")
    assert r.status_code == 200
    assert b"Sign in" in r.content


def test_login_wrong_password_returns_401(auth_client):
    r = auth_client.post("/login", data={"password": "wrong", "next": "/"})
    assert r.status_code == 401
    assert b"Incorrect" in r.content


def test_login_correct_password_sets_cookie(auth_client):
    r = auth_client.post("/login", data={"password": _TEST_PASSWORD, "next": "/"})
    assert r.status_code == 303
    assert SESSION_COOKIE in r.cookies


def test_dashboard_accessible_with_valid_session(auth_client):
    token = create_session_token()
    auth_client.cookies.set(SESSION_COOKIE, token)
    r = auth_client.get("/")
    auth_client.cookies.clear()
    assert r.status_code == 200


def test_api_accessible_with_valid_session(auth_client):
    token = create_session_token()
    auth_client.cookies.set(SESSION_COOKIE, token)
    r = auth_client.get("/api/metrics/latency")
    auth_client.cookies.clear()
    assert r.status_code == 200


def test_csrf_blocks_post_wrong_origin(auth_client):
    token = create_session_token()
    auth_client.cookies.set(SESSION_COOKIE, token)
    r = auth_client.post(
        "/settings",
        data={"dns_preset": "quad9_tls", "route_preset": "full_tunnel"},
        headers={"origin": "http://evil.com"},
    )
    auth_client.cookies.clear()
    assert r.status_code == 403


def test_csrf_allows_post_from_localhost(auth_client):
    token = create_session_token()
    auth_client.cookies.set(SESSION_COOKIE, token)
    r = auth_client.post(
        "/settings",
        data={"dns_preset": "quad9_tls", "route_preset": "full_tunnel"},
        headers={"origin": "http://127.0.0.1:9090"},
    )
    auth_client.cookies.clear()
    assert r.status_code in (200, 303)


def test_logout_clears_session_cookie(auth_client):
    token = create_session_token()
    auth_client.cookies.set(SESSION_COOKIE, token)
    r = auth_client.post(
        "/logout",
        headers={"origin": "http://127.0.0.1:9090"},
    )
    auth_client.cookies.clear()
    assert r.status_code == 303
    assert r.cookies.get(SESSION_COOKIE, "") == ""
