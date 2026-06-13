from __future__ import annotations

from typing import Optional, Set

from app.telegram.handlers import AdminCommandHandler, UserCommandHandler
from app.telegram.types import BotResponse, TelegramMessage, parse_command


class TelegramDispatcher:
    def __init__(
        self,
        admin_ids: Set[int],
        admin_handler: AdminCommandHandler,
        user_handler: UserCommandHandler,
    ) -> None:
        self._admin_ids = admin_ids
        self._admin_handler = admin_handler
        self._user_handler = user_handler

    async def handle(self, message: TelegramMessage) -> Optional[BotResponse]:
        command = parse_command(message.text)
        if not command.name:
            return None
        if message.actor_id in self._admin_ids:
            return await self._admin_handler.handle(message, command)

        response = await self._user_handler.handle(message, command)
        return response
