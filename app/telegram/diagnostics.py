from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Set

from app.config import parse_id_set

TELEGRAM_ENV_KEYS = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_ADMIN_IDS",
    "TELEGRAM_ADMIN_BOT_ENABLED",
)


@dataclass(frozen=True)
class TelegramEnv:
    bot_token: str = ""
    chat_id: str = ""
    admin_ids_raw: str = ""
    admin_bot_enabled_raw: str = "1"

    @property
    def admin_ids(self) -> Set[int]:
        return parse_id_set(self.admin_ids_raw)

    @property
    def admin_bot_enabled(self) -> bool:
        return self.admin_bot_enabled_raw.lower() not in {"0", "false", "no", "off"}

    @property
    def bot_ready(self) -> bool:
        return bool(self.bot_token and self.admin_ids and self.admin_bot_enabled)

    @property
    def notification_ready(self) -> bool:
        return bool(self.bot_token and self.chat_id)


def parse_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in TELEGRAM_ENV_KEYS:
            continue
        values[key] = _strip_quotes(value.strip())
    return values


def load_telegram_env(env_file: Path, env: Optional[Mapping[str, str]] = None) -> TelegramEnv:
    source = parse_env_file(env_file)
    runtime_env = os.environ if env is None else env
    for key in TELEGRAM_ENV_KEYS:
        if key in runtime_env:
            source[key] = runtime_env[key]

    return TelegramEnv(
        bot_token=source.get("TELEGRAM_BOT_TOKEN", ""),
        chat_id=source.get("TELEGRAM_CHAT_ID", ""),
        admin_ids_raw=source.get("TELEGRAM_ADMIN_IDS", ""),
        admin_bot_enabled_raw=source.get("TELEGRAM_ADMIN_BOT_ENABLED", "1") or "1",
    )


def missing_admin_bot_settings(env: TelegramEnv) -> Set[str]:
    missing = set()
    if not env.bot_token:
        missing.add("TELEGRAM_BOT_TOKEN")
    if not env.admin_ids:
        missing.add("TELEGRAM_ADMIN_IDS")
    return missing


def redact_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 10:
        return "***"
    prefix, _, suffix = token.partition(":")
    tail = suffix[-4:] if suffix else token[-4:]
    return f"{prefix}:...{tail}" if prefix else f"...{tail}"


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
