from __future__ import annotations

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[assignment]

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import notify
from app.db import get_db
from app.models import Profile
from app.routes.common import redirect
from app.services.settings import LOG_LEVELS, presets, set_setting, singbox_log_level
from app.singbox.dns import DNS_PRESETS
from app.singbox.routes import ROUTE_PRESETS
from app.web import templates

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    dns_p, route_p = presets(db)
    return templates.TemplateResponse(request, "settings.html", {
        "dns_preset": dns_p,
        "route_preset": route_p,
        "singbox_log_level": singbox_log_level(db),
        "log_levels": LOG_LEVELS,
        "dns_presets": DNS_PRESETS,
        "route_presets": ROUTE_PRESETS,
        "notify_channels": notify.channels_status(),
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@router.post("/settings")
async def save_settings(
    dns_preset: Annotated[str, Form()],
    route_preset: Annotated[str, Form()],
    singbox_log_level: Annotated[str, Form()] = "warn",
    db: Session = Depends(get_db),
):
    if dns_preset not in DNS_PRESETS:
        return redirect("/settings", msg="Invalid DNS preset", msg_type="error")
    if route_preset not in ROUTE_PRESETS:
        return redirect("/settings", msg="Invalid route preset", msg_type="error")
    if singbox_log_level not in LOG_LEVELS:
        return redirect("/settings", msg="Invalid log level", msg_type="error")
    set_setting(db, "dns_preset", dns_preset)
    set_setting(db, "route_preset", route_preset)
    set_setting(db, "singbox_log_level", singbox_log_level)
    db.query(Profile).update({"active": False})
    db.commit()
    return redirect("/settings", msg="Saved. Re-activate node to apply.", msg_type="success")


@router.post("/settings/notify-test")
async def notify_test():
    notify.fire("🔔 Test notification", "Sing-Box Manager notifications are working!", "info")
    return redirect("/settings", msg="Test notification sent to all active channels.", msg_type="success")
