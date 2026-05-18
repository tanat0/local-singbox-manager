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
from app.services import users as user_service
from app.services.users import ConfigGroupInput, ManagedUserInput, decode_node_tags
from app.web import templates

router = APIRouter()


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db)):
    page = user_service.users_page_data(db)
    return templates.TemplateResponse(request, "users.html", {
        "groups": page.groups,
        "users": page.users,
        "decode_node_tags": decode_node_tags,
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@router.post("/users/groups")
async def create_group(
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    node_tags: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    enabled: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    form = ConfigGroupInput(name=name, description=description, node_tags=node_tags, notes=notes, enabled=enabled == "on")
    return _user_redirect(user_service.create_group(db, form))


@router.post("/users/groups/{group_id}")
async def update_group(
    group_id: int,
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    node_tags: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    enabled: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    form = ConfigGroupInput(name=name, description=description, node_tags=node_tags, notes=notes, enabled=enabled == "on")
    return _user_redirect(user_service.update_group(db, group_id, form))


@router.post("/users/groups/{group_id}/delete")
async def delete_group(group_id: int, db: Session = Depends(get_db)):
    return _user_redirect(user_service.delete_group(db, group_id))


@router.post("/users")
async def create_user(
    telegram_id: Annotated[str, Form()],
    display_name: Annotated[str, Form()] = "",
    config_group_id: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    enabled: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    form = ManagedUserInput(
        telegram_id=telegram_id,
        display_name=display_name,
        config_group_id=config_group_id,
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
    notes: Annotated[str, Form()] = "",
    enabled: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    form = ManagedUserInput(
        telegram_id=telegram_id,
        display_name=display_name,
        config_group_id=config_group_id,
        notes=notes,
        enabled=enabled == "on",
    )
    return _user_redirect(user_service.update_user(db, user_id, form))


@router.post("/users/{user_id}/delete")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    return _user_redirect(user_service.delete_user(db, user_id))


def _user_redirect(result: user_service.MutationResult):
    return redirect("/users", msg=result.message, msg_type="success" if result.ok else "error")
