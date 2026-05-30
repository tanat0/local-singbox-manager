from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class TelegramApiClient:
    def __init__(self, token: str) -> None:
        self._base_url = f"https://api.telegram.org/bot{token}"

    async def _post(self, method: str, payload: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{self._base_url}/{method}", json=payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API {method} failed: {data}")
        return data

    async def get_me(self) -> Dict[str, Any]:
        data = await self._post("getMe", {})
        result = data.get("result")
        return dict(result) if isinstance(result, dict) else {}

    async def get_updates(
        self,
        offset: Optional[int],
        timeout: int,
        allowed_updates: List[str],
    ) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {"timeout": timeout, "allowed_updates": allowed_updates}
        if offset is not None:
            payload["offset"] = offset
        data = await self._post("getUpdates", payload, timeout=timeout + 5)
        return list(data.get("result", []))

    async def send_message(self, chat_id: int, text: str) -> None:
        chunks = [text[i:i + 3900] for i in range(0, len(text), 3900)] or [""]
        for chunk in chunks:
            await self._post("sendMessage", {"chat_id": chat_id, "text": chunk})
