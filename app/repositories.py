from __future__ import annotations

from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models import (
    AdminActionLog,
    ConfigDeliveryLog,
    ConfigGroup,
    DeployLog,
    HealthCheckLog,
    ManagedUser,
    Node,
    Profile,
    Settings,
)


class NodeRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_dashboard(self) -> List[Node]:
        return self._db.query(Node).order_by(Node.active.desc(), Node.created_at.desc()).all()

    def list_by_tag(self) -> List[Node]:
        return self._db.query(Node).order_by(Node.tag).all()

    def list_all(self) -> List[Node]:
        return self._db.query(Node).all()

    def list_by_tags(self, tags: Iterable[str]) -> List[Node]:
        return self._db.query(Node).filter(Node.tag.in_(list(tags))).order_by(Node.tag).all()

    def get_active(self) -> Optional[Node]:
        return self._db.query(Node).filter(Node.active.is_(True)).first()

    def get_by_id(self, node_id: int) -> Optional[Node]:
        return self._db.query(Node).filter(Node.id == node_id).first()

    def get_by_tag(self, tag: str) -> Optional[Node]:
        return self._db.query(Node).filter(Node.tag == tag).first()

    def find_by_id_or_tag(self, value: str) -> Optional[Node]:
        node = self.get_by_id(int(value)) if value.isdigit() else None
        return node or self.get_by_tag(value)

    def deactivate_all(self) -> None:
        self._db.query(Node).update({"active": False})


class ProfileRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_all(self) -> List[Profile]:
        return self._db.query(Profile).order_by(Profile.created_at).all()

    def get_active(self) -> Optional[Profile]:
        return self._db.query(Profile).filter(Profile.active.is_(True)).first()

    def get_by_id(self, profile_id: int) -> Optional[Profile]:
        return self._db.query(Profile).filter(Profile.id == profile_id).first()

    def get_by_name(self, name: str) -> Optional[Profile]:
        return self._db.query(Profile).filter(Profile.name == name).first()

    def deactivate_all(self) -> None:
        self._db.query(Profile).update({"active": False})


class SettingsRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, key: str) -> Optional[Settings]:
        return self._db.query(Settings).filter(Settings.key == key).first()


class DeployLogRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def latest_by_node_tag(self) -> dict[str, DeployLog]:
        latest: dict[str, DeployLog] = {}
        rows = self._db.query(DeployLog).order_by(DeployLog.started_at.desc(), DeployLog.id.desc()).all()
        for row in rows:
            if row.node_tag and row.node_tag not in latest:
                latest[row.node_tag] = row
        return latest


class HealthLogRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def recent_connectivity(self, cutoff) -> List[HealthCheckLog]:
        return (
            self._db.query(HealthCheckLog)
            .filter(
                HealthCheckLog.checked_at >= cutoff,
                HealthCheckLog.category == "connectivity",
            )
            .order_by(HealthCheckLog.checked_at)
            .all()
        )


class UserRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_groups(self) -> List[ConfigGroup]:
        return self._db.query(ConfigGroup).order_by(ConfigGroup.enabled.desc(), ConfigGroup.name).all()

    def list_users(self) -> List[ManagedUser]:
        return self._db.query(ManagedUser).order_by(ManagedUser.enabled.desc(), ManagedUser.created_at.desc()).all()

    def get_group(self, group_id: int) -> Optional[ConfigGroup]:
        return self._db.query(ConfigGroup).filter(ConfigGroup.id == group_id).first()

    def get_group_by_name(self, name: str) -> Optional[ConfigGroup]:
        return self._db.query(ConfigGroup).filter(ConfigGroup.name == name).first()

    def get_group_name_duplicate(self, name: str, exclude_id: int) -> Optional[ConfigGroup]:
        return self._db.query(ConfigGroup).filter(ConfigGroup.name == name, ConfigGroup.id != exclude_id).first()

    def get_user(self, user_id: int) -> Optional[ManagedUser]:
        return self._db.query(ManagedUser).filter(ManagedUser.id == user_id).first()

    def get_user_by_telegram_id(self, telegram_id: str) -> Optional[ManagedUser]:
        return self._db.query(ManagedUser).filter(ManagedUser.telegram_id == telegram_id).first()

    def get_user_telegram_duplicate(self, telegram_id: str, exclude_id: int) -> Optional[ManagedUser]:
        return self._db.query(ManagedUser).filter(
            ManagedUser.telegram_id == telegram_id,
            ManagedUser.id != exclude_id,
        ).first()

    def clear_group_assignments(self, group_id: int) -> None:
        self._db.query(ManagedUser).filter(ManagedUser.config_group_id == group_id).update({"config_group_id": None})


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add_admin_action(self, actor: str, channel: str, action: str, success: bool, detail: str = "") -> None:
        self._db.add(AdminActionLog(
            actor=actor,
            channel=channel,
            action=action,
            success=success,
            detail=detail or None,
        ))

    def add_delivery(
        self,
        telegram_id: str,
        action: str,
        success: bool,
        managed_user_id: Optional[int] = None,
        config_group_id: Optional[int] = None,
        detail: str = "",
    ) -> None:
        self._db.add(ConfigDeliveryLog(
            managed_user_id=managed_user_id,
            telegram_id=telegram_id,
            config_group_id=config_group_id,
            action=action,
            success=success,
            detail=detail or None,
        ))
