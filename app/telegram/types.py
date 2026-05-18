from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class TelegramMessage:
    actor_id: Optional[int]
    chat_id: Optional[int]
    text: str

    @classmethod
    def from_api_message(cls, raw: Dict[str, Any]) -> "TelegramMessage":
        return cls(
            actor_id=_extract_int(raw.get("from") or {}, "id"),
            chat_id=_extract_int(raw.get("chat") or {}, "id"),
            text=str(raw.get("text") or ""),
        )


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    arg: str = ""


@dataclass(frozen=True)
class BotResponse:
    ok: bool
    text: str


def _extract_int(raw: Dict[str, Any], key: str) -> Optional[int]:
    try:
        return int(raw[key])
    except (KeyError, TypeError, ValueError):
        return None


def parse_command(text: str) -> ParsedCommand:
    text = (text or "").strip()
    if not text.startswith("/"):
        return ParsedCommand("")
    first, _, rest = text.partition(" ")
    command = first.split("@", 1)[0].lower()
    return ParsedCommand(command, rest.strip())


def command_parts(text: str) -> Tuple[str, str]:
    parsed = parse_command(text)
    return parsed.name, parsed.arg
