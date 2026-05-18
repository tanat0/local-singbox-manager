from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Iterable, Optional, Set, Tuple

import httpx

from app import notify
from app.health import check_external_ip, run_health_checks
from app.logging_config import get_logger
from app.singbox import service as svc

_log = get_logger(__name__)

TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_IDS_RAW: str = os.environ.get("TELEGRAM_ADMIN_IDS", "")
TELEGRAM_ADMIN_BOT_ENABLED: str = os.environ.get("TELEGRAM_ADMIN_BOT_ENABLED", "1")

_POLL_TIMEOUT = 25
_POLL_BACKOFF = 5


def parse_admin_ids(raw: Optional[str] = None) -> Set[int]:
    raw = TELEGRAM_ADMIN_IDS_RAW if raw is None else raw
    ids: Set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            _log.warning("Ignoring invalid TELEGRAM_ADMIN_IDS entry: %r", part)
    return ids


def is_enabled() -> bool:
    return (
        TELEGRAM_ADMIN_BOT_ENABLED.lower() not in {"0", "false", "no", "off"}
        and bool(TELEGRAM_BOT_TOKEN)
        and bool(parse_admin_ids())
    )


def _chat_id(message: Dict[str, Any]) -> Optional[int]:
    chat = message.get("chat") or {}
    try:
        return int(chat["id"])
    except Exception:
        return None


def _actor_id(message: Dict[str, Any]) -> Optional[int]:
    sender = message.get("from") or {}
    try:
        return int(sender["id"])
    except Exception:
        return None


def _command_parts(text: str) -> Tuple[str, str]:
    text = (text or "").strip()
    if not text.startswith("/"):
        return "", ""
    first, _, rest = text.partition(" ")
    command = first.split("@", 1)[0].lower()
    return command, rest.strip()


def _short_status() -> str:
    status = svc.get_status()
    return (
        f"sing-box: {status.get('active_state', 'unknown')}/{status.get('sub_state', 'unknown')}\n"
        f"pid: {status.get('pid') or '-'}\n"
        f"since: {status.get('since') or '-'}"
    )


def _format_nodes(nodes: Iterable[Node]) -> str:
    lines = []
    for node in nodes:
        marker = "*" if node.active else " "
        meta = []
        if node.country_code:
            meta.append(node.country_code)
        if node.provider_name or node.provider_suggestion:
            meta.append(node.provider_name or node.provider_suggestion or "")
        suffix = f" ({', '.join(meta)})" if meta else ""
        lines.append(f"{marker} {node.id}: {node.tag} [{node.protocol}]{suffix}")
    return "\n".join(lines) if lines else "No nodes yet."


def _session():
    from app.db import SessionLocal

    return SessionLocal()


def _log_admin_action(db, actor: str, action: str, success: bool, detail: str = "") -> None:
    from app.services.audit import log_admin_action

    log_admin_action(db, actor, "telegram", action, success, detail)


def _get_active_node(db):
    from app.models import Node

    return db.query(Node).filter(Node.active.is_(True)).first()


def _list_nodes(db):
    from app.models import Node

    return db.query(Node).order_by(Node.active.desc(), Node.created_at.desc()).all()


def _find_node(db, value: str):
    from app.models import Node

    node = None
    if value.isdigit():
        node = db.query(Node).filter(Node.id == int(value)).first()
    if not node:
        node = db.query(Node).filter(Node.tag == value).first()
    return node


