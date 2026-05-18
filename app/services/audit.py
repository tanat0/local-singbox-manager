from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AdminActionLog


def log_admin_action(
    db: Session,
    actor: str,
    channel: str,
    action: str,
    success: bool,
    detail: str = "",
) -> None:
    db.add(AdminActionLog(
        actor=actor,
        channel=channel,
        action=action,
        success=success,
        detail=detail or None,
    ))
    db.commit()
