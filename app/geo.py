from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from app.logging_config import get_logger

_log = get_logger(__name__)


@dataclass
class GeoInfo:
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    provider_suggestion: Optional[str] = None


async def lookup_node_geo(server: str) -> GeoInfo:
    """Best-effort one-shot geo lookup. Failure must not block node creation."""
    if not server:
        return GeoInfo()
    url = f"https://ipapi.co/{server}/json/"
    try:
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
            resp = await client.get(url)
        if resp.status_code >= 400:
            return GeoInfo()
        data = resp.json()
        if data.get("error"):
            return GeoInfo()
        return GeoInfo(
            country_code=(data.get("country_code") or "")[:8] or None,
            country_name=data.get("country_name") or None,
            provider_suggestion=data.get("org") or data.get("asn") or None,
        )
    except Exception as exc:
        _log.info("Geo lookup skipped for %s: %s", server, exc)
        return GeoInfo()
