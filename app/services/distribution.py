from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, TYPE_CHECKING

from app.services.users import decode_node_tags

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass
class UserAssignment:
    user: Optional[Any]
    group: Optional[Any]
    nodes: List[Any]
    error: str = ""


def get_user_assignment(db: "Session", telegram_id: str) -> UserAssignment:
    from app.models import ConfigGroup, ManagedUser, Node

    user = db.query(ManagedUser).filter(ManagedUser.telegram_id == telegram_id).first()
    if not user:
        return UserAssignment(None, None, [], "User is not registered.")
    if not user.enabled:
        return UserAssignment(user, None, [], "User is disabled.")
    if not user.config_group_id:
        return UserAssignment(user, None, [], "No config group assigned.")

    group = db.query(ConfigGroup).filter(ConfigGroup.id == user.config_group_id).first()
    if not group:
        return UserAssignment(user, None, [], "Assigned config group no longer exists.")
    if not group.enabled:
        return UserAssignment(user, group, [], "Assigned config group is disabled.")

    tags = decode_node_tags(group.node_tags_json)
    if not tags:
        return UserAssignment(user, group, [], "Assigned config group has no nodes.")

    nodes = db.query(Node).filter(Node.tag.in_(tags)).order_by(Node.tag).all()
    if not nodes:
        return UserAssignment(user, group, [], "Assigned nodes were not found.")
    return UserAssignment(user, group, nodes)


def record_delivery(
    db: "Session",
    telegram_id: str,
    action: str,
    success: bool,
    assignment: Optional[UserAssignment] = None,
    detail: str = "",
) -> None:
    from app.models import ConfigDeliveryLog

    user = assignment.user if assignment else None
    group = assignment.group if assignment else None
    db.add(ConfigDeliveryLog(
        managed_user_id=user.id if user else None,
        telegram_id=telegram_id,
        config_group_id=group.id if group else None,
        action=action,
        success=success,
        detail=detail or None,
    ))
    db.commit()


def format_user_status(assignment: UserAssignment) -> str:
    if assignment.error:
        return assignment.error
    user = assignment.user
    group = assignment.group
    label = (user.display_name or user.telegram_id) if user else "user"
    return (
        f"User: {label}\n"
        f"Group: {group.name if group else '-'}\n"
        f"Assigned configs: {len(assignment.nodes)}"
    )


def format_user_configs(assignment: UserAssignment) -> str:
    if assignment.error:
        return assignment.error
    group = assignment.group
    lines = [
        f"Config group: {group.name if group else '-'}",
        "Import one of these links in a compatible client:",
        "",
    ]
    for node in assignment.nodes:
        lines.append(f"{node.tag} [{node.protocol}]")
        lines.append(node.raw_url)
        lines.append("")
    return "\n".join(lines).strip()
