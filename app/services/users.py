from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import ConfigDeliveryLog, ConfigGroup, ManagedUser, Node
from app.repositories import UserRepository
from app.services.node_tags import decode_node_tags, encode_node_tags, parse_node_tags
from app.telegram.client import TelegramApiClient


@dataclass(frozen=True)
class MutationResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class ConfigGroupInput:
    name: str
    description: str = ""
    node_tags: Optional[List[str]] = None
    refresh_limit_per_hour: str = ""
    notes: str = ""
    enabled: bool = False


@dataclass(frozen=True)
class ManagedUserInput:
    telegram_id: str
    display_name: str = ""
    config_group_id: str = ""
    refresh_limit_per_hour: str = ""
    notes: str = ""
    enabled: bool = False


@dataclass(frozen=True)
class UsersPageData:
    groups: List[ConfigGroup]
    users: List[ManagedUser]
    nodes: List[Node]
    deliveries: List["DeliveryLogView"]


@dataclass(frozen=True)
class DeliveryLogView:
    created_at: object
    telegram_id: str
    action: str
    success: bool
    group_name: str
    config_version: Optional[int]
    config_fingerprint: str
    detail: str


def users_page_data(db: Session) -> UsersPageData:
    repo = UserRepository(db)
    groups = repo.list_groups()
    group_names = {group.id: group.name for group in groups}
    return UsersPageData(
        groups=groups,
        users=repo.list_users(),
        nodes=db.query(Node).order_by(Node.tag).all(),
        deliveries=[
            _delivery_view(row, group_names)
            for row in repo.list_recent_deliveries()
        ],
    )


def create_group(db: Session, form: ConfigGroupInput) -> MutationResult:
    repo = UserRepository(db)
    name = form.name.strip()
    if not name:
        return MutationResult(False, "Group name is required")
    if repo.get_group_by_name(name):
        return MutationResult(False, f"Group '{name}' already exists")
    node_tags_result = _validated_node_tags(db, form.node_tags or [])
    if not node_tags_result.ok:
        return MutationResult(False, node_tags_result.message)
    limit_result = _parse_optional_positive_int(form.refresh_limit_per_hour, "Group refresh limit")
    if not limit_result.ok:
        return MutationResult(False, limit_result.message)

    db.add(ConfigGroup(
        name=name,
        description=form.description.strip() or None,
        node_tags_json=encode_node_tags(node_tags_result.tags),
        refresh_limit_per_hour=limit_result.value,
        notes=form.notes.strip() or None,
        enabled=form.enabled,
    ))
    db.commit()
    return MutationResult(True, f"Created group '{name}'")


async def update_group(db: Session, group_id: int, form: ConfigGroupInput) -> MutationResult:
    repo = UserRepository(db)
    group = repo.get_group(group_id)
    if not group:
        return MutationResult(False, "Group not found")

    name = form.name.strip()
    if not name:
        return MutationResult(False, "Group name is required")
    if repo.get_group_name_duplicate(name, exclude_id=group_id):
        return MutationResult(False, f"Group '{name}' already exists")
    node_tags_result = _validated_node_tags(db, form.node_tags or [])
    if not node_tags_result.ok:
        return MutationResult(False, node_tags_result.message)
    limit_result = _parse_optional_positive_int(form.refresh_limit_per_hour, "Group refresh limit")
    if not limit_result.ok:
        return MutationResult(False, limit_result.message)

    previous_tags = decode_node_tags(group.node_tags_json)
    nodes_changed = set(previous_tags) != set(node_tags_result.tags)
    group.name = name
    group.description = form.description.strip() or None
    group.node_tags_json = encode_node_tags(node_tags_result.tags)
    group.refresh_limit_per_hour = limit_result.value
    group.notes = form.notes.strip() or None
    group.enabled = form.enabled
    if nodes_changed:
        group.config_version = int(group.config_version or 1) + 1
    db.commit()
    if nodes_changed and group.enabled:
        await notify_group_config_changed(db, group)
    return MutationResult(True, f"Updated group '{name}'")


def delete_group(db: Session, group_id: int) -> MutationResult:
    repo = UserRepository(db)
    group = repo.get_group(group_id)
    if not group:
        return MutationResult(False, "Group not found")

    name = group.name
    repo.clear_group_assignments(group_id)
    db.delete(group)
    db.commit()
    return MutationResult(True, f"Deleted group '{name}'")


def create_user(db: Session, form: ManagedUserInput) -> MutationResult:
    repo = UserRepository(db)
    telegram_id = form.telegram_id.strip()
    if not telegram_id:
        return MutationResult(False, "Telegram ID is required")
    if repo.get_user_by_telegram_id(telegram_id):
        return MutationResult(False, f"User '{telegram_id}' already exists")
    limit_result = _parse_optional_positive_int(form.refresh_limit_per_hour, "User refresh limit")
    if not limit_result.ok:
        return MutationResult(False, limit_result.message)

    db.add(ManagedUser(
        telegram_id=telegram_id,
        display_name=form.display_name.strip() or None,
        config_group_id=_parse_group_id(form.config_group_id),
        refresh_limit_per_hour=limit_result.value,
        notes=form.notes.strip() or None,
        enabled=form.enabled,
    ))
    db.commit()
    return MutationResult(True, f"Created user '{telegram_id}'")


