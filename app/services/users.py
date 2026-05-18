from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models import ConfigGroup, ManagedUser
from app.repositories import UserRepository


@dataclass(frozen=True)
class MutationResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class ConfigGroupInput:
    name: str
    description: str = ""
    node_tags: str = ""
    notes: str = ""
    enabled: bool = False


@dataclass(frozen=True)
class ManagedUserInput:
    telegram_id: str
    display_name: str = ""
    config_group_id: str = ""
    notes: str = ""
    enabled: bool = False


@dataclass(frozen=True)
class UsersPageData:
    groups: List[ConfigGroup]
    users: List[ManagedUser]


def parse_node_tags(raw: str) -> List[str]:
    tags: List[str] = []
    seen = set()
    for part in raw.replace("\n", ",").split(","):
        tag = part.strip()
        if tag and tag not in seen:
            tags.append(tag)
            seen.add(tag)
    return tags


def encode_node_tags(tags: Iterable[str]) -> str:
    return json.dumps(list(tags), ensure_ascii=False)


def decode_node_tags(raw: str) -> List[str]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [str(item) for item in data if str(item).strip()]
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return []


def users_page_data(db: Session) -> UsersPageData:
    repo = UserRepository(db)
    return UsersPageData(groups=repo.list_groups(), users=repo.list_users())


def create_group(db: Session, form: ConfigGroupInput) -> MutationResult:
    repo = UserRepository(db)
    name = form.name.strip()
    if not name:
        return MutationResult(False, "Group name is required")
    if repo.get_group_by_name(name):
        return MutationResult(False, f"Group '{name}' already exists")

    db.add(ConfigGroup(
        name=name,
        description=form.description.strip() or None,
        node_tags_json=encode_node_tags(parse_node_tags(form.node_tags)),
        notes=form.notes.strip() or None,
        enabled=form.enabled,
    ))
    db.commit()
    return MutationResult(True, f"Created group '{name}'")


def update_group(db: Session, group_id: int, form: ConfigGroupInput) -> MutationResult:
    repo = UserRepository(db)
    group = repo.get_group(group_id)
    if not group:
        return MutationResult(False, "Group not found")

    name = form.name.strip()
    if not name:
        return MutationResult(False, "Group name is required")
    if repo.get_group_name_duplicate(name, exclude_id=group_id):
        return MutationResult(False, f"Group '{name}' already exists")

    group.name = name
    group.description = form.description.strip() or None
    group.node_tags_json = encode_node_tags(parse_node_tags(form.node_tags))
    group.notes = form.notes.strip() or None
    group.enabled = form.enabled
    db.commit()
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

    db.add(ManagedUser(
        telegram_id=telegram_id,
        display_name=form.display_name.strip() or None,
        config_group_id=_parse_group_id(form.config_group_id),
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

    user.telegram_id = telegram_id
    user.display_name = form.display_name.strip() or None
    user.config_group_id = _parse_group_id(form.config_group_id)
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
