from __future__ import annotations
import asyncio
import difflib
import json
import os
import re
import statistics
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[assignment]
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import escape
from sqlalchemy.orm import Session

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

from app.auth import (
    AUTH_ENABLED, SESSION_COOKIE, SESSION_MAX_AGE,
    AuthMiddleware, create_session_token, emit_startup_warnings,
    rate_limit_ok, verify_password,
)
from app.db import SessionLocal, get_db
from app.health import run_health_checks, check_external_ip
from app.logging_config import setup_logging, get_logger
from app import notify
from app.version import VERSION

_log = get_logger(__name__)
from app.models import Node, Settings, DeployLog, HealthCheckLog, Profile
from app.parsers import parse_url, ParsedNode, VlessNode, Hysteria2Node
from app.singbox import service as svc
from app.singbox.deployer import (
    deploy_with_rollback, list_backups, restore_backup, get_current_config,
)
from app.singbox.dns import DNS_PRESETS, DEFAULT_DNS_PRESET
from app.singbox.generator import generate_config, build_outbound
from app.singbox.routes import ROUTE_PRESETS, DEFAULT_ROUTE_PRESET
from app.singbox.validator import validate_config

_HEALTH_CHECK_INTERVAL = int(os.environ.get("HEALTH_CHECK_INTERVAL", "300"))
_HEALTH_RETAIN_DAYS = 7
_last_health_state: str = "unknown"   # tracks previous overall to detect transitions


def _run_migrations() -> None:
    ini = Path(__file__).parent.parent / "alembic.ini"
    cfg = AlembicConfig(str(ini))
    alembic_command.upgrade(cfg, "head")


async def _health_check_loop() -> None:
    global _last_health_state
    await asyncio.sleep(15)   # let the server fully start first
    while True:
        try:
            report = await run_health_checks()
            now = datetime.utcnow()
            cutoff = now - timedelta(days=_HEALTH_RETAIN_DAYS)
            db = SessionLocal()
            try:
                for c in report.checks:
                    db.add(HealthCheckLog(
                        checked_at=now,
                        check_name=c.name,
                        category=c.category,
                        ok=c.ok,
                        latency_ms=c.latency_ms,
                        detail=c.detail,
                    ))
                db.query(HealthCheckLog).filter(
                    HealthCheckLog.checked_at < cutoff
                ).delete()
                db.commit()
            finally:
                db.close()

            _notify_health_change(_last_health_state, report.overall, report)
            _last_health_state = report.overall
        except Exception as e:
            _log.warning("Health check loop error: %s", e, exc_info=True)
        await asyncio.sleep(_HEALTH_CHECK_INTERVAL)


