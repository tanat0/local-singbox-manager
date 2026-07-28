from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Tuple

from sqlalchemy.orm import Session

from app import notify
from app.health import check_external_ip, run_health_checks
from app.repositories import AuditRepository, NodeRepository
from app.services.client_configs import build_client_config_document, build_sbclient_bundle_document
from app.services.deploy import ActivationResult, activate_node
from app.services.distribution import RATE_LIMIT_MESSAGE, get_user_assignment, record_delivery, refresh_limit_exceeded
from app.singbox import service as svc
from app.telegram import presenters
from app.telegram.types import BotResponse, ParsedCommand, TelegramDocument, TelegramMessage

SessionFactory = Callable[[], Session]
StatusProvider = Callable[[], dict]
LogProvider = Callable[[int, str], str]
ExternalIpChecker = Callable[[], Awaitable[Tuple[str, str]]]
HealthChecker = Callable[[], Awaitable[object]]
DeployActivator = Callable[[Session, object], Awaitable[ActivationResult]]
Notifier = Callable[[str, str, str], None]


@dataclass
class AdminHandlerDeps:
    session_factory: SessionFactory
    external_ip_checker: ExternalIpChecker
    health_checker: HealthChecker
    status_provider: StatusProvider = svc.get_status
    log_provider: LogProvider = lambda lines, mode: svc.get_logs(lines, mode=mode)
    deploy_activator: DeployActivator = activate_node
    notifier: Notifier = notify.fire


class AdminCommandHandler:
    def __init__(self, deps: AdminHandlerDeps) -> None:
        self._deps = deps

    async def handle(self, message: TelegramMessage, command: ParsedCommand) -> BotResponse:
        actor = str(message.actor_id or "unknown")
        db = self._deps.session_factory()
        try:
            audit = AuditRepository(db)
            nodes = NodeRepository(db)

            if command.name in {"/start", "/help"}:
                return BotResponse(True, presenters.admin_help())

            if command.name == "/status":
                active = nodes.get_active()
                ip, err = await self._deps.external_ip_checker()
                text = presenters.format_service_status(
                    self._deps.status_provider(),
                    active.tag if active else "",
                    ip or err or "",
                )
                audit.add_admin_action(actor, "telegram", command.name, True, "status requested")
                db.commit()
                return BotResponse(True, text)

            if command.name == "/nodes":
                audit.add_admin_action(actor, "telegram", command.name, True, "nodes listed")
                db.commit()
                return BotResponse(True, presenters.format_nodes(nodes.list_for_dashboard()))

            if command.name == "/activate":
                if not command.arg:
                    audit.add_admin_action(actor, "telegram", command.name, False, "missing node")
                    db.commit()
                    return BotResponse(False, "Usage: /activate <node-id-or-tag>")
                node = nodes.find_by_id_or_tag(command.arg)
                if not node:
                    audit.add_admin_action(actor, "telegram", command.name, False, f"node not found: {command.arg}")
                    db.commit()
                    return BotResponse(False, f"Node not found: {command.arg}")
                result = await self._deps.deploy_activator(db, node)
                audit.add_admin_action(actor, "telegram", command.name, result.ok, result.message)
                db.commit()
                return BotResponse(result.ok, result.message)

            if command.name == "/logs":
                audit.add_admin_action(actor, "telegram", command.name, True, "logs requested")
                db.commit()
                text = self._deps.log_provider(300, "problems")
                return BotResponse(True, text[-3500:] if text else "No recent problems.")

            if command.name == "/health":
                report = await self._deps.health_checker()
                audit.add_admin_action(actor, "telegram", command.name, report.overall == "connected", report.overall)
                db.commit()
                return BotResponse(report.overall == "connected", presenters.format_health_report(report))

            if command.name == "/notify_test":
                self._deps.notifier("Test notification", "Telegram admin bot requested a test notification.", "info")
                audit.add_admin_action(actor, "telegram", command.name, True, "test notification")
                db.commit()
                return BotResponse(True, "Test notification scheduled.")

            return BotResponse(False, "Unknown command. Use /help.")
        finally:
            db.close()


