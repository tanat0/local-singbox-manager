from __future__ import annotations

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[assignment]

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.db import get_db
from app.routes.common import redirect
from app.services.servers import ALLOWED_ALIASES, inventory, probe_server, save_notes
from app.web import templates

router = APIRouter()


@router.get("/servers", response_class=HTMLResponse)
async def servers_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "servers.html", {
        "servers": inventory(db),
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@router.post("/servers/notes")
async def save_server_notes(
    db: Session = Depends(get_db),
    notes_hykz: Annotated[str, Form()] = "",
    notes_aeza: Annotated[str, Form()] = "",
    notes_swvps: Annotated[str, Form()] = "",
    notes_ge_vps: Annotated[str, Form()] = "",
):
    save_notes(db, {
        "hykz": notes_hykz,
        "aeza": notes_aeza,
        "swvps": notes_swvps,
        "ge_vps": notes_ge_vps,
    })
    return redirect("/servers", msg="Notes saved.", msg_type="success")


@router.post("/servers/{alias}/probe", response_class=HTMLResponse)
async def probe_one_server(request: Request, alias: str, db: Session = Depends(get_db)):
    if alias not in ALLOWED_ALIASES:
        return HTMLResponse('<p class="text-dim">Unknown SSH alias.</p>', status_code=404)
    snapshot = await run_in_threadpool(probe_server, alias)
    notes = next((item.notes for item in inventory(db) if item.spec.alias == alias), "")
    snapshot.notes = notes
    return templates.TemplateResponse(request, "partials/server_probe.html", {
        "server": snapshot,
    })
