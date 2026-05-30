"""
Unit tests for app/notify.py.

All HTTP calls and subprocess.run are mocked — no real network or system calls.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import notify

# ── channels_status ───────────────────────────────────────────────────────────

def test_channels_status_notify_send_available():
    with patch("shutil.which", return_value="/usr/bin/notify-send"):
        s = notify.channels_status()
    assert s["notify_send"] is True


def test_channels_status_notify_send_missing():
    with patch("shutil.which", return_value=None):
        s = notify.channels_status()
    assert s["notify_send"] is False


def test_channels_status_telegram_disabled_by_default():
    with patch.object(notify, "TELEGRAM_BOT_TOKEN", ""), \
         patch.object(notify, "TELEGRAM_CHAT_ID", ""):
        s = notify.channels_status()
    assert s["telegram"] is False


def test_channels_status_telegram_enabled():
    with patch.object(notify, "TELEGRAM_BOT_TOKEN", "mytoken"), \
         patch.object(notify, "TELEGRAM_CHAT_ID", "99999"):
        s = notify.channels_status()
    assert s["telegram"] is True
    assert s["telegram_chat_id"] == "99999"


def test_channels_status_ntfy_disabled_by_default():
    with patch.object(notify, "NTFY_TOPIC", ""):
        s = notify.channels_status()
    assert s["ntfy"] is False
    assert s["ntfy_server"] == ""


def test_channels_status_ntfy_enabled():
    with patch.object(notify, "NTFY_TOPIC", "singbox"), \
         patch.object(notify, "NTFY_SERVER", "https://ntfy.sh"):
        s = notify.channels_status()
    assert s["ntfy"] is True
    assert s["ntfy_topic"] == "singbox"
    assert "ntfy.sh" in s["ntfy_server"]


# ── _notify_send ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_send_calls_subprocess():
    with patch("app.notify._notify_send_sync") as m:
        await notify._notify_send("Title", "Body", "info")
    m.assert_called_once_with("Title", "Body", "normal")


@pytest.mark.asyncio
async def test_notify_send_critical_uses_critical_urgency():
    with patch("app.notify._notify_send_sync") as m:
        await notify._notify_send("T", "B", "critical")
    m.assert_called_once_with("T", "B", "critical")


@pytest.mark.asyncio
async def test_notify_send_silently_ignores_errors():
    with patch("app.notify._notify_send_sync", side_effect=FileNotFoundError):
        await notify._notify_send("T", "B", "info")  # must not raise


def test_notify_send_sync_builds_correct_command():
    with patch("subprocess.run") as m:
        notify._notify_send_sync("My Title", "My Body", "critical")
    cmd = m.call_args[0][0]
    assert "notify-send" in cmd
    assert "-u" in cmd
    assert "critical" in cmd
    assert "My Title" in cmd
    assert "My Body" in cmd


# ── _telegram ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_telegram_skips_when_no_credentials():
    with patch.object(notify, "TELEGRAM_BOT_TOKEN", ""), \
         patch.object(notify, "TELEGRAM_CHAT_ID", ""), \
         patch("app.notify.httpx.AsyncClient") as m:
        await notify._telegram("T", "B")
    m.assert_not_called()


@pytest.mark.asyncio
async def test_telegram_posts_to_correct_url():
    mock_resp = MagicMock(status_code=200)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(notify, "TELEGRAM_BOT_TOKEN", "tok123"), \
         patch.object(notify, "TELEGRAM_CHAT_ID", "42"), \
         patch("app.notify.httpx.AsyncClient", return_value=mock_client):
        await notify._telegram("Hello", "World")

    url, kwargs = mock_client.post.call_args[0][0], mock_client.post.call_args[1]
    assert "tok123" in url
    assert "sendMessage" in url
    assert kwargs["json"]["chat_id"] == "42"
    assert "<b>Hello</b>" in kwargs["json"]["text"]
    assert "World" in kwargs["json"]["text"]


@pytest.mark.asyncio
async def test_telegram_logs_warning_on_http_error():
    mock_resp = MagicMock(status_code=401, text="Unauthorized")
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(notify, "TELEGRAM_BOT_TOKEN", "bad"), \
         patch.object(notify, "TELEGRAM_CHAT_ID", "1"), \
         patch("app.notify.httpx.AsyncClient", return_value=mock_client):
        await notify._telegram("T", "B")  # should not raise


@pytest.mark.asyncio
async def test_telegram_logs_warning_on_network_error():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("connection refused"))

    with patch.object(notify, "TELEGRAM_BOT_TOKEN", "tok"), \
         patch.object(notify, "TELEGRAM_CHAT_ID", "1"), \
         patch("app.notify.httpx.AsyncClient", return_value=mock_client):
        await notify._telegram("T", "B")  # should not raise


# ── _ntfy ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ntfy_skips_when_no_topic():
    with patch.object(notify, "NTFY_TOPIC", ""), \
         patch("app.notify.httpx.AsyncClient") as m:
        await notify._ntfy("T", "B", "info")
    m.assert_not_called()


@pytest.mark.asyncio
async def test_ntfy_posts_to_correct_url():
    mock_resp = MagicMock(status_code=200)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(notify, "NTFY_TOPIC", "my-alerts"), \
         patch.object(notify, "NTFY_SERVER", "https://ntfy.sh"), \
         patch("app.notify.httpx.AsyncClient", return_value=mock_client):
        await notify._ntfy("Hello", "World", "warning")

    url = mock_client.post.call_args[0][0]
    headers = mock_client.post.call_args[1]["headers"]
    assert "my-alerts" in url
    assert "ntfy.sh" in url
    assert headers["Title"] == "Hello"
    assert headers["Priority"] == "high"   # warning → high


@pytest.mark.asyncio
async def test_ntfy_priority_mapping():
    mock_resp = MagicMock(status_code=200)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    for level, expected_priority in [("info", "default"), ("warning", "high"), ("critical", "urgent")]:
        mock_client.post.reset_mock()
        with patch.object(notify, "NTFY_TOPIC", "topic"), \
             patch.object(notify, "NTFY_SERVER", "https://ntfy.sh"), \
             patch("app.notify.httpx.AsyncClient", return_value=mock_client):
            await notify._ntfy("T", "B", level)
        headers = mock_client.post.call_args[1]["headers"]
        assert headers["Priority"] == expected_priority, f"level={level}"


@pytest.mark.asyncio
async def test_ntfy_uses_custom_server():
    mock_resp = MagicMock(status_code=200)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(notify, "NTFY_TOPIC", "alerts"), \
         patch.object(notify, "NTFY_SERVER", "https://ntfy.myserver.com"), \
         patch("app.notify.httpx.AsyncClient", return_value=mock_client):
        await notify._ntfy("T", "B", "info")

    url = mock_client.post.call_args[0][0]
    assert "myserver.com" in url


@pytest.mark.asyncio
async def test_ntfy_silently_ignores_network_error():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("timeout"))

    with patch.object(notify, "NTFY_TOPIC", "alerts"), \
         patch("app.notify.httpx.AsyncClient", return_value=mock_client):
        await notify._ntfy("T", "B", "info")  # must not raise


# ── _dispatch ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_calls_all_channels():
    with patch.object(notify, "_notify_send", AsyncMock()) as m_ns, \
         patch.object(notify, "_telegram", AsyncMock()) as m_tg, \
         patch.object(notify, "_ntfy", AsyncMock()) as m_nt:
        await notify._dispatch("T", "B", "info")

    m_ns.assert_awaited_once_with("T", "B", "info")
    m_tg.assert_awaited_once_with("T", "B")
    m_nt.assert_awaited_once_with("T", "B", "info")


@pytest.mark.asyncio
async def test_dispatch_resilient_to_one_channel_failing():
    with patch.object(notify, "_notify_send", AsyncMock(side_effect=Exception("boom"))), \
         patch.object(notify, "_telegram", AsyncMock()) as m_tg, \
         patch.object(notify, "_ntfy", AsyncMock()) as m_nt:
        await notify._dispatch("T", "B", "info")  # must not raise

    m_tg.assert_awaited_once()
    m_nt.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_resilient_to_all_channels_failing():
    with patch.object(notify, "_notify_send", AsyncMock(side_effect=Exception)), \
         patch.object(notify, "_telegram", AsyncMock(side_effect=Exception)), \
         patch.object(notify, "_ntfy", AsyncMock(side_effect=Exception)):
        await notify._dispatch("T", "B", "critical")  # must not raise


# ── fire ─────────────────────────────────────────────────────────────────────

def test_fire_schedules_task_when_loop_running():
    async def run():
        dispatched = []

        async def fake_dispatch(title, body, level):
            dispatched.append((title, body, level))

        with patch.object(notify, "_dispatch", fake_dispatch):
            notify.fire("T", "B", "warning")
            await asyncio.sleep(0)   # yield to let the task run

        assert dispatched == [("T", "B", "warning")]

    asyncio.run(run())


def test_fire_is_noop_outside_event_loop():
    # Should not raise even when there's no running loop
    with patch.object(notify, "_dispatch", AsyncMock()):
        notify.fire("T", "B")   # called synchronously, outside any async context
