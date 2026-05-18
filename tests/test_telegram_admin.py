from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import telegram_admin as tg
from app.services.distribution import UserAssignment


def test_parse_admin_ids_accepts_commas_and_semicolons():
    assert tg.parse_admin_ids("1, 2;3,,bad") == {1, 2, 3}


def test_command_parts_strips_bot_username():
    assert tg._command_parts("/activate@my_bot node-a") == ("/activate", "node-a")


def test_is_enabled_requires_token_and_admin_ids():
    with patch.object(tg, "TELEGRAM_BOT_TOKEN", "token"), \
         patch.object(tg, "TELEGRAM_ADMIN_IDS_RAW", "42"), \
         patch.object(tg, "TELEGRAM_ADMIN_BOT_ENABLED", "1"):
        assert tg.is_enabled() is True

    with patch.object(tg, "TELEGRAM_BOT_TOKEN", "token"), \
         patch.object(tg, "TELEGRAM_ADMIN_IDS_RAW", ""), \
         patch.object(tg, "TELEGRAM_ADMIN_BOT_ENABLED", "1"):
        assert tg.is_enabled() is False


@pytest.mark.asyncio
async def test_handle_message_rejects_unknown_user():
    db = MagicMock()
    assignment = UserAssignment(user=None, group=None, nodes=[], error="User is not registered.")
    with patch.object(tg, "_session", return_value=db), \
         patch("app.services.distribution.get_user_assignment", return_value=assignment), \
         patch("app.services.distribution.record_delivery"), \
         patch.object(tg, "_log_admin_action") as log_action:
        response = await tg.handle_message(
            {"from": {"id": 99}, "chat": {"id": 99}, "text": "/status"},
            admin_ids={42},
        )
    assert response == "Access denied."
    assert log_action.called
    assert db.close.called


@pytest.mark.asyncio
async def test_handle_message_user_config():
    user = MagicMock(id=1, telegram_id="99", display_name="Alex")
    group = MagicMock(id=2, name="family")
    node = MagicMock(tag="node-a", protocol="vless", raw_url="vless://example")
    assignment = UserAssignment(user=user, group=group, nodes=[node])
    db = MagicMock()

    with patch.object(tg, "_session", return_value=db), \
         patch("app.services.distribution.get_user_assignment", return_value=assignment), \
         patch("app.services.distribution.record_delivery") as record_delivery:
        response = await tg.handle_message(
            {"from": {"id": 99}, "chat": {"id": 99}, "text": "/config"},
            admin_ids={42},
        )

    assert response is not None
    assert "vless://example" in response
    assert "node-a" in response
    assert record_delivery.called
    assert db.close.called


@pytest.mark.asyncio
async def test_handle_message_unregistered_user_denied():
    assignment = UserAssignment(user=None, group=None, nodes=[], error="User is not registered.")
    db = MagicMock()

    with patch.object(tg, "_session", return_value=db), \
         patch("app.services.distribution.get_user_assignment", return_value=assignment), \
         patch("app.services.distribution.record_delivery"), \
         patch.object(tg, "_log_admin_action") as log_action:
        response = await tg.handle_message(
            {"from": {"id": 77}, "chat": {"id": 77}, "text": "/config"},
            admin_ids={42},
        )

    assert response == "Access denied."
    assert log_action.called


@pytest.mark.asyncio
async def test_handle_message_help_for_admin():
    db = MagicMock()
    with patch.object(tg, "_session", return_value=db):
        response = await tg.handle_message(
            {"from": {"id": 42}, "chat": {"id": 42}, "text": "/help"},
            admin_ids={42},
        )
    assert response is not None
    assert "/status" in response
    assert "/activate" in response
    assert db.close.called


@pytest.mark.asyncio
async def test_handle_message_status_for_admin():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch.object(tg, "_session", return_value=db), \
         patch.object(tg, "_get_active_node", return_value=None), \
         patch.object(tg, "_log_admin_action"), \
         patch.object(tg.svc, "get_status", return_value={
             "active_state": "active",
             "sub_state": "running",
             "pid": "123",
             "since": "",
         }), \
         patch.object(tg, "check_external_ip", AsyncMock(return_value=("1.2.3.4", ""))):
        response = await tg.handle_message(
            {"from": {"id": 42}, "chat": {"id": 42}, "text": "/status"},
            admin_ids={42},
        )
    assert response is not None
    assert "active/running" in response
    assert "1.2.3.4" in response


@pytest.mark.asyncio
async def test_send_message_splits_long_text():
    bot = tg.TelegramAdminBot("token", {42})
    bot._post = AsyncMock(return_value={"ok": True})  # type: ignore[assignment]

    await bot.send_message(42, "x" * 8000)

    assert bot._post.await_count == 3
    first_payload = bot._post.await_args_list[0].args[1]
    assert first_payload["chat_id"] == 42
    assert len(first_payload["text"]) == 3900
