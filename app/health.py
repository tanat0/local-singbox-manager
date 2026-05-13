from __future__ import annotations
import asyncio
import socket
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

from app.logging_config import get_logger

_log = get_logger(__name__)


@dataclass
class CheckResult:
    name: str
    ok: bool
    latency_ms: Optional[float]
    detail: str
    category: str = "connectivity"   # "system" | "connectivity"


@dataclass
class HealthReport:
    overall: str   # connected | degraded | failed
    checks: List[CheckResult]
    external_ip: Optional[str]

    @property
    def system_checks(self) -> List[CheckResult]:
        return [c for c in self.checks if c.category == "system"]

    @property
    def connectivity_checks(self) -> List[CheckResult]:
        return [c for c in self.checks if c.category == "connectivity"]


# ── System checks ────────────────────────────────────────────────────────────

async def check_service(unit: str = "sing-box.service") -> CheckResult:
    """Check whether the systemd unit is active."""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True, text=True, timeout=5,
            ),
        )
        active = result.stdout.strip() == "active"
        return CheckResult(
            f"Service ({unit})", ok=active,
            latency_ms=None,
            detail="active" if active else result.stdout.strip() or "inactive",
            category="system",
        )
    except Exception as e:
        return CheckResult(f"Service ({unit})", ok=False, latency_ms=None,
                           detail=str(e), category="system")


async def check_tun_interface(iface: str = "singtun0") -> CheckResult:
    """Check whether the TUN interface exists and is UP."""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["ip", "link", "show", iface],
                capture_output=True, text=True, timeout=5,
            ),
        )
        if result.returncode != 0:
            return CheckResult(f"TUN ({iface})", ok=False, latency_ms=None,
                               detail="interface not found", category="system")
        up = "state UP" in result.stdout or ",UP," in result.stdout
        detail = "UP" if up else "DOWN (sing-box not running or TUN not created)"
        return CheckResult(f"TUN ({iface})", ok=up, latency_ms=None,
                           detail=detail, category="system")
    except Exception as e:
        return CheckResult(f"TUN ({iface})", ok=False, latency_ms=None,
                           detail=str(e), category="system")


# ── Connectivity checks ──────────────────────────────────────────────────────

async def check_dns(hostname: str = "google.com") -> CheckResult:
    t0 = time.monotonic()
    try:
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, socket.getaddrinfo, hostname, None),
            timeout=5.0,
        )
        ms = round((time.monotonic() - t0) * 1000, 1)
        return CheckResult(f"DNS ({hostname})", ok=True, latency_ms=ms,
                           detail=f"Resolved in {ms:.0f}ms")
    except asyncio.TimeoutError:
        return CheckResult(f"DNS ({hostname})", ok=False, latency_ms=None,
                           detail="Timed out after 5s")
    except Exception as e:
        return CheckResult(f"DNS ({hostname})", ok=False, latency_ms=None, detail=str(e))


async def check_tcp(host: str = "1.1.1.1", port: int = 80) -> CheckResult:
    t0 = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=5.0,
        )
        ms = round((time.monotonic() - t0) * 1000, 1)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return CheckResult(f"TCP {host}:{port}", ok=True, latency_ms=ms,
                           detail=f"Connected in {ms:.0f}ms")
    except asyncio.TimeoutError:
        return CheckResult(f"TCP {host}:{port}", ok=False, latency_ms=None,
                           detail="Timed out after 5s")
    except Exception as e:
        return CheckResult(f"TCP {host}:{port}", ok=False, latency_ms=None, detail=str(e))


async def check_https(url: str = "https://www.google.com") -> CheckResult:
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            r = await client.get(url)
        ms = round((time.monotonic() - t0) * 1000, 1)
        ok = r.status_code < 400
        return CheckResult(f"HTTPS {url}", ok=ok, latency_ms=ms,
                           detail=f"HTTP {r.status_code} in {ms:.0f}ms")
    except asyncio.TimeoutError:
        return CheckResult(f"HTTPS {url}", ok=False, latency_ms=None, detail="Timed out after 8s")
    except Exception as e:
        return CheckResult(f"HTTPS {url}", ok=False, latency_ms=None, detail=str(e))


# ── External IP ──────────────────────────────────────────────────────────────

_IP_PROVIDERS = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://ipinfo.io/ip",
]


async def check_external_ip() -> tuple[Optional[str], str]:
    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
        for url in _IP_PROVIDERS:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    ip = r.text.strip()
                    if ip:
                        return ip, ""
            except Exception:
                continue
    return None, "all IP providers unreachable"


# ── Combined runner ──────────────────────────────────────────────────────────

async def run_health_checks() -> HealthReport:
    results = await asyncio.gather(
        check_service(),
        check_tun_interface(),
        check_dns("google.com"),
        check_tcp("1.1.1.1", 80),
        check_https("https://www.google.com"),
        return_exceptions=False,
    )
    checks: List[CheckResult] = list(results)
    ip, _ = await check_external_ip()

    connectivity = [c for c in checks if c.category == "connectivity"]
    conn_passed = sum(1 for c in connectivity if c.ok)
    all_passed = all(c.ok for c in checks)

    if all_passed:
        overall = "connected"
    elif conn_passed >= 1:
        overall = "degraded"
    else:
        overall = "failed"

    if overall != "connected":
        failed_names = [c.name for c in checks if not c.ok]
        _log.warning("Health %s — failing: %s", overall, ", ".join(failed_names))

    return HealthReport(overall=overall, checks=checks, external_ip=ip)