def _notify_health_change(prev: str, current: str, report: "HealthReport") -> None:  # type: ignore[name-defined]
    if prev == current or prev == "unknown":
        return
    if current == "connected":
        notify.fire("✓ Tunnel recovered", "All health checks passing", "info")
    elif current == "degraded":
        failing = [c.name for c in report.checks if not c.ok]
        notify.fire("⚠ Tunnel degraded",
                    f"Failing: {', '.join(failing)}", "warning")
    elif current == "failed":
        notify.fire("✗ Tunnel failed",
                    "All connectivity checks failing", "critical")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    _log.info("Sing-Box Manager v%s starting up", VERSION)
    emit_startup_warnings()
    _run_migrations()
    task = asyncio.create_task(_health_check_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Sing-Box Manager", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(AuthMiddleware)

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["fromjson"] = json.loads
templates.env.filters["tojson"] = json.dumps
templates.env.globals["auth_enabled"] = AUTH_ENABLED
templates.env.globals["app_version"] = VERSION

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Health / version probes (always open, no auth required)
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_probe():
    return JSONResponse({"status": "ok", "version": VERSION})


@app.get("/version")
async def version_probe():
    return JSONResponse({"app": VERSION, "singbox": svc.get_version() or "unknown"})


# ---------------------------------------------------------------------------
# Auth: login / logout
# ---------------------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": ""})


@app.post("/login")
async def login_post(
    request: Request,
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = "/",
):
    ip = request.client.host if request.client else "unknown"
    if not rate_limit_ok(ip):
        _log.warning("Login rate-limited for %s", ip)
        return templates.TemplateResponse(request, "login.html", {
            "next": next,
            "error": "Too many attempts — wait 60 seconds and try again.",
        }, status_code=429)

    if not verify_password(password):
        _log.warning("Failed login attempt from %s", ip)
        return templates.TemplateResponse(request, "login.html", {
            "next": next,
            "error": "Incorrect password.",
        }, status_code=401)

    _log.info("Login successful from %s", ip)
    safe_next = next if (next.startswith("/") and not next.startswith("//")) else "/"
    response = RedirectResponse(safe_next, status_code=303)
    response.set_cookie(
        SESSION_COOKIE, create_session_token(),
        httponly=True, samesite="strict",
        max_age=SESSION_MAX_AGE, path="/",
    )
    return response


@app.post("/logout")
async def logout_post():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redirect(path: str, msg: str = "", msg_type: str = "info") -> RedirectResponse:
    url = path
    if msg:
        url += f"?msg={quote(msg)}&msg_type={msg_type}"
    return RedirectResponse(url=url, status_code=303)


def _get_setting(db: Session, key: str, default: str = "") -> str:
    s = db.query(Settings).filter(Settings.key == key).first()
    return s.value if s else default


def _set_setting(db: Session, key: str, value: str) -> None:
    s = db.query(Settings).filter(Settings.key == key).first()
    if s:
        s.value = value
    else:
        db.add(Settings(key=key, value=value))
    db.commit()


def _deserialize_node(node: Node) -> ParsedNode:
    data = json.loads(node.parsed_json)
    proto = data.get("protocol", "")
    if proto == "vless":
        return VlessNode.model_validate(data)
    if proto in ("hysteria2", "hy2"):
        return Hysteria2Node.model_validate(data)
    raise ValueError(
        f"Unknown protocol {proto!r} stored for node '{node.tag}' — "
        "delete and re-add this node from /nodes"
    )


def _presets(db: Session) -> tuple[str, str]:
    return (
        _get_setting(db, "dns_preset", DEFAULT_DNS_PRESET),
        _get_setting(db, "route_preset", DEFAULT_ROUTE_PRESET),
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    status = svc.get_status()
    active_node = db.query(Node).filter(Node.active.is_(True)).first()
    active_profile = db.query(Profile).filter(Profile.active.is_(True)).first()
    return templates.TemplateResponse(request, "dashboard.html", {
        "status": status,
        "active_node": active_node,
        "active_profile": active_profile,
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@app.post("/service/{action}")
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
        return _redirect("/", msg=f"Unknown action: {action}", msg_type="error")
    return _redirect("/", msg=out[:300] or action, msg_type="success" if ok else "error")


@app.post("/validate")
async def validate_active(db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.active.is_(True)).first()
    if not node:
        return _redirect("/", msg="No active node", msg_type="error")
    try:
        parsed = _deserialize_node(node)
        dns_p, route_p = _presets(db)
        config = generate_config(parsed, dns_preset=dns_p, route_preset=route_p)
    except Exception as e:
        return _redirect("/", msg=f"Config generation error: {e}", msg_type="error")
    ok, msg = validate_config(config)
    return _redirect("/", msg=msg, msg_type="success" if ok else "error")


# ---------------------------------------------------------------------------
# HTMX partials
# ---------------------------------------------------------------------------

@app.get("/api/ip", response_class=HTMLResponse)
async def api_ip():
    ip, err = await check_external_ip()
    if ip:
        return HTMLResponse(f'<span class="ip-value">{ip}</span>')
    return HTMLResponse(f'<span class="text-dim">Error: {err}</span>')


@app.get("/api/logs", response_class=HTMLResponse)
async def api_logs(lines: int = 100):
    lines = min(lines, 500)
    return HTMLResponse(f'<pre class="log-output">{escape(svc.get_logs(lines))}</pre>')


@app.get("/api/health", response_class=HTMLResponse)
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
        f'<div style="margin-top:12px" class="text-dim">'
        f'External IP: <strong>{escape(report.external_ip or "—")}</strong></div>'
    )
    return HTMLResponse(
        f'<span class="badge {cls}" style="font-size:14px;margin-bottom:14px;display:inline-block">'
        f'{report.overall.upper()}</span>'
        f'<p class="text-dim" style="margin:4px 0 10px">System</p>'
        f'{table_head}{_rows(report.system_checks)}</tbody></table>'
        f'<p class="text-dim" style="margin:12px 0 10px">Connectivity</p>'
        f'{table_head}{_rows(report.connectivity_checks)}</tbody></table>'
        f'{ip_line}'
    )


@app.get("/api/sysinfo", response_class=HTMLResponse)
async def api_sysinfo():
    version = svc.get_version()
    ver_str = escape(version) if version else '<span class="text-dim">unavailable</span>'
    return HTMLResponse(
        f'<div class="text-dim" style="font-size:13px;line-height:1.8">'
        f'<div>sing-box: <strong>{ver_str}</strong></div>'
        f'</div>'
    )


@app.get("/api/metrics/latency")
async def api_metrics_latency(hours: int = 24, db: Session = Depends(get_db)):
    hours = min(max(hours, 1), 168)   # clamp 1h–7d
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    rows = (
        db.query(HealthCheckLog)
        .filter(
            HealthCheckLog.checked_at >= cutoff,
            HealthCheckLog.category == "connectivity",
        )
        .order_by(HealthCheckLog.checked_at)
        .all()
    )

    # Group by check name
    by_name: dict = {}
    for r in rows:
        by_name.setdefault(r.check_name, []).append(r)

    series = []
    for name, checks in by_name.items():
        total = len(checks)
        ok_count = sum(1 for c in checks if c.ok)
        latencies = [c.latency_ms for c in checks if c.ok and c.latency_ms is not None]

        points = []
        for c in checks:
            ts = c.checked_at.strftime("%H:%M") if c.checked_at else "?"
            points.append({
                "t": ts,
                "ms": round(c.latency_ms, 1) if c.latency_ms is not None else None,
                "ok": c.ok,
            })

        series.append({
            "name": name,
            "points": points,
            "uptime_pct": round(ok_count / total * 100, 1) if total else None,
            "avg_ms": round(statistics.mean(latencies), 1) if latencies else None,
            "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 1) if len(latencies) >= 2 else None,
            "sample_count": total,
        })

    return JSONResponse({"hours": hours, "series": series})


@app.get("/api/diff", response_class=HTMLResponse)
async def api_diff(db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.active.is_(True)).first()
    if not node:
        return HTMLResponse('<p class="text-dim">No active node selected.</p>')

    current = get_current_config()
    current_text = json.dumps(current, indent=2) if current else "(no deployed config)"

    try:
        parsed = _deserialize_node(node)
        dns_p, route_p = _presets(db)
        new_config = generate_config(parsed, dns_preset=dns_p, route_preset=route_p)
        new_text = json.dumps(new_config, indent=2)
    except Exception as e:
        return HTMLResponse(f'<p class="text-dim">Generation error: {e}</p>')

    diff = list(difflib.unified_diff(
        current_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile="deployed", tofile="pending", n=3,
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


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

@app.get("/nodes", response_class=HTMLResponse)
async def nodes_page(request: Request, db: Session = Depends(get_db)):
    nodes = db.query(Node).order_by(Node.created_at.desc()).all()
    return templates.TemplateResponse(request, "nodes.html", {
        "nodes": nodes,
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@app.post("/nodes")
async def add_node(url: Annotated[str, Form()], db: Session = Depends(get_db)):
    try:
        parsed = parse_url(url)
    except Exception as e:
        return _redirect("/nodes", msg=f"Parse error: {e}", msg_type="error")

    existing = db.query(Node).filter(Node.tag == parsed.tag).first()
    if existing:
        existing.raw_url = parsed.raw_url
        existing.protocol = parsed.protocol
        existing.parsed_json = json.dumps(parsed.to_dict())
        existing.schema_version = parsed.schema_version
        db.commit()
        return _redirect("/nodes", msg=f"Updated '{parsed.tag}'", msg_type="success")

    db.add(Node(
        tag=parsed.tag, protocol=parsed.protocol, raw_url=parsed.raw_url,
        parsed_json=json.dumps(parsed.to_dict()),
        schema_version=parsed.schema_version, active=False,
    ))
    db.commit()
    return _redirect("/nodes", msg=f"Added '{parsed.tag}'", msg_type="success")


@app.post("/nodes/{node_id}/delete")
async def delete_node(node_id: int, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        return _redirect("/nodes", msg="Node not found", msg_type="error")
    was_active, tag = node.active, node.tag
    db.delete(node)
    db.commit()
    msg = f"Deleted '{tag}'"
    if was_active:
        msg += " (was active — sing-box still runs previous config)"
    return _redirect("/nodes", msg=msg, msg_type="success")


@app.post("/nodes/{node_id}/activate")
async def activate_node(node_id: int, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        return _redirect("/nodes", msg="Node not found", msg_type="error")
    try:
        parsed = _deserialize_node(node)
    except Exception as e:
        return _redirect("/nodes", msg=f"Failed to load node: {e}", msg_type="error")
    try:
        dns_p, route_p = _presets(db)
        config = generate_config(parsed, dns_preset=dns_p, route_preset=route_p)
    except Exception as e:
        return _redirect("/nodes", msg=f"Config generation failed: {e}", msg_type="error")

    result = await deploy_with_rollback(config, node.tag, health_check=True)

    db.add(DeployLog(
        node_tag=result.node_tag or node.tag,
        config_hash=result.config_hash,
        backup_name=result.backup_name,
        stage_reached=result.stage,
        success=result.success,
        rolled_back=result.rolled_back,
        error=result.error or None,
    ))

    if not result.success:
        db.commit()
        return _redirect("/nodes", msg=result.user_message(), msg_type="error")

    db.query(Node).update({"active": False})
    node.active = True
    db.query(Profile).update({"active": False})  # direct node activation = off-profile
    db.commit()
    return _redirect("/", msg=result.user_message(), msg_type="success")


# ---------------------------------------------------------------------------
# Import / Export
# ---------------------------------------------------------------------------

@app.get("/api/nodes/export")
async def export_nodes(db: Session = Depends(get_db)):
    nodes = db.query(Node).all()
    data = [{"tag": n.tag, "protocol": n.protocol, "raw_url": n.raw_url,
              "parsed": json.loads(n.parsed_json), "schema_version": n.schema_version}
            for n in nodes]
    content = json.dumps(data, indent=2, ensure_ascii=False)
    return StreamingResponse(
        iter([content]), media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=singbox-nodes.json"},
    )


@app.post("/api/nodes/import")
async def import_nodes(nodes_json: Annotated[str, Form()], db: Session = Depends(get_db)):
    try:
        data = json.loads(nodes_json)
        if not isinstance(data, list):
            raise ValueError("Expected a JSON array")
    except Exception as e:
        return _redirect("/nodes", msg=f"Import error: {e}", msg_type="error")

    imported, errors = 0, []
    for item in data:
        raw_url = item.get("raw_url", "")
        if not raw_url:
            continue
        try:
            parsed = parse_url(raw_url)
            ex = db.query(Node).filter(Node.tag == parsed.tag).first()
            if ex:
                ex.raw_url = parsed.raw_url
                ex.protocol = parsed.protocol
                ex.parsed_json = json.dumps(parsed.to_dict())
                ex.schema_version = parsed.schema_version
            else:
                db.add(Node(tag=parsed.tag, protocol=parsed.protocol, raw_url=parsed.raw_url,
                            parsed_json=json.dumps(parsed.to_dict()),
                            schema_version=parsed.schema_version, active=False))
            imported += 1
        except Exception as e:
            errors.append(f"{raw_url[:40]}: {e}")
    db.commit()
    msg = f"Imported {imported} nodes"
    if errors:
        msg += f". Skipped: {'; '.join(errors[:3])}"
    return _redirect("/nodes", msg=msg, msg_type="success" if imported else "error")


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    try:
        lines = min(int(request.query_params.get("lines", "100")), 500)
    except ValueError:
        lines = 100
    return templates.TemplateResponse(request, "logs.html", {
        "log_text": svc.get_logs(lines),
        "lines": lines,
    })


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

@app.get("/diagnostics", response_class=HTMLResponse)
async def diagnostics_page(request: Request, db: Session = Depends(get_db)):
    active_node = db.query(Node).filter(Node.active.is_(True)).first()
    return templates.TemplateResponse(request, "diagnostics.html", {
        "active_node": active_node,
    })


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------

@app.get("/backups", response_class=HTMLResponse)
async def backups_page(request: Request):
    return templates.TemplateResponse(request, "backups.html", {
        "backups": list_backups(),
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@app.post("/backups/{name}/restore")
async def restore_backup_route(name: str, db: Session = Depends(get_db)):
    if not re.match(r'^config_\d{8}_\d{6}\.json$', name):
        return _redirect("/backups", msg="Invalid backup filename", msg_type="error")
    ok, msg = restore_backup(name)
    if not ok:
        return _redirect("/backups", msg=f"Restore failed: {msg}", msg_type="error")
    svc.restart()
    db.query(Node).update({"active": False})
    db.commit()
    return _redirect("/", msg=f"Restored {name} — sing-box restarted", msg_type="success")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    dns_p, route_p = _presets(db)
    return templates.TemplateResponse(request, "settings.html", {
        "dns_preset": dns_p,
        "route_preset": route_p,
        "dns_presets": DNS_PRESETS,
        "route_presets": ROUTE_PRESETS,
        "notify_channels": notify.channels_status(),
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@app.post("/settings")
async def save_settings(
    dns_preset: Annotated[str, Form()],
    route_preset: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    if dns_preset not in DNS_PRESETS:
        return _redirect("/settings", msg=f"Invalid DNS preset", msg_type="error")
    if route_preset not in ROUTE_PRESETS:
        return _redirect("/settings", msg=f"Invalid route preset", msg_type="error")
    _set_setting(db, "dns_preset", dns_preset)
    _set_setting(db, "route_preset", route_preset)
    db.query(Profile).update({"active": False})  # manual settings change = off-profile
    db.commit()
    return _redirect("/settings", msg="Saved. Re-activate node to apply.", msg_type="success")


@app.post("/settings/notify-test")
async def notify_test():
    notify.fire("🔔 Test notification", "Sing-Box Manager notifications are working!", "info")
    return _redirect("/settings", msg="Test notification sent to all active channels.", msg_type="success")


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

@app.get("/profiles", response_class=HTMLResponse)
async def profiles_page(request: Request, db: Session = Depends(get_db)):
    profiles = db.query(Profile).order_by(Profile.created_at).all()
    nodes = db.query(Node).order_by(Node.tag).all()
    dns_p, route_p = _presets(db)
    return templates.TemplateResponse(request, "profiles.html", {
        "profiles": profiles,
        "nodes": nodes,
        "dns_presets": DNS_PRESETS,
        "route_presets": ROUTE_PRESETS,
        "dns_preset": dns_p,
        "route_preset": route_p,
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@app.post("/profiles")
async def create_profile(
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    node_tag: Annotated[str, Form()] = "",
    dns_preset: Annotated[str, Form()] = "quad9_tls",
    route_preset: Annotated[str, Form()] = "full_tunnel",
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        return _redirect("/profiles", msg="Profile name is required", msg_type="error")
    if dns_preset not in DNS_PRESETS:
        return _redirect("/profiles", msg=f"Invalid DNS preset: {dns_preset!r}", msg_type="error")
    if route_preset not in ROUTE_PRESETS:
        return _redirect("/profiles", msg=f"Invalid route preset: {route_preset!r}", msg_type="error")
    existing = db.query(Profile).filter(Profile.name == name).first()
    if existing:
        return _redirect("/profiles", msg=f"Profile '{name}' already exists", msg_type="error")
    db.add(Profile(
        name=name,
        description=description.strip() or None,
        node_tag=node_tag.strip() or None,
        dns_preset=dns_preset,
        route_preset=route_preset,
        active=False,
    ))
    db.commit()
    return _redirect("/profiles", msg=f"Created profile '{name}'", msg_type="success")


@app.post("/profiles/{profile_id}/activate")
async def activate_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return _redirect("/profiles", msg="Profile not found", msg_type="error")
    if not profile.node_tag:
        return _redirect("/profiles",
                         msg=f"Profile '{profile.name}' has no node — edit or delete it",
                         msg_type="error")

    node = db.query(Node).filter(Node.tag == profile.node_tag).first()
    if not node:
        return _redirect("/profiles",
                         msg=f"Node '{profile.node_tag}' no longer exists — update the profile",
                         msg_type="error")

    try:
        parsed = _deserialize_node(node)
    except Exception as e:
        return _redirect("/profiles", msg=f"Failed to load node: {e}", msg_type="error")
    try:
        config = generate_config(parsed,
                                 dns_preset=profile.dns_preset,
                                 route_preset=profile.route_preset)
    except Exception as e:
        return _redirect("/profiles", msg=f"Config generation failed: {e}", msg_type="error")

    result = await deploy_with_rollback(config, node.tag, health_check=True)

    db.add(DeployLog(
        node_tag=result.node_tag or node.tag,
        config_hash=result.config_hash,
        backup_name=result.backup_name,
        stage_reached=result.stage,
        success=result.success,
        rolled_back=result.rolled_back,
        error=result.error or None,
    ))

    if not result.success:
        db.commit()
        return _redirect("/profiles", msg=result.user_message(), msg_type="error")

    db.query(Node).update({"active": False})
    node.active = True
    db.query(Profile).update({"active": False})
    profile.active = True
    _set_setting(db, "dns_preset", profile.dns_preset)
    _set_setting(db, "route_preset", profile.route_preset)
    db.commit()
    return _redirect("/", msg=f"✓ Profile '{profile.name}' activated", msg_type="success")


@app.post("/profiles/{profile_id}/delete")
async def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return _redirect("/profiles", msg="Profile not found", msg_type="error")
    name = profile.name
    db.delete(profile)
    db.commit()
    return _redirect("/profiles", msg=f"Deleted profile '{name}'", msg_type="success")
