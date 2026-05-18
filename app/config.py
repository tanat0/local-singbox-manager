from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional, Set


def _env_bool(value: str, default: bool = True) -> bool:
    if value == "":
        return default
    return value.lower() not in {"0", "false", "no", "off"}


def parse_id_set(raw: str) -> Set[int]:
    ids: Set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


def _env_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class SystemPaths:
    singbox_bin: str = "/usr/bin/sing-box"
    helper_bin: str = "/usr/local/bin/singbox-manager-helper"


@dataclass(frozen=True)
class SecuritySettings:
    admin_password: str = ""
    session_secret: str = ""

    @property
    def auth_enabled(self) -> bool:
        return bool(self.admin_password)


@dataclass(frozen=True)
class TelegramSettings:
    bot_token: str = ""
    chat_id: str = ""
    admin_ids_raw: str = ""
    admin_bot_enabled: bool = True

    @property
    def admin_ids(self) -> Set[int]:
        return parse_id_set(self.admin_ids_raw)

    @property
    def admin_bot_ready(self) -> bool:
        return self.admin_bot_enabled and bool(self.bot_token) and bool(self.admin_ids)


@dataclass(frozen=True)
class NotificationSettings:
    ntfy_topic: str = ""
    ntfy_server: str = "https://ntfy.sh"


@dataclass(frozen=True)
class AppSettings:
    database_url: str = "sqlite:///./singbox_manager.db"
    health_check_interval: int = 300
    system_paths: SystemPaths = SystemPaths()
    security: SecuritySettings = SecuritySettings()
    telegram: TelegramSettings = TelegramSettings()
    notifications: NotificationSettings = NotificationSettings()


def load_settings(env: Optional[Mapping[str, str]] = None) -> AppSettings:
    source = os.environ if env is None else env
    return AppSettings(
        database_url=source.get("DATABASE_URL", "sqlite:///./singbox_manager.db"),
        health_check_interval=_env_int(source.get("HEALTH_CHECK_INTERVAL", "300"), 300),
        system_paths=SystemPaths(
            singbox_bin=source.get("SINGBOX_BIN", "/usr/bin/sing-box"),
            helper_bin=source.get("HELPER_BIN", "/usr/local/bin/singbox-manager-helper"),
        ),
        security=SecuritySettings(
            admin_password=source.get("SINGLE_ADMIN_PASSWORD", ""),
            session_secret=source.get("SESSION_SECRET", ""),
        ),
        telegram=TelegramSettings(
            bot_token=source.get("TELEGRAM_BOT_TOKEN", ""),
            chat_id=source.get("TELEGRAM_CHAT_ID", ""),
            admin_ids_raw=source.get("TELEGRAM_ADMIN_IDS", ""),
            admin_bot_enabled=_env_bool(source.get("TELEGRAM_ADMIN_BOT_ENABLED", "1")),
        ),
        notifications=NotificationSettings(
            ntfy_topic=source.get("NTFY_TOPIC", ""),
            ntfy_server=source.get("NTFY_SERVER", "https://ntfy.sh"),
        ),
    )


settings = load_settings()
