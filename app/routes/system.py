from __future__ import annotations

import re

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[assignment]

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    create_session_token,
    rate_limit_ok,
    verify_password,
)
from app.db import get_db
from app.logging_config import get_logger
from app.models import Node
from app.routes.common import redirect
from app.singbox import service as svc
from app.singbox.deployer import list_backups, restore_backup
from app.version import VERSION
from app.web import templates

router = APIRouter()
_log = get_logger(__name__)


@router.get("/health")
async def health_probe():
    return JSONResponse({"status": "ok", "version": VERSION})


@router.get("/version")
async def version_probe():
    return JSONResponse({"app": VERSION, "singbox": svc.get_version() or "unknown"})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": ""})


@router.post("/login")
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
        SESSION_COOKIE,
        create_session_token(),
        httponly=True,
        samesite="strict",
        max_age=SESSION_MAX_AGE,
        path="/",
    )
    return response


@router.post("/logout")
async def logout_post():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/diagnostics", response_class=HTMLResponse)
async def diagnostics_page(request: Request, db: Session = Depends(get_db)):
    active_node = db.query(Node).filter(Node.active.is_(True)).first()
    return templates.TemplateResponse(request, "diagnostics.html", {
        "active_node": active_node,
    })


@router.get("/backups", response_class=HTMLResponse)
async def backups_page(request: Request):
    return templates.TemplateResponse(request, "backups.html", {
        "backups": list_backups(),
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@router.post("/backups/{name}/restore")
async def restore_backup_route(name: str, db: Session = Depends(get_db)):
    if not re.match(r'^config_\d{8}_\d{6}\.json$', name):
        return redirect("/backups", msg="Invalid backup filename", msg_type="error")
    ok, msg = restore_backup(name)
    if not ok:
        return redirect("/backups", msg=f"Restore failed: {msg}", msg_type="error")
    svc.restart()
    db.query(Node).update({"active": False})
    db.commit()
    return redirect("/", msg=f"Restored {name} — sing-box restarted", msg_type="success")
