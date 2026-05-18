from __future__ import annotations

import asyncio
from typing import Optional, Set

from app.config import settings
from app.db import SessionLocal
from app.health import check_external_ip, run_health_checks
from app.logging_config import get_logger
from app.telegram.client import TelegramApiClient
from app.telegram.dispatcher import TelegramDispatcher
from app.telegram.handlers import AdminCommandHandler, AdminHandlerDeps, UserCommandHandler, UserHandlerDeps
from app.telegram.types import TelegramMessage, command_parts

_log = get_logger(__name__)
_POLL_TIMEOUT = 25
_POLL_BACKOFF = 5

TELEGRAM_BOT_TOKEN = settings.telegram.bot_token
TELEGRAM_ADMIN_IDS_RAW = settings.telegram.admin_ids_raw
TELEGRAM_ADMIN_BOT_ENABLED = "1" if settings.telegram.admin_bot_enabled else "0"


def parse_admin_ids(raw: Optional[str] = None) -> Set[int]:
    from app.config import parse_id_set

    return parse_id_set(TELEGRAM_ADMIN_IDS_RAW if raw is None else raw)


def is_enabled() -> bool:
    return (
        TELEGRAM_ADMIN_BOT_ENABLED.lower() not in {"0", "false", "no", "off"}
        and bool(TELEGRAM_BOT_TOKEN)
        and bool(parse_admin_ids())
    )


def build_dispatcher(admin_ids: Set[int]) -> TelegramDispatcher:
    admin_deps = AdminHandlerDeps(
        session_factory=SessionLocal,
        external_ip_checker=check_external_ip,
        health_checker=run_health_checks,
    )
    return TelegramDispatcher(
        admin_ids,
        AdminCommandHandler(admin_deps),
        UserCommandHandler(UserHandlerDeps(session_factory=SessionLocal)),
    )


async def handle_message(message: dict, admin_ids: Set[int]) -> Optional[str]:
    return await build_dispatcher(admin_ids).handle(TelegramMessage.from_api_message(message))


class TelegramBotRunner:
    def __init__(
        self,
        client: TelegramApiClient,
        dispatcher: TelegramDispatcher,
        poll_timeout: int = _POLL_TIMEOUT,
    ) -> None:
        self._client = client
        self._dispatcher = dispatcher
        self._poll_timeout = poll_timeout
        self.offset: Optional[int] = None

    async def send_message(self, chat_id: int, text: str) -> None:
        await self._client.send_message(chat_id, text)

    async def poll_once(self) -> None:
        updates = await self._client.get_updates(self.offset, self._poll_timeout, ["message"])
        for update in updates:
            self.offset = int(update["update_id"]) + 1
            message = update.get("message") or {}
            tg_message = TelegramMessage.from_api_message(message)
            if tg_message.chat_id is None:
                continue
            response = await self._dispatcher.handle(tg_message)
            if response:
                await self.send_message(tg_message.chat_id, response)

    async def run_forever(self) -> None:
        _log.info("Telegram bot polling started")
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _log.warning("Telegram bot polling error: %s", e)
                await asyncio.sleep(_POLL_BACKOFF)


def create_bot_from_env() -> Optional[TelegramBotRunner]:
    if not is_enabled():
        return None
    admin_ids = parse_admin_ids()
    return TelegramBotRunner(TelegramApiClient(TELEGRAM_BOT_TOKEN), build_dispatcher(admin_ids))
