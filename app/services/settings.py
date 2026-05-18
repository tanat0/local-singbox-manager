from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Settings
from app.singbox.dns import DEFAULT_DNS_PRESET
from app.singbox.routes import DEFAULT_ROUTE_PRESET

LOG_LEVELS = ("error", "warn", "info", "debug")


def get_setting(db: Session, key: str, default: str = "") -> str:
    setting = db.query(Settings).filter(Settings.key == key).first()
    return setting.value if setting else default


def set_setting(db: Session, key: str, value: str) -> None:
    setting = db.query(Settings).filter(Settings.key == key).first()
    if setting:
        setting.value = value
    else:
        db.add(Settings(key=key, value=value))
    db.commit()


def presets(db: Session) -> tuple[str, str]:
    return (
        get_setting(db, "dns_preset", DEFAULT_DNS_PRESET),
        get_setting(db, "route_preset", DEFAULT_ROUTE_PRESET),
    )


def singbox_log_level(db: Session) -> str:
    level = get_setting(db, "singbox_log_level", "warn")
    return level if level in LOG_LEVELS else "warn"
