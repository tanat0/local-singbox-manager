"""
Notification dispatch — fire-and-forget, best-effort.

Channels:
  notify-send  — always attempted (desktop, no config needed)
  Telegram     — enabled when TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID are set
  ntfy.sh      — enabled when NTFY_TOPIC is set;
                 NTFY_SERVER overrides the default ntfy.sh endpoint

Levels: "info" | "warning" | "critical"
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from typing import Dict

import httpx

from app.logging_config import get_logger

_log = get_logger(__name__)

# ── Runtime config (patched in tests via patch.object) ───────────────────────

TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str   = os.environ.get("TELEGRAM_CHAT_ID", "")
NTFY_TOPIC: str          = os.environ.get("NTFY_TOPIC", "")
NTFY_SERVER: str         = os.environ.get("NTFY_SERVER", "https://ntfy.sh")

# ── Per-level mappings ────────────────────────────────────────────────────────

_NTFY_PRIORITY: Dict[str, str] = {
    "info":     "default",
    "warning":  "high",
    "critical": "urgent",
}
_SEND_URGENCY: Dict[str, str] = {
    "info":     "normal",
    "warning":  "normal",
    "critical": "critical",
}
_NTFY_TAGS: Dict[str, str] = {
    "info":     "white_check_mark",
    "warning":  "warning",
    "critical": "rotating_light",
}


# ── Channel implementations ──────────────────────────────────────────────────

def _notify_send_sync(title: str, body: str, urgency: str) -> None:
    subprocess.run(
        ["notify-send", "-a", "Sing-Box Manager", "-u", urgency, title, body],
        capture_output=True, timeout=3,
    )


async def _notify_send(title: str, body: str, level: str) -> None:
    urgency = _SEND_URGENCY.get(level, "normal")
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _notify_send_sync, title, body, urgency)
    except Exception:
        pass  # binary missing or no DBUS session — silently skip


async def _telegram(title: str, body: str) -> None:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    text = f"<b>{title}</b>\n{body}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            )
            if r.status_code != 200:
                _log.warning("Telegram notification HTTP %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        _log.warning("Telegram notification failed: %s", e)


async def _ntfy(title: str, body: str, level: str) -> None:
    if not NTFY_TOPIC:
        return
    url = f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}"
    priority = _NTFY_PRIORITY.get(level, "default")
    tags = _NTFY_TAGS.get(level, "bell")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(
                url,
                content=body.encode(),
                headers={"Title": title, "Priority": priority, "Tags": tags},
            )
            if r.status_code not in (200, 201):
                _log.warning("ntfy notification HTTP %s", r.status_code)
    except Exception as e:
        _log.warning("ntfy notification failed: %s", e)


# ── Dispatcher ───────────────────────────────────────────────────────────────

async def _dispatch(title: str, body: str, level: str) -> None:
    await asyncio.gather(
        _notify_send(title, body, level),
        _telegram(title, body),
        _ntfy(title, body, level),
        return_exceptions=True,
    )


def fire(title: str, body: str, level: str = "info") -> None:
    """Schedule a notification as a fire-and-forget asyncio task.

    Safe to call from any async context (request handler, background task).
    No-op if the event loop is not running (e.g. during unit tests).
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_dispatch(title, body, level))
    except Exception:
        pass


# ── Status introspection (for Settings UI) ───────────────────────────────────

def channels_status() -> Dict[str, object]:
    """Return which notification channels are configured."""
    return {
        "notify_send": shutil.which("notify-send") is not None,
        "telegram": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "telegram_chat_id": TELEGRAM_CHAT_ID if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID else "",
        "ntfy": bool(NTFY_TOPIC),
        "ntfy_server": NTFY_SERVER if NTFY_TOPIC else "",
        "ntfy_topic": NTFY_TOPIC,
    }
