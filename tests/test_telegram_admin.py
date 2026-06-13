from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import telegram_admin as tg
from app.services.distribution import UserAssignment
from app.telegram.bot import TelegramBotRunner
from app.telegram.client import TelegramApiClient
from app.telegram.dispatcher import TelegramDispatcher
from app.telegram.handlers import AdminCommandHandler, AdminHandlerDeps, UserCommandHandler, UserHandlerDeps
from app.telegram.types import BotResponse, ParsedCommand, TelegramDocument, TelegramMessage


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
async def test_dispatcher_routes_admin():
    admin_handler = MagicMock()
    admin_handler.handle = AsyncMock(return_value=BotResponse(True, "admin ok"))
    user_handler = MagicMock()
    user_handler.handle = AsyncMock(return_value=BotResponse(True, "user ok"))
    dispatcher = TelegramDispatcher({42}, admin_handler, user_handler)

    response = await dispatcher.handle(TelegramMessage(actor_id=42, chat_id=42, text="/status"))

    assert response == BotResponse(True, "admin ok")
    admin_handler.handle.assert_awaited_once()
    user_handler.handle.assert_not_called()


@pytest.mark.asyncio
async def test_dispatcher_routes_user():
    admin_handler = MagicMock()
    admin_handler.handle = AsyncMock(return_value=BotResponse(True, "admin ok"))
    user_handler = MagicMock()
    user_handler.handle = AsyncMock(return_value=BotResponse(True, "user ok"))
    dispatcher = TelegramDispatcher({42}, admin_handler, user_handler)

    response = await dispatcher.handle(TelegramMessage(actor_id=99, chat_id=99, text="/config"))

    assert response == BotResponse(True, "user ok")
    admin_handler.handle.assert_not_called()
    user_handler.handle.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_handler_config():
    user = MagicMock(id=1, telegram_id="99", display_name="Alex")
    group = MagicMock(id=2, name="family")
    node = MagicMock(tag="node-a", protocol="vless", raw_url="vless://example")
    assignment = UserAssignment(user=user, group=group, nodes=[node], config_version=4, config_fingerprint="c" * 64)
    db = MagicMock()
    handler = UserCommandHandler(UserHandlerDeps(session_factory=lambda: db))

    with patch("app.telegram.handlers.get_user_assignment", return_value=assignment), \
         patch("app.telegram.handlers.refresh_limit_exceeded", return_value=False), \
         patch("app.telegram.handlers.build_client_config_document", return_value=SimpleNamespace(
             filename="singbox-family-v4.json",
             content=b"{}",
             mime_type="application/json",
             caption="config",
         )), \
         patch("app.telegram.handlers.record_delivery") as record_delivery:
        response = await handler.handle(
            TelegramMessage(actor_id=99, chat_id=99, text="/config"),
            ParsedCommand("/config"),
        )

    assert response.ok is True
    assert "vless://example" in response.text
    assert "node-a" in response.text
    assert "Version: 4" in response.text
    assert "cccccccccccc" in response.text
    assert response.document is not None
    assert response.document.filename == "singbox-family-v4.json"
    assert record_delivery.called
    assert db.close.called


@pytest.mark.asyncio
async def test_user_handler_config_rate_limited():
    user = MagicMock(id=1, telegram_id="99", display_name="Alex")
    group = MagicMock(id=2, name="family")
    assignment = UserAssignment(user=user, group=group, nodes=[], config_version=1, config_fingerprint="d" * 64)
    db = MagicMock()
    handler = UserCommandHandler(UserHandlerDeps(session_factory=lambda: db))

    with patch("app.telegram.handlers.get_user_assignment", return_value=assignment), \
         patch("app.telegram.handlers.refresh_limit_exceeded", return_value=True), \
         patch("app.telegram.handlers.record_delivery") as record_delivery:
        response = await handler.handle(
            TelegramMessage(actor_id=99, chat_id=99, text="/refresh"),
            ParsedCommand("/refresh"),
        )

    assert response.ok is False
    assert response.text == "Refresh limit reached. Try later."
    assert response.document is None
    record_delivery.assert_called_once()
    assert db.close.called


