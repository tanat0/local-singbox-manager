from __future__ import annotations
import asyncio
import socket
import time
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class CheckResult:
    name: str
    ok: bool
    latency_ms: Optional[float]
    detail: str


@dataclass
class HealthReport:
    overall: str   # connected | degraded | failed
    checks: list[CheckResult]
    external_ip: Optional[str]


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


async def check_external_ip() -> tuple[Optional[str], str]:
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.get("https://api.ipify.org")
            return r.text.strip(), ""
    except Exception as e:
        return None, str(e)


async def run_health_checks() -> HealthReport:
    results = await asyncio.gather(
        check_dns("google.com"),
        check_tcp("1.1.1.1", 80),
        check_https("https://www.google.com"),
        return_exceptions=False,
    )
    checks: list[CheckResult] = list(results)
    ip, _ = await check_external_ip()

    passed = sum(1 for c in checks if c.ok)
    overall = "connected" if passed == 3 else ("degraded" if passed >= 1 else "failed")
    return HealthReport(overall=overall, checks=checks, external_ip=ip)
