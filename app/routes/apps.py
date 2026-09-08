from __future__ import annotations

import mimetypes

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[assignment]

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.routes.common import redirect
from app.services.app_bypass import (
    build_entries_from_form,
    custom_process_text,
    load_bypass_entries,
    save_bypass_entries,
    selected_app_ids,
)
from app.services.desktop_apps import get_desktop_app, list_desktop_apps
from app.web import templates

router = APIRouter()

_PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="8" fill="#2a2a38"/>'
    '<text x="16" y="21" text-anchor="middle" font-size="14" fill="#6e6e88">?</text>'
    "</svg>"
)


@router.get("/apps", response_class=HTMLResponse)
async def apps_page(request: Request, db: Session = Depends(get_db)):
    apps = list_desktop_apps()
    entries = load_bypass_entries(db)
    selected = selected_app_ids(entries)
    overrides = {
        entry.app_id: entry.process_name
        for entry in entries
        if not entry.custom and entry.process_name
    }
    return templates.TemplateResponse(request, "apps.html", {
        "apps": apps,
        "selected_ids": selected,
        "overrides": overrides,
        "custom_text": custom_process_text(entries),
        "selected_count": len(entries),
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@router.post("/apps")
async def save_apps(
    request: Request,
    db: Session = Depends(get_db),
    custom_processes: Annotated[str, Form()] = "",
):
    form = await request.form()
    app_ids = [str(value) for value in form.getlist("app_ids")]
    overrides = {
        app_id: str(form.get(f"process-{app_id}", "") or "")
        for app_id in app_ids
    }
    entries = build_entries_from_form(app_ids, overrides, custom_processes)
    save_bypass_entries(db, entries)
    return redirect(
        "/apps",
        msg=f"Saved {len(entries)} bypass entries. Re-activate the node to apply.",
        msg_type="success",
    )


@router.get("/apps/icon")
async def app_icon(app_id: Annotated[str, Query()]):
    app = get_desktop_app(app_id)
    if app and app.icon_path and app.icon_path.is_file():
        media_type = mimetypes.guess_type(str(app.icon_path))[0] or "application/octet-stream"
        return FileResponse(
            path=app.icon_path,
            media_type=media_type,
            headers={"Cache-Control": "private, max-age=86400"},
        )
    return Response(
        content=_PLACEHOLDER_SVG,
        media_type="image/svg+xml",
        headers={"Cache-Control": "private, max-age=3600"},
    )
