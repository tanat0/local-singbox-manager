from __future__ import annotations

from pathlib import Path

from app.telegram.diagnostics import (
    load_telegram_env,
    missing_admin_bot_settings,
    parse_env_file,
    redact_token,
)


def test_parse_env_file_reads_only_telegram_keys(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join([
            "TELEGRAM_BOT_TOKEN='123456:abcdef'",
            'TELEGRAM_CHAT_ID="42"',
            "TELEGRAM_ADMIN_IDS=1,2",
            "DATABASE_URL=sqlite:///ignored.db",
        ])
    )

    values = parse_env_file(env_file)

    assert values == {
        "TELEGRAM_BOT_TOKEN": "123456:abcdef",
        "TELEGRAM_CHAT_ID": "42",
        "TELEGRAM_ADMIN_IDS": "1,2",
    }


def test_load_telegram_env_process_env_overrides_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_ADMIN_IDS=1\nTELEGRAM_ADMIN_BOT_ENABLED=0\n")

    env = load_telegram_env(env_file, {
        "TELEGRAM_BOT_TOKEN": "token",
        "TELEGRAM_ADMIN_IDS": "7",
    })

    assert env.bot_token == "token"
    assert env.admin_ids == {7}
    assert env.admin_bot_enabled is False
    assert env.bot_ready is False


def test_missing_admin_bot_settings_reports_required_values():
    env = load_telegram_env(Path("/tmp/does-not-exist"), {})

    assert missing_admin_bot_settings(env) == {"TELEGRAM_BOT_TOKEN", "TELEGRAM_ADMIN_IDS"}


def test_redact_token_keeps_prefix_and_tail():
    assert redact_token("123456:abcdef1234") == "123456:...1234"
    assert redact_token("short") == "***"
    assert redact_token("") == ""
