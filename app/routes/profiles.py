from __future__ import annotations

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[assignment]

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Node, Profile
from app.routes.common import redirect
from app.services.deploy import activate_node as activate_node_service
from app.services.settings import presets, set_setting
from app.singbox.dns import DNS_PRESETS
from app.singbox.routes import ROUTE_PRESETS
from app.web import templates

router = APIRouter()


@router.get("/profiles", response_class=HTMLResponse)
async def profiles_page(request: Request, db: Session = Depends(get_db)):
    profiles = db.query(Profile).order_by(Profile.created_at).all()
    nodes = db.query(Node).order_by(Node.tag).all()
    dns_p, route_p = presets(db)
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


@router.post("/profiles")
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
        return redirect("/profiles", msg="Profile name is required", msg_type="error")
    if dns_preset not in DNS_PRESETS:
        return redirect("/profiles", msg=f"Invalid DNS preset: {dns_preset!r}", msg_type="error")
    if route_preset not in ROUTE_PRESETS:
        return redirect("/profiles", msg=f"Invalid route preset: {route_preset!r}", msg_type="error")
    existing = db.query(Profile).filter(Profile.name == name).first()
    if existing:
        return redirect("/profiles", msg=f"Profile '{name}' already exists", msg_type="error")
    db.add(Profile(
        name=name,
        description=description.strip() or None,
        node_tag=node_tag.strip() or None,
        dns_preset=dns_preset,
        route_preset=route_preset,
        active=False,
    ))
    db.commit()
    return redirect("/profiles", msg=f"Created profile '{name}'", msg_type="success")


@router.post("/profiles/{profile_id}/activate")
async def activate_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return redirect("/profiles", msg="Profile not found", msg_type="error")
    if not profile.node_tag:
        return redirect(
            "/profiles",
            msg=f"Profile '{profile.name}' has no node — edit or delete it",
            msg_type="error",
        )

    node = db.query(Node).filter(Node.tag == profile.node_tag).first()
    if not node:
        return redirect(
            "/profiles",
            msg=f"Node '{profile.node_tag}' no longer exists — update the profile",
            msg_type="error",
        )

    result = await activate_node_service(db, node, profile=profile)
    if not result.ok:
        return redirect("/profiles", msg=result.message, msg_type="error")
    set_setting(db, "dns_preset", profile.dns_preset)
    set_setting(db, "route_preset", profile.route_preset)
    db.commit()
    return redirect("/", msg=f"✓ Profile '{profile.name}' activated", msg_type="success")


@router.post("/profiles/{profile_id}/delete")
async def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return redirect("/profiles", msg="Profile not found", msg_type="error")
    name = profile.name
    db.delete(profile)
    db.commit()
    return redirect("/profiles", msg=f"Deleted profile '{name}'", msg_type="success")
