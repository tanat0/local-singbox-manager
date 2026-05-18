"""
Authentication and security primitives.

Design:
  - SINGLE_ADMIN_PASSWORD env var  → enables auth (if absent: open panel + big warning)
  - SESSION_SECRET env var         → signs cookies (if absent: random ephemeral key)
  - Stateless signed session cookie (HMAC-SHA256, stdlib only, no extra deps)
  - CSRF: Origin/Referer header check (no token to manage, no body read needed)
  - Rate limit: in-memory per-IP attempt tracking with cleanup
  - API routes (/api/*) get 401 JSON; page routes get redirect to /login
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict
from typing import Dict, List

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.logging_config import get_logger
from app.config import settings

_log = get_logger(__name__)

# ── Config from environment ───────────────────────────────────────────────────

ADMIN_PASSWORD: str = settings.security.admin_password
SESSION_COOKIE = "sb_session"
SESSION_MAX_AGE = 30 * 24 * 3600  # 30 days

# If SESSION_SECRET is not set, generate an ephemeral one (sessions reset on restart).
_raw_secret = settings.security.session_secret
SESSION_SECRET: str = _raw_secret or secrets.token_hex(32)

AUTH_ENABLED: bool = bool(ADMIN_PASSWORD)

# ── Startup warnings ──────────────────────────────────────────────────────────

def emit_startup_warnings() -> None:
    if not AUTH_ENABLED:
        _log.warning("=" * 62)
        _log.warning("  ⚠  NO PASSWORD SET — PANEL IS COMPLETELY UNPROTECTED  ⚠")
        _log.warning("  Set SINGLE_ADMIN_PASSWORD env var to enable authentication.")
        _log.warning("  Anyone with access to this host can control sing-box.")
        _log.warning("=" * 62)
    if not _raw_secret:
        _log.warning(
            "SESSION_SECRET not set — using ephemeral random key; "
            "all sessions will be invalidated on restart"
        )


# ── Session token (HMAC-SHA256, stateless) ────────────────────────────────────

def _sign_session(ts: int) -> str:
    msg = f"singbox-session:v1:{ts}"
    return hmac.new(SESSION_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


def create_session_token() -> str:
    ts = int(time.time())
    return f"{ts}.{_sign_session(ts)}"


def verify_session_token(token: str) -> bool:
    try:
        ts_str, sig = token.split(".", 1)
        ts = int(ts_str)
        age = time.time() - ts
        if not (0 <= age <= SESSION_MAX_AGE):
            return False
        expected = _sign_session(ts)
        return hmac.compare_digest(expected, sig)
    except (TypeError, ValueError):
        return False


# ── Password verification ─────────────────────────────────────────────────────

def verify_password(password: str) -> bool:
    if not ADMIN_PASSWORD:
        return False
    return hmac.compare_digest(ADMIN_PASSWORD.encode(), password.encode())


# ── Rate limiting ─────────────────────────────────────────────────────────────

_login_attempts: Dict[str, List[float]] = defaultdict(list)
_RATE_MAX = 5
_RATE_WINDOW = 60   # seconds
_CLEANUP_THRESHOLD = 500   # clean dict when it exceeds this many IPs


def rate_limit_ok(ip: str) -> bool:
    """Returns True if the attempt is within rate limit, recording it."""
    now = time.monotonic()

    # Periodic cleanup to prevent unbounded growth
    if len(_login_attempts) > _CLEANUP_THRESHOLD:
        stale = [k for k, v in _login_attempts.items()
                 if not any(now - t < _RATE_WINDOW for t in v)]
        for k in stale:
            del _login_attempts[k]

    recent = [t for t in _login_attempts[ip] if now - t < _RATE_WINDOW]
    if len(recent) >= _RATE_MAX:
        _login_attempts[ip] = recent
        return False
    recent.append(now)
    _login_attempts[ip] = recent
    return True


# ── Auth check ────────────────────────────────────────────────────────────────

def is_authenticated(request: Request) -> bool:
    if not AUTH_ENABLED:
        return True
    token = request.cookies.get(SESSION_COOKIE, "")
    return verify_session_token(token)


# ── CSRF: Origin / Referer check ──────────────────────────────────────────────
# Defends against cross-site form submissions. No token management needed.
# A malicious website cannot spoof the Origin header.
_ALLOWED_ORIGINS = ("http://127.0.0.1", "http://localhost")


def check_csrf(request: Request) -> bool:
    if not AUTH_ENABLED:
        return True   # auth disabled → skip CSRF too
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return True
    origin = request.headers.get("origin", "")
    referer = request.headers.get("referer", "")
    src = origin or referer
    if not src:
        return False  # no origin info → reject
    return any(src.startswith(o) for o in _ALLOWED_ORIGINS)


# ── Middleware ────────────────────────────────────────────────────────────────

# Paths that bypass auth entirely
_OPEN_PREFIXES = ("/static/", "/login", "/health", "/version")
# Paths that return JSON 401 (not redirect) when unauthenticated
_API_PREFIXES = ("/api/",)
# Paths that skip CSRF (API routes use 401, not CSRF redirect)
_CSRF_SKIP_PREFIXES = ("/api/", "/login", "/logout", "/static/", "/health", "/version")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always open: static assets, login form, health + version probes
        if any(path == p or path.startswith(p) for p in _OPEN_PREFIXES):
            return await call_next(request)

        # Auth check
        if not is_authenticated(request):
            if any(path.startswith(p) for p in _API_PREFIXES):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            from urllib.parse import quote
            return RedirectResponse(f"/login?next={quote(path)}", status_code=302)

        # CSRF check for state-changing methods on page routes
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if not any(path.startswith(p) for p in _CSRF_SKIP_PREFIXES):
                if not check_csrf(request):
                    _log.warning("CSRF check failed: %s %s origin=%s referer=%s",
                                 request.method, path,
                                 request.headers.get("origin", "-"),
                                 request.headers.get("referer", "-"))
                    return Response("CSRF validation failed", status_code=403)

        return await call_next(request)
