from __future__ import annotations

from typing import Iterable, Protocol

from app.services.distribution import UserAssignment


class NodeView(Protocol):
    id: int
    tag: str
    protocol: str
    active: bool
    country_code: str
    provider_name: str
    provider_suggestion: str


def admin_help() -> str:
    return (
        "Commands:\n"
        "/status\n"
        "/nodes\n"
        "/activate <node-id-or-tag>\n"
        "/logs\n"
        "/health\n"
        "/notify_test"
    )


def user_help() -> str:
    return "Commands:\n/status\n/config\n/refresh"


def format_service_status(status: dict, active_tag: str, external_ip: str) -> str:
    return (
        f"sing-box: {status.get('active_state', 'unknown')}/{status.get('sub_state', 'unknown')}\n"
        f"pid: {status.get('pid') or '-'}\n"
        f"since: {status.get('since') or '-'}\n"
        f"active node: {active_tag or '-'}\n"
        f"external ip: {external_ip or '-'}"
    )


def format_nodes(nodes: Iterable[NodeView]) -> str:
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


def format_health_report(report) -> str:
    lines = [f"overall: {report.overall}"]
    for check in report.checks:
        mark = "OK" if check.ok else "FAIL"
        lat = f" {check.latency_ms:.0f}ms" if check.latency_ms is not None else ""
        lines.append(f"{mark} {check.name}{lat}: {check.detail}")
    return "\n".join(lines)


def format_user_status(assignment: UserAssignment) -> str:
    if assignment.error:
        return assignment.error
    user = assignment.user
    group = assignment.group
    label = (user.display_name or user.telegram_id) if user else "user"
    return (
        f"User: {label}\n"
        f"Group: {group.name if group else '-'}\n"
        f"Assigned configs: {len(assignment.nodes)}\n"
        f"Config version: {assignment.config_version or '-'}\n"
        f"Route preset: {assignment.route_preset}\n"
        f"Fingerprint: {assignment.config_fingerprint[:12] or '-'}"
    )


def format_user_configs(assignment: UserAssignment) -> str:
    if assignment.error:
        return assignment.error
    group = assignment.group
    lines = [
        f"Config group: {group.name if group else '-'}",
        f"Version: {assignment.config_version or '-'}",
        f"Route preset: {assignment.route_preset}",
        f"Fingerprint: {assignment.config_fingerprint[:12] or '-'}",
        "Generated sing-box config is attached.",
        "Raw proxy links remain below as fallback:",
        "",
    ]
    for node in assignment.nodes:
        lines.append(f"{node.tag} [{node.protocol}]")
        lines.append(node.raw_url)
        lines.append("")
    return "\n".join(lines).strip()
