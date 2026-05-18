from __future__ import annotations

from typing import Optional, Set

from app.config import parse_id_set
from app.telegram.bot import (
    TELEGRAM_ADMIN_BOT_ENABLED as _TELEGRAM_ADMIN_BOT_ENABLED,
    TELEGRAM_ADMIN_IDS_RAW as _TELEGRAM_ADMIN_IDS_RAW,
    TELEGRAM_BOT_TOKEN as _TELEGRAM_BOT_TOKEN,
    TelegramBotRunner,
    build_dispatcher,
    command_parts as _command_parts,
    create_bot_from_env,
    handle_message,
)
from app.telegram.client import TelegramApiClient

TELEGRAM_BOT_TOKEN = _TELEGRAM_BOT_TOKEN
TELEGRAM_ADMIN_IDS_RAW = _TELEGRAM_ADMIN_IDS_RAW
TELEGRAM_ADMIN_BOT_ENABLED = _TELEGRAM_ADMIN_BOT_ENABLED


def parse_admin_ids(raw: Optional[str] = None) -> Set[int]:
    return parse_id_set(TELEGRAM_ADMIN_IDS_RAW if raw is None else raw)


def is_enabled() -> bool:
    return (
        TELEGRAM_ADMIN_BOT_ENABLED.lower() not in {"0", "false", "no", "off"}
        and bool(TELEGRAM_BOT_TOKEN)
        and bool(parse_admin_ids())
    )


class TelegramAdminBot(TelegramBotRunner):
    def __init__(self, token: str, admin_ids: Set[int]) -> None:
        super().__init__(TelegramApiClient(token), build_dispatcher(admin_ids))

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
