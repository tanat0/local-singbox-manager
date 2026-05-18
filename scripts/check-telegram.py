#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.telegram.client import TelegramApiClient
from app.telegram.diagnostics import (
    load_telegram_env,
    missing_admin_bot_settings,
    redact_token,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Telegram bot environment and connectivity.")
    parser.add_argument("--env-file", default=".env", help="Environment file to read before process env.")
    parser.add_argument("--send-test", action="store_true", help="Send a test message to TELEGRAM_CHAT_ID.")
    parser.add_argument("--list-updates", action="store_true", help="Print recent message sender IDs from getUpdates.")
    args = parser.parse_args()
    return asyncio.run(_main(args))


async def _main(args: argparse.Namespace) -> int:
    env = load_telegram_env(Path(args.env_file))
    print("Telegram env:")
    print(f"  TELEGRAM_BOT_TOKEN: {redact_token(env.bot_token) or 'EMPTY'}")
    print(f"  TELEGRAM_ADMIN_IDS: {sorted(env.admin_ids) if env.admin_ids else 'EMPTY'}")
    print(f"  TELEGRAM_ADMIN_BOT_ENABLED: {env.admin_bot_enabled_raw}")
    print(f"  TELEGRAM_CHAT_ID: {'SET' if env.chat_id else 'EMPTY'}")

    missing = missing_admin_bot_settings(env)
    if missing:
        print(f"\nAdmin bot is not ready. Missing: {', '.join(sorted(missing))}")
        return 1
    if not env.admin_bot_enabled:
        print("\nAdmin bot is disabled by TELEGRAM_ADMIN_BOT_ENABLED.")
        return 1

    client = TelegramApiClient(env.bot_token)
    try:
        me = await client.get_me()
    except Exception as exc:
        print(f"\nTelegram getMe failed: {exc}")
        return 2

    username = me.get("username") or me.get("first_name") or me.get("id") or "unknown"
    print(f"\nTelegram getMe: OK ({username})")

    if args.send_test:
        if not env.chat_id:
            print("Cannot send test: TELEGRAM_CHAT_ID is empty.")
            return 1
        try:
            await client.send_message(int(env.chat_id), "Sing-Box Manager Telegram check: OK")
            print("Test message: sent.")
        except Exception as exc:
            print(f"Test message failed: {exc}")
            return 2

    if args.list_updates:
        try:
            updates = await client.get_updates(offset=None, timeout=1, allowed_updates=["message"])
        except Exception as exc:
            print(f"getUpdates failed: {exc}")
            return 2
        _print_updates(updates)

    return 0


def _print_updates(updates: list[dict]) -> None:
    if not updates:
        print("Recent updates: none. Send /start to the bot, then rerun with --list-updates.")
        return

    print("Recent message senders:")
    seen = set()
    for update in updates:
        message = update.get("message") or {}
        sender = message.get("from") or {}
        chat = message.get("chat") or {}
        sender_id = sender.get("id")
        if sender_id in seen:
            continue
        seen.add(sender_id)
        username = sender.get("username") or sender.get("first_name") or "-"
        chat_id = chat.get("id") or "-"
        print(f"  user_id={sender_id} username={username} chat_id={chat_id}")


if __name__ == "__main__":
    raise SystemExit(main())
