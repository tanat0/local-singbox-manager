from __future__ import annotations

from typing import Optional, Set

from app.config import parse_id_set
from app.telegram import bot as telegram_bot
from app.telegram.client import TelegramApiClient

TELEGRAM_BOT_TOKEN = telegram_bot.TELEGRAM_BOT_TOKEN
TELEGRAM_ADMIN_IDS_RAW = telegram_bot.TELEGRAM_ADMIN_IDS_RAW
TELEGRAM_ADMIN_BOT_ENABLED = telegram_bot.TELEGRAM_ADMIN_BOT_ENABLED
_command_parts = telegram_bot.command_parts
create_bot_from_env = telegram_bot.create_bot_from_env
handle_message = telegram_bot.handle_message


def parse_admin_ids(raw: Optional[str] = None) -> Set[int]:
    return parse_id_set(TELEGRAM_ADMIN_IDS_RAW if raw is None else raw)


def is_enabled() -> bool:
    return (
        TELEGRAM_ADMIN_BOT_ENABLED.lower() not in {"0", "false", "no", "off"}
        and bool(TELEGRAM_BOT_TOKEN)
        and bool(parse_admin_ids())
    )


class TelegramAdminBot(telegram_bot.TelegramBotRunner):
    def __init__(self, token: str, admin_ids: Set[int]) -> None:
        super().__init__(TelegramApiClient(token), telegram_bot.build_dispatcher(admin_ids))

__all__ = [
    "TELEGRAM_ADMIN_BOT_ENABLED",
    "TELEGRAM_ADMIN_IDS_RAW",
    "TELEGRAM_BOT_TOKEN",
    "TelegramAdminBot",
    "_command_parts",
    "create_bot_from_env",
    "handle_message",
    "is_enabled",
    "parse_admin_ids",
]
