from __future__ import annotations

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[assignment]

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ConfigGroup, ManagedUser, Node
from app.routes.common import redirect
from app.services.users import decode_node_tags, encode_node_tags, parse_node_tags
from app.web import templates

router = APIRouter()


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db)):
    groups = db.query(ConfigGroup).order_by(ConfigGroup.enabled.desc(), ConfigGroup.name).all()
    users = db.query(ManagedUser).order_by(ManagedUser.enabled.desc(), ManagedUser.created_at.desc()).all()
    nodes = db.query(Node).order_by(Node.tag).all()
    return templates.TemplateResponse(request, "users.html", {
        "groups": groups,
        "users": users,
        "nodes": nodes,
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
    name = name.strip()
    if not name:
        return redirect("/users", msg="Group name is required", msg_type="error")
    existing = db.query(ConfigGroup).filter(ConfigGroup.name == name).first()
    if existing:
        return redirect("/users", msg=f"Group '{name}' already exists", msg_type="error")
    db.add(ConfigGroup(
        name=name,
        description=description.strip() or None,
        node_tags_json=encode_node_tags(parse_node_tags(node_tags)),
        notes=notes.strip() or None,
        enabled=enabled == "on",
    ))
    db.commit()
    return redirect("/users", msg=f"Created group '{name}'", msg_type="success")


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
    group = db.query(ConfigGroup).filter(ConfigGroup.id == group_id).first()
    if not group:
        return redirect("/users", msg="Group not found", msg_type="error")
    name = name.strip()
    if not name:
        return redirect("/users", msg="Group name is required", msg_type="error")
    duplicate = db.query(ConfigGroup).filter(ConfigGroup.name == name, ConfigGroup.id != group_id).first()
    if duplicate:
        return redirect("/users", msg=f"Group '{name}' already exists", msg_type="error")
    group.name = name
    group.description = description.strip() or None
    group.node_tags_json = encode_node_tags(parse_node_tags(node_tags))
    group.notes = notes.strip() or None
    group.enabled = enabled == "on"
    db.commit()
    return redirect("/users", msg=f"Updated group '{name}'", msg_type="success")


@router.post("/users/groups/{group_id}/delete")
async def delete_group(group_id: int, db: Session = Depends(get_db)):
    group = db.query(ConfigGroup).filter(ConfigGroup.id == group_id).first()
    if not group:
        return redirect("/users", msg="Group not found", msg_type="error")
    name = group.name
    db.query(ManagedUser).filter(ManagedUser.config_group_id == group_id).update({"config_group_id": None})
    db.delete(group)
    db.commit()
    return redirect("/users", msg=f"Deleted group '{name}'", msg_type="success")


@router.post("/users")
async def create_user(
    telegram_id: Annotated[str, Form()],
    display_name: Annotated[str, Form()] = "",
    config_group_id: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    enabled: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    telegram_id = telegram_id.strip()
    if not telegram_id:
        return redirect("/users", msg="Telegram ID is required", msg_type="error")
    existing = db.query(ManagedUser).filter(ManagedUser.telegram_id == telegram_id).first()
    if existing:
        return redirect("/users", msg=f"User '{telegram_id}' already exists", msg_type="error")
    group_id = int(config_group_id) if config_group_id.isdigit() else None
    db.add(ManagedUser(
        telegram_id=telegram_id,
        display_name=display_name.strip() or None,
        config_group_id=group_id,
        notes=notes.strip() or None,
        enabled=enabled == "on",
    ))
    db.commit()
    return redirect("/users", msg=f"Created user '{telegram_id}'", msg_type="success")


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
    user = db.query(ManagedUser).filter(ManagedUser.id == user_id).first()
    if not user:
        return redirect("/users", msg="User not found", msg_type="error")
    telegram_id = telegram_id.strip()
    if not telegram_id:
        return redirect("/users", msg="Telegram ID is required", msg_type="error")
    duplicate = db.query(ManagedUser).filter(
        ManagedUser.telegram_id == telegram_id,
        ManagedUser.id != user_id,
    ).first()
    if duplicate:
        return redirect("/users", msg=f"User '{telegram_id}' already exists", msg_type="error")
    user.telegram_id = telegram_id
    user.display_name = display_name.strip() or None
    user.config_group_id = int(config_group_id) if config_group_id.isdigit() else None
    user.notes = notes.strip() or None
    user.enabled = enabled == "on"
    db.commit()
    return redirect("/users", msg=f"Updated user '{telegram_id}'", msg_type="success")


@router.post("/users/{user_id}/delete")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(ManagedUser).filter(ManagedUser.id == user_id).first()
    if not user:
        return redirect("/users", msg="User not found", msg_type="error")
    label = user.display_name or user.telegram_id
    db.delete(user)
    db.commit()
    return redirect("/users", msg=f"Deleted user '{label}'", msg_type="success")
