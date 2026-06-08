from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.health import check_external_ip, run_health_checks
from app.repositories import NodeRepository, ProfileRepository
from app.routes.common import redirect
from app.services.dashboard import (
    render_config_diff,
    render_external_ip,
    render_health_report,
    render_log_insights,
    render_log_output,
    render_sysinfo,
    validate_node_config,
)
from app.services.log_insights import summarize_problem_logs
from app.services.metrics import connectivity_summary, latency_series, node_health_summary
from app.services.nodes import latest_deploy_logs
from app.singbox import service as svc
from app.singbox.deployer import get_current_config
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
        "health_24h": connectivity_summary(db, 24),
        "health_7d": connectivity_summary(db, 168),
        "node_health": node_health_summary(db, 168),
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
    result = validate_node_config(db, node)
    return redirect("/", msg=result.message, msg_type="success" if result.ok else "error")


@router.get("/api/ip", response_class=HTMLResponse)
async def api_ip():
    ip, err = await check_external_ip()
    return HTMLResponse(render_external_ip(ip, err))


@router.get("/api/logs", response_class=HTMLResponse)
async def api_logs(lines: int = 100, mode: str = "all", grep: str = ""):
    lines = min(lines, 500)
    mode = mode if mode in {"all", "problems", "fatal"} else "all"
    return HTMLResponse(render_log_output(svc.get_logs(lines, mode=mode, grep=grep)))


@router.get("/api/log-insights", response_class=HTMLResponse)
async def api_log_insights(lines: int = 500):
    bounded_lines = min(max(lines, 50), 2000)
    text = svc.get_logs(bounded_lines, mode="problems")
    return HTMLResponse(render_log_insights(summarize_problem_logs(text)))


@router.get("/api/health", response_class=HTMLResponse)
async def api_health():
    report = await run_health_checks()
    return HTMLResponse(render_health_report(report))


@router.get("/api/sysinfo", response_class=HTMLResponse)
async def api_sysinfo():
    return HTMLResponse(render_sysinfo(svc.get_version()))


@router.get("/api/metrics/latency")
async def api_metrics_latency(hours: int = 24, db: Session = Depends(get_db)):
    return JSONResponse(latency_series(db, hours))


@router.get("/api/diff", response_class=HTMLResponse)
async def api_diff(db: Session = Depends(get_db)):
    node = NodeRepository(db).get_active()
    return HTMLResponse(render_config_diff(db, node, get_current_config()))
