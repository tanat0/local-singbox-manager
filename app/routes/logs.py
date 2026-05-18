from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.singbox import service as svc
from app.web import templates

router = APIRouter()


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    try:
        lines = min(int(request.query_params.get("lines", "100")), 500)
    except ValueError:
        lines = 100
    mode = request.query_params.get("mode", "all")
    mode = mode if mode in {"all", "problems", "fatal"} else "all"
    grep = request.query_params.get("grep", "")
    return templates.TemplateResponse(request, "logs.html", {
        "log_text": svc.get_logs(lines, mode=mode, grep=grep),
        "lines": lines,
        "mode": mode,
        "grep": grep,
    })
