from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.db import Base, SessionLocal, engine
from app.models import ConfigDeliveryLog
from app.services.distribution import (
    UserAssignment,
    config_fingerprint,
    effective_refresh_limit,
    refresh_limit_exceeded,
)
from app.telegram.presenters import format_user_configs, format_user_status


def test_format_user_status_shows_assignment():
    assignment = UserAssignment(
        user=SimpleNamespace(telegram_id="123", display_name="Alex"),
        group=SimpleNamespace(name="family"),
        nodes=[SimpleNamespace(), SimpleNamespace()],
        config_version=3,
        config_fingerprint="abcdef1234567890",
    )

    text = format_user_status(assignment)

    assert "Alex" in text
    assert "family" in text
    assert "2" in text
    assert "3" in text
    assert "abcdef123456" in text


def test_format_user_configs_includes_raw_urls():
    assignment = UserAssignment(
        user=SimpleNamespace(telegram_id="123", display_name="Alex"),
        group=SimpleNamespace(name="family"),
        nodes=[
            SimpleNamespace(tag="node-a", protocol="vless", raw_url="vless://node-a"),
            SimpleNamespace(tag="node-b", protocol="hysteria2", raw_url="hysteria2://node-b"),
        ],
        config_version=2,
        config_fingerprint="b" * 64,
    )

    text = format_user_configs(assignment)

    assert "Config group: family" in text
    assert "Version: 2" in text
    assert "bbbbbbbbbbbb" in text
    assert "vless://node-a" in text
    assert "hysteria2://node-b" in text


def test_format_user_configs_returns_error():
    assignment = UserAssignment(user=None, group=None, nodes=[], error="No config group assigned.")

    assert format_user_configs(assignment) == "No config group assigned."


def test_config_fingerprint_is_stable_and_content_based():
    nodes_a = [
        SimpleNamespace(tag="b", protocol="vless", raw_url="vless://b"),
        SimpleNamespace(tag="a", protocol="hysteria2", raw_url="hysteria2://a"),
    ]
    nodes_b = list(reversed(nodes_a))
    nodes_changed = [
        SimpleNamespace(tag="a", protocol="hysteria2", raw_url="hysteria2://changed"),
        SimpleNamespace(tag="b", protocol="vless", raw_url="vless://b"),
    ]

    assert config_fingerprint(nodes_a) == config_fingerprint(nodes_b)
    assert config_fingerprint(nodes_a) != config_fingerprint(nodes_changed)


def test_effective_refresh_limit_prefers_user_then_group_then_default():
    assert effective_refresh_limit(
        SimpleNamespace(refresh_limit_per_hour=2),
        SimpleNamespace(refresh_limit_per_hour=5),
    ) == 2
    assert effective_refresh_limit(
        SimpleNamespace(refresh_limit_per_hour=None),
        SimpleNamespace(refresh_limit_per_hour=5),
    ) == 5
    assert effective_refresh_limit(
        SimpleNamespace(refresh_limit_per_hour=None),
        SimpleNamespace(refresh_limit_per_hour=None),
    ) == 10


def test_refresh_limit_counts_recent_config_and_refresh_attempts():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(ConfigDeliveryLog).delete()
        now = datetime.utcnow()
        assignment = UserAssignment(
            user=SimpleNamespace(telegram_id="123", id=1),
            group=SimpleNamespace(id=1),
            nodes=[],
            refresh_limit_per_hour=2,
        )
        db.add(ConfigDeliveryLog(
            telegram_id="123",
            action="/config",
            success=True,
            created_at=now - timedelta(minutes=10),
        ))
        db.add(ConfigDeliveryLog(
            telegram_id="123",
            action="/refresh",
            success=False,
            created_at=now - timedelta(minutes=5),
        ))
        db.add(ConfigDeliveryLog(
            telegram_id="123",
            action="notify_config_changed",
            success=False,
            created_at=now - timedelta(minutes=1),
        ))
        db.commit()

        assert refresh_limit_exceeded(db, assignment, now=now)
    finally:
        db.query(ConfigDeliveryLog).delete()
        db.commit()
        db.close()
