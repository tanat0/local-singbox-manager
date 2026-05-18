from __future__ import annotations

from app.config import load_settings, parse_id_set


def test_load_settings_uses_safe_defaults():
    settings = load_settings({})

    assert settings.database_url == "sqlite:///./singbox_manager.db"
    assert settings.health_check_interval == 300
    assert settings.system_paths.singbox_bin == "/usr/bin/sing-box"
    assert settings.system_paths.helper_bin == "/usr/local/bin/singbox-manager-helper"
    assert settings.telegram.admin_bot_enabled is True


def test_load_settings_preserves_existing_env_names():
    settings = load_settings({
        "DATABASE_URL": "sqlite:////tmp/app.db",
        "HEALTH_CHECK_INTERVAL": "15",
        "SINGBOX_BIN": "/opt/sing-box",
        "HELPER_BIN": "/opt/helper",
        "SINGLE_ADMIN_PASSWORD": "secret",
        "SESSION_SECRET": "session",
        "TELEGRAM_BOT_TOKEN": "token",
        "TELEGRAM_CHAT_ID": "42",
        "TELEGRAM_ADMIN_IDS": "1, 2",
        "TELEGRAM_ADMIN_BOT_ENABLED": "false",
        "NTFY_TOPIC": "topic",
        "NTFY_SERVER": "https://ntfy.example",
    })

    assert settings.database_url == "sqlite:////tmp/app.db"
    assert settings.health_check_interval == 15
    assert settings.system_paths.singbox_bin == "/opt/sing-box"
    assert settings.system_paths.helper_bin == "/opt/helper"
    assert settings.security.admin_password == "secret"
    assert settings.security.session_secret == "session"
    assert settings.telegram.bot_token == "token"
    assert settings.telegram.chat_id == "42"
    assert settings.telegram.admin_ids == {1, 2}
    assert settings.telegram.admin_bot_enabled is False
    assert settings.notifications.ntfy_topic == "topic"
    assert settings.notifications.ntfy_server == "https://ntfy.example"


def test_invalid_health_interval_falls_back_to_default():
    assert load_settings({"HEALTH_CHECK_INTERVAL": "abc"}).health_check_interval == 300


def test_parse_id_set_ignores_invalid_parts():
    assert parse_id_set("1, bad; 2,,3") == {1, 2, 3}
