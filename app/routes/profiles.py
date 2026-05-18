from __future__ import annotations

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[assignment]

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.routes.common import redirect
from app.services import profiles as profile_service
from app.services.settings import presets
from app.singbox.dns import DNS_PRESETS
from app.singbox.routes import ROUTE_PRESETS
from app.web import templates

router = APIRouter()


@router.get("/profiles", response_class=HTMLResponse)
async def profiles_page(request: Request, db: Session = Depends(get_db)):
    dns_p, route_p = presets(db)
    page = profile_service.profiles_page_data(db, dns_p, route_p)
    return templates.TemplateResponse(request, "profiles.html", {
        "profiles": page.profiles,
        "nodes": page.nodes,
        "dns_presets": DNS_PRESETS,
        "route_presets": ROUTE_PRESETS,
        "dns_preset": page.dns_preset,
        "route_preset": page.route_preset,
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@router.post("/profiles")
async def create_profile(
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    node_tag: Annotated[str, Form()] = "",
    dns_preset: Annotated[str, Form()] = "quad9_tls",
    route_preset: Annotated[str, Form()] = "full_tunnel",
    db: Session = Depends(get_db),
):
    data = profile_service.ProfileInput(
        name=name,
        description=description,
        node_tag=node_tag,
        dns_preset=dns_preset,
        route_preset=route_preset,
    )
    return _profile_redirect(profile_service.create_profile(db, data))


@router.post("/profiles/{profile_id}/activate")
async def activate_profile(profile_id: int, db: Session = Depends(get_db)):
    return _profile_redirect(await profile_service.activate_profile(db, profile_id))


@router.post("/profiles/{profile_id}/delete")
async def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    return _profile_redirect(profile_service.delete_profile(db, profile_id))


def _profile_redirect(result: profile_service.ProfileMutationResult):
    return redirect(result.redirect_to, msg=result.message, msg_type="success" if result.ok else "error")