@pytest.mark.asyncio
async def test_user_handler_unregistered_user_denied():
    assignment = UserAssignment(user=None, group=None, nodes=[], error="User is not registered.")
    db = MagicMock()
    handler = UserCommandHandler(UserHandlerDeps(session_factory=lambda: db))

    with patch("app.telegram.handlers.get_user_assignment", return_value=assignment), \
         patch("app.telegram.handlers.record_delivery") as record_delivery:
        response = await handler.handle(
            TelegramMessage(actor_id=77, chat_id=77, text="/config"),
            ParsedCommand("/config"),
        )

    assert response.ok is False
    assert response.text == "Access denied."
    assert response.document is None
    assert record_delivery.called
    assert db.close.called


@pytest.mark.asyncio
async def test_admin_handler_help():
    db = MagicMock()
    handler = AdminCommandHandler(AdminHandlerDeps(
        session_factory=lambda: db,
        external_ip_checker=AsyncMock(return_value=("1.2.3.4", "")),
        health_checker=AsyncMock(),
    ))

    response = await handler.handle(
        TelegramMessage(actor_id=42, chat_id=42, text="/help"),
        ParsedCommand("/help"),
    )

    assert response.ok is True
    assert "/status" in response.text
    assert "/activate" in response.text
    assert db.close.called


@pytest.mark.asyncio
async def test_admin_handler_status():
    db = MagicMock()
    node = MagicMock(tag="node-a")
    db.query.return_value.filter.return_value.first.return_value = node
    handler = AdminCommandHandler(AdminHandlerDeps(
        session_factory=lambda: db,
        status_provider=lambda: {
            "active_state": "active",
            "sub_state": "running",
            "pid": "123",
            "since": "",
        },
        external_ip_checker=AsyncMock(return_value=("1.2.3.4", "")),
        health_checker=AsyncMock(),
    ))

    response = await handler.handle(
        TelegramMessage(actor_id=42, chat_id=42, text="/status"),
        ParsedCommand("/status"),
    )

    assert response.ok is True
    assert "active/running" in response.text
    assert "1.2.3.4" in response.text


@pytest.mark.asyncio
async def test_telegram_client_send_message_splits_long_text():
    client = TelegramApiClient("token")
    client._post = AsyncMock(return_value={"ok": True})  # type: ignore[assignment]

    await client.send_message(42, "x" * 8000)

    assert client._post.await_count == 3
    first_payload = client._post.await_args_list[0].args[1]
    assert first_payload["chat_id"] == 42
    assert len(first_payload["text"]) == 3900


@pytest.mark.asyncio
async def test_telegram_client_send_document_uploads_multipart():
    client = TelegramApiClient("token")
    client._post_multipart = AsyncMock(return_value={"ok": True})  # type: ignore[assignment]

    await client.send_document(42, "config.json", b"{}", "application/json", caption="caption")

    client._post_multipart.assert_awaited_once()
    method, data, files = client._post_multipart.await_args.args
    assert method == "sendDocument"
    assert data == {"chat_id": 42, "caption": "caption"}
    assert files["document"] == ("config.json", b"{}", "application/json")


@pytest.mark.asyncio
async def test_bot_runner_sends_document_after_message():
    client = MagicMock()
    client.get_updates = AsyncMock(return_value=[{
        "update_id": 1,
        "message": {"from": {"id": 99}, "chat": {"id": 99}, "text": "/config"},
    }])
    client.send_message = AsyncMock()
    client.send_document = AsyncMock()
    dispatcher = MagicMock()
    dispatcher.handle = AsyncMock(return_value=BotResponse(
        True,
        "config ready",
        document=TelegramDocument("config.json", b"{}", "application/json", "caption"),
    ))
    runner = TelegramBotRunner(client, dispatcher, poll_timeout=0)

    await runner.poll_once()

    client.send_message.assert_awaited_once_with(99, "config ready")
    client.send_document.assert_awaited_once_with(99, "config.json", b"{}", "application/json", caption="caption")
