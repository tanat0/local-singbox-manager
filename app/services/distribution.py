from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List, Optional

from app.services.node_tags import decode_node_tags
from app.singbox.routes import DEFAULT_ROUTE_PRESET, ROUTE_PRESETS

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models import ConfigGroup, ManagedUser, Node


@dataclass
class UserAssignment:
    user: Optional["ManagedUser"]
    group: Optional["ConfigGroup"]
    nodes: List["Node"]
    error: str = ""
    config_version: Optional[int] = None
    config_fingerprint: str = ""
    route_preset: str = DEFAULT_ROUTE_PRESET
    refresh_limit_per_hour: int = 10


DELIVERY_ACTIONS = ("/config", "/refresh", "/sbclient")
DEFAULT_REFRESH_LIMIT_PER_HOUR = 10
RATE_LIMIT_MESSAGE = "Refresh limit reached. Try later."


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
    if len(nodes) != len(set(tags)):
        return UserAssignment(user, group, nodes, "Some assigned nodes were not found.")
    route_preset = group.route_preset or DEFAULT_ROUTE_PRESET
    if route_preset not in ROUTE_PRESETS:
        return UserAssignment(user, group, [], "Assigned config group has an invalid route preset.")
    return UserAssignment(
        user,
        group,
        nodes,
        config_version=group.config_version,
        config_fingerprint=config_fingerprint(nodes, route_preset),
        route_preset=route_preset,
        refresh_limit_per_hour=effective_refresh_limit(user, group),
    )


def config_fingerprint(nodes: List["Node"], route_preset: str = DEFAULT_ROUTE_PRESET) -> str:
    payload = {
        "route_preset": route_preset,
        "nodes": [
            {"tag": node.tag, "protocol": node.protocol, "raw_url": node.raw_url}
            for node in sorted(nodes, key=lambda item: item.tag)
        ],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def effective_refresh_limit(user: "ManagedUser", group: "ConfigGroup") -> int:
    user_limit = _positive_int_or_none(user.refresh_limit_per_hour)
    if user_limit is not None:
        return user_limit
    group_limit = _positive_int_or_none(group.refresh_limit_per_hour)
    if group_limit is not None:
        return group_limit
    return DEFAULT_REFRESH_LIMIT_PER_HOUR


def refresh_limit_exceeded(db: "Session", assignment: UserAssignment, now: Optional[datetime] = None) -> bool:
    from app.models import ConfigDeliveryLog

    if not assignment.user:
        return False
    cutoff = (now or datetime.utcnow()) - timedelta(hours=1)
    count = (
        db.query(ConfigDeliveryLog)
        .filter(
            ConfigDeliveryLog.telegram_id == assignment.user.telegram_id,
            ConfigDeliveryLog.action.in_(DELIVERY_ACTIONS),
            ConfigDeliveryLog.created_at >= cutoff,
        )
        .count()
    )
    return count >= assignment.refresh_limit_per_hour


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
        config_version=assignment.config_version if assignment else None,
        config_fingerprint=assignment.config_fingerprint if assignment else None,
        detail=detail or None,
    ))
    db.commit()


def _positive_int_or_none(value: object) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
