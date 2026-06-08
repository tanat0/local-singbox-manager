from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from typing import List, Optional

from markupsafe import escape
from sqlalchemy.orm import Session

from app.health import HealthReport
from app.models import Node
from app.services.log_insights import LogInsight
from app.services.nodes import deserialize_node
from app.services.settings import presets, singbox_log_level
from app.singbox.generator import generate_config
from app.singbox.validator import validate_config


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    message: str


def validate_node_config(db: Session, node: Node) -> ValidationResult:
    try:
        parsed = deserialize_node(node)
        dns_preset, route_preset = presets(db)
        config = generate_config(
            parsed,
            dns_preset=dns_preset,
            route_preset=route_preset,
            log_level=singbox_log_level(db),
        )
    except Exception as exc:
        return ValidationResult(False, f"Config generation error: {exc}")

    ok, message = validate_config(config)
    return ValidationResult(ok, message)


def render_external_ip(ip: Optional[str], error: str) -> str:
    if ip:
        return f'<span class="ip-value">{escape(ip)}</span>'
    return f'<span class="text-dim">Error: {escape(error)}</span>'


def render_log_output(text: str) -> str:
    return f'<pre class="log-output">{escape(text)}</pre>'


def render_log_insights(insights: List[LogInsight]) -> str:
    if not insights:
        return '<p class="text-dim">No recent connection or DNS problems found.</p>'

    rows = []
    for item in insights:
        outbound = _outbound_label(item)
        target = escape(item.target or "—")
        rows.append(
            "<tr>"
            f"<td><span class=\"badge badge-red\">{escape(item.kind)}</span></td>"
            f"<td>{outbound}</td>"
            f"<td><code>{target}</code></td>"
            f"<td>{escape(item.reason)}</td>"
            f"<td>{item.count}</td>"
            f"<td class=\"text-dim\">{escape(item.last_seen or '—')}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Kind</th><th>Outbound</th><th>Target</th><th>Reason</th><th>Count</th><th>Last Seen</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def render_health_report(report: HealthReport) -> str:
    badge_class = {
        "connected": "badge-green",
        "degraded": "badge-warning",
        "failed": "badge-red",
    }.get(report.overall, "badge-gray")
    return (
        f'<span class="badge {badge_class} health-status-badge">{escape(report.overall.upper())}</span>'
        f'<p class="text-dim section-label">System</p>'
        f'{_health_table(report.system_checks)}'
        f'<p class="text-dim section-label section-label-spaced">Connectivity</p>'
        f'{_health_table(report.connectivity_checks)}'
        f'<div class="status-meta">External IP: '
        f'<strong>{escape(report.external_ip or "—")}</strong></div>'
    )


def render_sysinfo(version: str) -> str:
    version_html = escape(version) if version else '<span class="text-dim">unavailable</span>'
    return (
        f'<div class="compact-info text-dim">'
        f'<div>sing-box: <strong>{version_html}</strong></div>'
        f'</div>'
    )


def render_config_diff(db: Session, node: Optional[Node], current_config: Optional[dict]) -> str:
    if not node:
        return '<p class="text-dim">No active node selected.</p>'

    current_text = json.dumps(current_config, indent=2) if current_config else "(no deployed config)"
    try:
        parsed = deserialize_node(node)
        dns_preset, route_preset = presets(db)
        new_config = generate_config(
            parsed,
            dns_preset=dns_preset,
            route_preset=route_preset,
            log_level=singbox_log_level(db),
        )
        new_text = json.dumps(new_config, indent=2)
    except Exception as exc:
        return f'<p class="text-dim">Generation error: {escape(str(exc))}</p>'

    diff = list(difflib.unified_diff(
        current_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile="deployed",
        tofile="pending",
        n=3,
    ))
    if not diff:
        return '<p class="text-dim">No changes — config is already current.</p>'
    return f'<pre class="log-output diff-output">{"".join(_render_diff_line(line) for line in diff)}</pre>'


def _health_table(checks) -> str:
    rows = []
    for check in checks:
        symbol = "✓" if check.ok else "✗"
        row_class = "check-ok" if check.ok else "check-fail"
        latency = f"{check.latency_ms:.0f}ms" if check.latency_ms else "—"
        rows.append(
            f'<tr class="{row_class}"><td>{symbol}</td><td>{escape(check.name)}</td>'
            f'<td class="text-dim">{latency}</td>'
            f'<td class="text-dim">{escape(check.detail)}</td></tr>'
        )
    return (
        '<table><thead><tr><th></th><th>Check</th><th>Latency</th><th>Detail</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _outbound_label(item: LogInsight) -> str:
    if item.protocol and item.outbound_tag:
        return f"{escape(item.protocol)} / <strong>{escape(item.outbound_tag)}</strong>"
    return '<span class="text-dim">—</span>'


def _render_diff_line(line: str) -> str:
    escaped = str(escape(line))
    if line.startswith("+") and not line.startswith("+++"):
        return f'<span class="diff-add">{escaped}</span>'
    if line.startswith("-") and not line.startswith("---"):
        return f'<span class="diff-del">{escaped}</span>'
    if line.startswith("@@"):
        return f'<span class="diff-hunk">{escaped}</span>'
    return escaped
