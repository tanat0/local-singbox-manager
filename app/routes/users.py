from __future__ import annotations

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[assignment]

from typing import Callable

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.routes.common import redirect
from app.services import users as user_service
from app.services.client_configs import (
    ClientConfigDocument,
    build_client_config_document,
    build_sbclient_bundle_document,
)
from app.services.distribution import UserAssignment, get_group_artifact_assignment
from app.services.node_tags import decode_node_tags
from app.services.users import ConfigGroupInput, ManagedUserInput
from app.web import templates

_ARTIFACT_BUILD_FAILED = "Could not prepare this artifact."

router = APIRouter()


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db)):
    page = user_service.users_page_data(db)
    return templates.TemplateResponse(request, "users.html", {
        "groups": page.groups,
        "users": page.users,
        "nodes": page.nodes,
        "deliveries": page.deliveries,
        "route_presets": page.route_presets,
        "decode_node_tags": decode_node_tags,
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@router.post("/users/groups")
async def create_group(
    request: Request,
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    route_preset: Annotated[str, Form()] = "full_tunnel",
    refresh_limit_per_hour: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    enabled: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    form_data = await request.form()
    form = ConfigGroupInput(
        name=name,
        description=description,
        node_tags=list(form_data.getlist("node_tags")),
        route_preset=route_preset,
        refresh_limit_per_hour=refresh_limit_per_hour,
        notes=notes,
        enabled=enabled == "on",
    )
    return _user_redirect(user_service.create_group(db, form))


@router.post("/users/groups/{group_id}")
async def update_group(
    request: Request,
    group_id: int,
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    route_preset: Annotated[str, Form()] = "full_tunnel",
    refresh_limit_per_hour: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    enabled: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    form_data = await request.form()
    form = ConfigGroupInput(
        name=name,
        description=description,
        node_tags=list(form_data.getlist("node_tags")),
        route_preset=route_preset,
        refresh_limit_per_hour=refresh_limit_per_hour,
        notes=notes,
        enabled=enabled == "on",
    )
    return _user_redirect(await user_service.update_group(db, group_id, form))


@router.post("/users/groups/{group_id}/delete")
async def delete_group(group_id: int, db: Session = Depends(get_db)):
    return _user_redirect(user_service.delete_group(db, group_id))


@router.get("/users/groups/{group_id}/download/config")
async def download_group_config(group_id: int, db: Session = Depends(get_db)):
    return _download_group_artifact(db, group_id, build_client_config_document)


@router.get("/users/groups/{group_id}/download/sbclient")
async def download_group_sbclient(group_id: int, db: Session = Depends(get_db)):
    return _download_group_artifact(db, group_id, build_sbclient_bundle_document)


@router.post("/users")
async def create_user(
    telegram_id: Annotated[str, Form()],
    display_name: Annotated[str, Form()] = "",
    config_group_id: Annotated[str, Form()] = "",
    refresh_limit_per_hour: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    enabled: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    form = ManagedUserInput(
        telegram_id=telegram_id,
        display_name=display_name,
        config_group_id=config_group_id,
        refresh_limit_per_hour=refresh_limit_per_hour,
        notes=notes,
        enabled=enabled == "on",
    )
    return _user_redirect(user_service.create_user(db, form))


@router.post("/users/{user_id}")
async def update_user(
    user_id: int,
    telegram_id: Annotated[str, Form()],
    display_name: Annotated[str, Form()] = "",
    config_group_id: Annotated[str, Form()] = "",
    refresh_limit_per_hour: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    enabled: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    form = ManagedUserInput(
        telegram_id=telegram_id,
        display_name=display_name,
        config_group_id=config_group_id,
        refresh_limit_per_hour=refresh_limit_per_hour,
        notes=notes,
        enabled=enabled == "on",
    )
    return _user_redirect(user_service.update_user(db, user_id, form))


@router.post("/users/{user_id}/delete")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    return _user_redirect(user_service.delete_user(db, user_id))


def _user_redirect(result: user_service.MutationResult):
    return redirect("/users", msg=result.message, msg_type="success" if result.ok else "error")


def _download_group_artifact(
    db: Session,
    group_id: int,
    builder: Callable[[UserAssignment], ClientConfigDocument],
) -> Response:
    assignment = get_group_artifact_assignment(db, group_id)
    if assignment.error:
        return redirect("/users", msg=assignment.error, msg_type="error")
    try:
        document = builder(assignment)
    except ValueError as exc:
        return redirect("/users", msg=_safe_build_error(exc), msg_type="error")
    except Exception:
        return redirect("/users", msg=_ARTIFACT_BUILD_FAILED, msg_type="error")
    return _artifact_response(document)


def _safe_build_error(exc: ValueError) -> str:
    message = str(exc).strip()
    if not message or "://" in message:
        return _ARTIFACT_BUILD_FAILED
    return message


def _artifact_response(document: ClientConfigDocument) -> Response:
    return Response(
        content=document.content,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{document.filename}"',
            "Cache-Control": "no-store",
        },
    )
