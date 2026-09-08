from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.db import Base, SessionLocal, engine
from app.models import ConfigDeliveryLog, ConfigGroup, ManagedUser, Node
from app.services.distribution import (
    UserAssignment,
    config_fingerprint,
    effective_refresh_limit,
    get_group_artifact_assignment,
    get_user_assignment,
    refresh_limit_exceeded,
)
from app.services.node_tags import encode_node_tags
from app.telegram.presenters import format_user_configs, format_user_status


def test_format_user_status_shows_assignment():
    assignment = UserAssignment(
        user=SimpleNamespace(telegram_id="123", display_name="Alex"),
        group=SimpleNamespace(name="family"),
        nodes=[SimpleNamespace(), SimpleNamespace()],
        config_version=3,
        route_preset="bypass_lan",
        config_fingerprint="abcdef1234567890",
    )

    text = format_user_status(assignment)

    assert "Alex" in text
    assert "family" in text
    assert "2" in text
    assert "3" in text
    assert "bypass_lan" in text
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
        route_preset="bypass_ru",
        config_fingerprint="b" * 64,
    )

    text = format_user_configs(assignment)

    assert "Config group: family" in text
    assert "Version: 2" in text
    assert "Route preset: bypass_ru" in text
    assert "Generated sing-box config is attached." in text
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
    assert config_fingerprint(nodes_a, "full_tunnel") != config_fingerprint(nodes_a, "bypass_lan")


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
    assert effective_refresh_limit(None, SimpleNamespace(refresh_limit_per_hour=4)) == 4
    assert effective_refresh_limit(None, SimpleNamespace(refresh_limit_per_hour=None)) == 10


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


def test_get_user_assignment_fails_when_some_assigned_nodes_are_missing():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(ConfigDeliveryLog).delete()
        db.query(ManagedUser).delete()
        db.query(ConfigGroup).delete()
        db.query(Node).delete()
        group = ConfigGroup(
            name="family",
            enabled=True,
            node_tags_json=encode_node_tags(["node-a", "missing-node"]),
        )
        db.add(group)
        db.flush()
        db.add(Node(
            tag="node-a",
            protocol="vless",
            raw_url="vless://node-a",
            parsed_json="{}",
            schema_version=1,
        ))
        db.add(ManagedUser(telegram_id="123", enabled=True, config_group_id=group.id))
        db.commit()

        assignment = get_user_assignment(db, "123")

        assert assignment.error == "Some assigned nodes were not found."
        assert assignment.user is not None
        assert assignment.group is not None
        assert [node.tag for node in assignment.nodes] == ["node-a"]
    finally:
        db.query(ConfigDeliveryLog).delete()
        db.query(ManagedUser).delete()
        db.query(ConfigGroup).delete()
        db.query(Node).delete()
        db.commit()
        db.close()


def _create_group_nodes(db, tags, *, route_preset="bypass_lan", refresh_limit=7, name="family"):
    group = ConfigGroup(
        name=name,
        enabled=True,
        node_tags_json=encode_node_tags(tags),
        route_preset=route_preset,
        refresh_limit_per_hour=refresh_limit,
        config_version=3,
    )
    db.add(group)
    for tag in tags:
        db.add(Node(
            tag=tag,
            protocol="vless",
            raw_url=f"vless://{tag}",
            parsed_json="{}",
            schema_version=1,
        ))
    db.commit()
    db.refresh(group)
    return group


def test_get_group_artifact_assignment_returns_nodes_fingerprint_and_limit():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(ConfigGroup).delete()
        db.query(Node).delete()
        group = _create_group_nodes(db, ["node-b", "node-a"])

        assignment = get_group_artifact_assignment(db, group.id)

        assert assignment.error == ""
        assert assignment.user is None
        assert assignment.group is not None
        assert assignment.group.id == group.id
        assert [node.tag for node in assignment.nodes] == ["node-a", "node-b"]
        assert assignment.route_preset == "bypass_lan"
        assert assignment.config_version == 3
        assert assignment.refresh_limit_per_hour == 7
        assert assignment.config_fingerprint == config_fingerprint(assignment.nodes, "bypass_lan")
    finally:
        db.query(ConfigGroup).delete()
        db.query(Node).delete()
        db.commit()
        db.close()


def test_get_group_artifact_assignment_fails_when_group_is_missing():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        assignment = get_group_artifact_assignment(db, 999999)
        assert assignment.error == "Config group not found."
        assert assignment.group is None
        assert assignment.nodes == []
    finally:
        db.close()


def test_get_group_artifact_assignment_fails_when_group_has_no_nodes():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(ConfigGroup).delete()
        db.query(Node).delete()
        group = ConfigGroup(name="empty", enabled=True, node_tags_json="[]")
        db.add(group)
        db.commit()

        assignment = get_group_artifact_assignment(db, group.id)

        assert assignment.error == "Assigned config group has no nodes."
        assert assignment.group is not None
        assert assignment.nodes == []
    finally:
        db.query(ConfigGroup).delete()
        db.query(Node).delete()
        db.commit()
        db.close()


def test_get_group_artifact_assignment_fails_when_some_assigned_nodes_are_missing():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(ConfigGroup).delete()
        db.query(Node).delete()
        group = ConfigGroup(
            name="partial",
            enabled=True,
            node_tags_json=encode_node_tags(["node-a", "missing-node"]),
        )
        db.add(group)
        db.add(Node(
            tag="node-a",
            protocol="vless",
            raw_url="vless://node-a",
            parsed_json="{}",
            schema_version=1,
        ))
        db.commit()

        assignment = get_group_artifact_assignment(db, group.id)

        assert assignment.error == "Some assigned nodes were not found."
        assert [node.tag for node in assignment.nodes] == ["node-a"]
    finally:
        db.query(ConfigGroup).delete()
        db.query(Node).delete()
        db.commit()
        db.close()


def test_get_group_artifact_assignment_fails_when_route_preset_is_invalid():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(ConfigGroup).delete()
        db.query(Node).delete()
        group = _create_group_nodes(db, ["node-a"], route_preset="missing")

        assignment = get_group_artifact_assignment(db, group.id)

        assert assignment.error == "Assigned config group has an invalid route preset."
        assert assignment.nodes == []
    finally:
        db.query(ConfigGroup).delete()
        db.query(Node).delete()
        db.commit()
        db.close()