@dataclass
class UserHandlerDeps:
    session_factory: SessionFactory


def default_admin_deps(session_factory: SessionFactory) -> AdminHandlerDeps:
    return AdminHandlerDeps(
        session_factory=session_factory,
        external_ip_checker=check_external_ip,
        health_checker=run_health_checks,
    )


class UserCommandHandler:
    def __init__(self, deps: UserHandlerDeps) -> None:
        self._deps = deps

    async def handle(self, message: TelegramMessage, command: ParsedCommand) -> BotResponse:
        actor = str(message.actor_id or "unknown")
        db = self._deps.session_factory()
        try:
            assignment = get_user_assignment(db, actor)
            if assignment.user is None:
                record_delivery(
                    db,
                    actor,
                    command.name or "unknown",
                    False,
                    assignment,
                    assignment.error or "access denied",
                )
                return BotResponse(False, "Access denied.")

            if command.name in {"/start", "/help"}:
                if assignment.error:
                    record_delivery(db, actor, command.name, False, assignment, assignment.error)
                    return BotResponse(False, assignment.error)
                record_delivery(db, actor, command.name, True, assignment, "help requested")
                return BotResponse(True, presenters.user_help())

            if command.name == "/status":
                ok = not bool(assignment.error)
                text = presenters.format_user_status(assignment)
                record_delivery(db, actor, command.name, ok, assignment, assignment.error or "status requested")
                return BotResponse(ok, text)

            if command.name in {"/config", "/refresh"}:
                if not assignment.error and refresh_limit_exceeded(db, assignment):
                    record_delivery(db, actor, command.name, False, assignment, "refresh limit exceeded")
                    return BotResponse(False, RATE_LIMIT_MESSAGE)
                ok = not bool(assignment.error)
                document = None
                document_error = None
                if ok:
                    try:
                        client_document = build_client_config_document(assignment)
                        document = TelegramDocument(
                            filename=client_document.filename,
                            content=client_document.content,
                            mime_type=client_document.mime_type,
                            caption=client_document.caption,
                        )
                    except Exception as exc:
                        document_error = f"generated client config failed: {type(exc).__name__}"
                text = presenters.format_user_configs(assignment)
                if document_error:
                    text += (
                        "\n\nGenerated sing-box config is unavailable for this assignment. "
                        "Use the raw fallback links above."
                    )
                detail = (
                    assignment.error
                    or document_error
                    or f"{len(assignment.nodes)} raw fallback link(s) and generated config prepared"
                )
                record_delivery(db, actor, command.name, ok and not document_error, assignment, detail)
                return BotResponse(ok, text, document=document)

            if command.name == "/sbclient":
                if not assignment.error and refresh_limit_exceeded(db, assignment):
                    record_delivery(db, actor, command.name, False, assignment, "refresh limit exceeded")
                    return BotResponse(False, RATE_LIMIT_MESSAGE)
                ok = not bool(assignment.error)
                document = None
                document_error = None
                if ok:
                    try:
                        client_document = build_sbclient_bundle_document(assignment)
                        document = TelegramDocument(
                            filename=client_document.filename,
                            content=client_document.content,
                            mime_type=client_document.mime_type,
                            caption=client_document.caption,
                        )
                    except Exception as exc:
                        document_error = f"generated sbclient bundle failed: {type(exc).__name__}"
                text = presenters.format_user_status(assignment)
                if document_error:
                    text = (
                        presenters.format_user_configs(assignment)
                        + "\n\n.sbclient bundle is unavailable for this assignment. Use the raw fallback links above."
                    )
                detail = (
                    assignment.error
                    or document_error
                    or f"{len(assignment.nodes)} profile(s) in .sbclient bundle prepared"
                )
                record_delivery(db, actor, command.name, ok and not document_error, assignment, detail)
                return BotResponse(ok, text, document=document)

            record_delivery(db, actor, command.name or "unknown", False, assignment, "unknown command")
            return BotResponse(False, "Unknown command. Use /help.")
        finally:
            db.close()
