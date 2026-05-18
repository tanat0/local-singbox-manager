from __future__ import annotations

import difflib
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from markupsafe import escape
from sqlalchemy.orm import Session

from app.db import get_db
from app.health import check_external_ip, run_health_checks
from app.repositories import NodeRepository, ProfileRepository
from app.routes.common import redirect
from app.services.metrics import latency_series
from app.services.nodes import deserialize_node, latest_deploy_logs
from app.services.settings import presets, singbox_log_level
from app.singbox import service as svc
from app.singbox.deployer import get_current_config
from app.singbox.generator import generate_config
from app.singbox.validator import validate_config
from app.web import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    status = svc.get_status()
    node_repo = NodeRepository(db)
    profile_repo = ProfileRepository(db)
    return templates.TemplateResponse(request, "dashboard.html", {
        "status": status,
        "active_node": node_repo.get_active(),
        "active_profile": profile_repo.get_active(),
        "nodes": node_repo.list_for_dashboard(),
        "latest_logs": latest_deploy_logs(db),
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@router.post("/service/{action}")
async def service_action(action: str):
    if action == "restart":
        ok, out = svc.restart()
    elif action == "stop":
        ok, out = svc.stop()
    elif action == "start":
        ok, out = svc.start()
    elif action == "reload":
        ok, out = svc.reload_or_restart()
    else:
        return redirect("/", msg=f"Unknown action: {action}", msg_type="error")
    return redirect("/", msg=out[:300] or action, msg_type="success" if ok else "error")


@router.post("/validate")
async def validate_active(db: Session = Depends(get_db)):
    node = NodeRepository(db).get_active()
    if not node:
        return redirect("/", msg="No active node", msg_type="error")
    try:
        parsed = deserialize_node(node)
        dns_p, route_p = presets(db)
        config = generate_config(
            parsed,
            dns_preset=dns_p,
            route_preset=route_p,
            log_level=singbox_log_level(db),
        )
    except Exception as e:
        return redirect("/", msg=f"Config generation error: {e}", msg_type="error")
    ok, msg = validate_config(config)
    return redirect("/", msg=msg, msg_type="success" if ok else "error")


@router.get("/api/ip", response_class=HTMLResponse)
async def api_ip():
    ip, err = await check_external_ip()
    if ip:
        return HTMLResponse(f'<span class="ip-value">{ip}</span>')
    return HTMLResponse(f'<span class="text-dim">Error: {err}</span>')


@router.get("/api/logs", response_class=HTMLResponse)
async def api_logs(lines: int = 100, mode: str = "all", grep: str = ""):
    lines = min(lines, 500)
    mode = mode if mode in {"all", "problems", "fatal"} else "all"
    log_text = escape(svc.get_logs(lines, mode=mode, grep=grep))
    return HTMLResponse(f'<pre class="log-output">{log_text}</pre>')


@router.get("/api/health", response_class=HTMLResponse)
async def api_health():
    report = await run_health_checks()
    cls = {"connected": "badge-green", "degraded": "badge-warning",
           "failed": "badge-red"}.get(report.overall, "badge-gray")

    def _rows(checks):
        parts = []
        for c in checks:
            sym = "✓" if c.ok else "✗"
            tr_cls = "check-ok" if c.ok else "check-fail"
            lat = f"{c.latency_ms:.0f}ms" if c.latency_ms else "—"
            parts.append(
                f'<tr class="{tr_cls}"><td>{sym}</td><td>{escape(c.name)}</td>'
                f'<td class="text-dim">{lat}</td>'
                f'<td class="text-dim">{escape(c.detail)}</td></tr>'
            )
        return "".join(parts)

    table_head = '<table><thead><tr><th></th><th>Check</th><th>Latency</th><th>Detail</th></tr></thead><tbody>'
    ip_line = (
        f'<div class="status-meta">'
        f'External IP: <strong>{escape(report.external_ip or "—")}</strong></div>'
    )
    return HTMLResponse(
        f'<span class="badge {cls} health-status-badge">{report.overall.upper()}</span>'
        f'<p class="text-dim section-label">System</p>'
        f'{table_head}{_rows(report.system_checks)}</tbody></table>'
        f'<p class="text-dim section-label section-label-spaced">Connectivity</p>'
        f'{table_head}{_rows(report.connectivity_checks)}</tbody></table>'
        f'{ip_line}'
    )


@router.get("/api/sysinfo", response_class=HTMLResponse)
async def api_sysinfo():
    version = svc.get_version()
    ver_str = escape(version) if version else '<span class="text-dim">unavailable</span>'
    return HTMLResponse(
        f'<div class="compact-info text-dim">'
        f'<div>sing-box: <strong>{ver_str}</strong></div>'
        f'</div>'
    )


@router.get("/api/metrics/latency")
async def api_metrics_latency(hours: int = 24, db: Session = Depends(get_db)):
    return JSONResponse(latency_series(db, hours))


@router.get("/api/diff", response_class=HTMLResponse)
async def api_diff(db: Session = Depends(get_db)):
    node = NodeRepository(db).get_active()
    if not node:
        return HTMLResponse('<p class="text-dim">No active node selected.</p>')

    current = get_current_config()
    current_text = json.dumps(current, indent=2) if current else "(no deployed config)"

    try:
        parsed = deserialize_node(node)
        dns_p, route_p = presets(db)
        new_config = generate_config(
            parsed,
            dns_preset=dns_p,
            route_preset=route_p,
            log_level=singbox_log_level(db),
        )
        new_text = json.dumps(new_config, indent=2)
    except Exception as e:
        return HTMLResponse(f'<p class="text-dim">Generation error: {e}</p>')

    diff = list(difflib.unified_diff(
        current_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile="deployed",
        tofile="pending",
        n=3,
    ))
    if not diff:
        return HTMLResponse('<p class="text-dim">No changes — config is already current.</p>')

    parts = []
    for line in diff:
        esc = str(escape(line))
        if line.startswith("+") and not line.startswith("+++"):
            parts.append(f'<span class="diff-add">{esc}</span>')
        elif line.startswith("-") and not line.startswith("---"):
            parts.append(f'<span class="diff-del">{esc}</span>')
        elif line.startswith("@@"):
            parts.append(f'<span class="diff-hunk">{esc}</span>')
        else:
            parts.append(esc)
    return HTMLResponse(f'<pre class="log-output diff-output">{"".join(parts)}</pre>')