def update_user(db: Session, user_id: int, form: ManagedUserInput) -> MutationResult:
    repo = UserRepository(db)
    user = repo.get_user(user_id)
    if not user:
        return MutationResult(False, "User not found")

    telegram_id = form.telegram_id.strip()
    if not telegram_id:
        return MutationResult(False, "Telegram ID is required")
    if repo.get_user_telegram_duplicate(telegram_id, exclude_id=user_id):
        return MutationResult(False, f"User '{telegram_id}' already exists")
    limit_result = _parse_optional_positive_int(form.refresh_limit_per_hour, "User refresh limit")
    if not limit_result.ok:
        return MutationResult(False, limit_result.message)

    user.telegram_id = telegram_id
    user.display_name = form.display_name.strip() or None
    user.config_group_id = _parse_group_id(form.config_group_id)
    user.refresh_limit_per_hour = limit_result.value
    user.notes = form.notes.strip() or None
    user.enabled = form.enabled
    db.commit()
    return MutationResult(True, f"Updated user '{telegram_id}'")


def delete_user(db: Session, user_id: int) -> MutationResult:
    repo = UserRepository(db)
    user = repo.get_user(user_id)
    if not user:
        return MutationResult(False, "User not found")

    label = user.display_name or user.telegram_id
    db.delete(user)
    db.commit()
    return MutationResult(True, f"Deleted user '{label}'")


def _parse_group_id(raw: str) -> Optional[int]:
    value = raw.strip()
    return int(value) if value.isdigit() else None


async def notify_group_config_changed(db: Session, group: ConfigGroup) -> None:
    from app.services.distribution import config_fingerprint

    repo = UserRepository(db)
    users = repo.list_enabled_users_for_group(group.id)
    if not users:
        return

    nodes = db.query(Node).filter(Node.tag.in_(decode_node_tags(group.node_tags_json))).order_by(Node.tag).all()
    fingerprint = config_fingerprint(nodes) if nodes else ""
    message = (
        f"Assigned config changed for group '{group.name}'.\n"
        "Use /refresh to get the latest config."
    )
    client = TelegramApiClient(settings.telegram.bot_token) if settings.telegram.bot_token else None
    for user in users:
        success = False
        detail = "Telegram bot token is not configured"
        if client:
            try:
                await client.send_message(int(user.telegram_id), message)
                success = True
                detail = "config change notification sent"
            except (TypeError, ValueError):
                detail = "invalid Telegram ID"
            except Exception as exc:
                detail = f"notification failed: {type(exc).__name__}"

        db.add(ConfigDeliveryLog(
            managed_user_id=user.id,
            telegram_id=user.telegram_id,
            config_group_id=group.id,
            action="notify_config_changed",
            success=success,
            config_version=group.config_version,
            config_fingerprint=fingerprint or None,
            detail=detail,
        ))
    db.commit()


@dataclass(frozen=True)
class _NodeTagsResult:
    ok: bool
    tags: List[str]
    message: str = ""


@dataclass(frozen=True)
class _LimitResult:
    ok: bool
    value: Optional[int]
    message: str = ""


def _validated_node_tags(db: Session, raw_tags: object) -> _NodeTagsResult:
    tags = parse_node_tags(raw_tags)
    if not tags:
        return _NodeTagsResult(True, [])
    existing = {
        row.tag
        for row in db.query(Node).filter(Node.tag.in_(tags)).all()
    }
    missing = [tag for tag in tags if tag not in existing]
    if missing:
        return _NodeTagsResult(False, [], f"Unknown node tag(s): {', '.join(missing[:5])}")
    return _NodeTagsResult(True, tags)


def _parse_optional_positive_int(raw: str, label: str) -> _LimitResult:
    value = raw.strip()
    if not value:
        return _LimitResult(True, None)
    if not value.isdigit():
        return _LimitResult(False, None, f"{label} must be a positive integer")
    parsed = int(value)
    if parsed <= 0:
        return _LimitResult(False, None, f"{label} must be greater than zero")
    return _LimitResult(True, parsed)


def _delivery_view(row: ConfigDeliveryLog, group_names: dict) -> DeliveryLogView:
    return DeliveryLogView(
        created_at=row.created_at,
        telegram_id=row.telegram_id,
        action=row.action,
        success=row.success,
        group_name=group_names.get(row.config_group_id, "-") if row.config_group_id else "-",
        config_version=row.config_version,
        config_fingerprint=row.config_fingerprint or "",
        detail=row.detail or "",
    )