async def _handle_admin_command(message: Dict[str, Any], command: str, arg: str) -> Tuple[bool, str]:
    actor = str(_actor_id(message) or "unknown")
    db = _session()
    try:
        if command == "/start" or command == "/help":
            return True, (
                "Commands:\n"
                "/status\n"
                "/nodes\n"
                "/activate <node-id-or-tag>\n"
                "/logs\n"
                "/health\n"
                "/notify_test"
            )

        if command == "/status":
            active = _get_active_node(db)
            ip, err = await check_external_ip()
            detail = _short_status()
            detail += f"\nactive node: {active.tag if active else '-'}"
            detail += f"\nexternal ip: {ip or err or '-'}"
            _log_admin_action(db, actor, command, True, "status requested")
            return True, detail

        if command == "/nodes":
            nodes = _list_nodes(db)
            _log_admin_action(db, actor, command, True, "nodes listed")
            return True, _format_nodes(nodes)

        if command == "/activate":
            if not arg:
                _log_admin_action(db, actor, command, False, "missing node")
                return False, "Usage: /activate <node-id-or-tag>"
            node = _find_node(db, arg)
            if not node:
                _log_admin_action(db, actor, command, False, f"node not found: {arg}")
                return False, f"Node not found: {arg}"
            from app.services.deploy import activate_node

            result = await activate_node(db, node)
            _log_admin_action(db, actor, command, result.ok, result.message)
            return result.ok, result.message

        if command == "/logs":
            _log_admin_action(db, actor, command, True, "logs requested")
            text = svc.get_logs(300, mode="problems")
            return True, text[-3500:] if text else "No recent problems."

        if command == "/health":
            report = await run_health_checks()
            lines = [f"overall: {report.overall}"]
            for check in report.checks:
                mark = "OK" if check.ok else "FAIL"
                lat = f" {check.latency_ms:.0f}ms" if check.latency_ms is not None else ""
                lines.append(f"{mark} {check.name}{lat}: {check.detail}")
            _log_admin_action(db, actor, command, report.overall == "connected", report.overall)
            return report.overall == "connected", "\n".join(lines)

        if command == "/notify_test":
            notify.fire("🔔 Test notification", "Telegram admin bot requested a test notification.", "info")
            _log_admin_action(db, actor, command, True, "test notification")
            return True, "Test notification scheduled."

        return False, "Unknown command. Use /help."
    finally:
        db.close()


async def handle_message(message: Dict[str, Any], admin_ids: Set[int]) -> Optional[str]:
    actor = _actor_id(message)
    if actor not in admin_ids:
        db = _session()
        try:
            _log_admin_action(db, str(actor or "unknown"), "unauthorized", False, "access denied")
        finally:
            db.close()
        return "Access denied."

    command, arg = _command_parts(message.get("text", ""))
    if not command:
        return None
    _, response = await _handle_admin_command(message, command, arg)
    return response


class TelegramAdminBot:
    def __init__(self, token: str, admin_ids: Set[int]) -> None:
        self.token = token
        self.admin_ids = admin_ids
        self.offset: Optional[int] = None
        self.base_url = f"https://api.telegram.org/bot{token}"

    async def _post(self, method: str, payload: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{self.base_url}/{method}", json=payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API {method} failed: {data}")
        return data

    async def send_message(self, chat_id: int, text: str) -> None:
        chunks = [text[i:i + 3900] for i in range(0, len(text), 3900)] or [""]
        for chunk in chunks:
            await self._post("sendMessage", {"chat_id": chat_id, "text": chunk})

    async def poll_once(self) -> None:
        payload: Dict[str, Any] = {"timeout": _POLL_TIMEOUT, "allowed_updates": ["message"]}
        if self.offset is not None:
            payload["offset"] = self.offset
        data = await self._post("getUpdates", payload, timeout=_POLL_TIMEOUT + 5)
        for update in data.get("result", []):
            self.offset = int(update["update_id"]) + 1
            message = update.get("message") or {}
            chat_id = _chat_id(message)
            if chat_id is None:
                continue
            response = await handle_message(message, self.admin_ids)
            if response:
                await self.send_message(chat_id, response)

    async def run_forever(self) -> None:
        _log.info("Telegram admin bot polling started for %d admin id(s)", len(self.admin_ids))
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _log.warning("Telegram admin bot polling error: %s", e)
                await asyncio.sleep(_POLL_BACKOFF)


def create_bot_from_env() -> Optional[TelegramAdminBot]:
    if not is_enabled():
        return None
    return TelegramAdminBot(TELEGRAM_BOT_TOKEN, parse_admin_ids())
