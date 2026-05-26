from __future__ import annotations

import asyncio
import json

from app.db import Base, SessionLocal, engine
from app.models import ConfigDeliveryLog, ConfigGroup, ManagedUser, Node
from app.services.node_tags import decode_node_tags, encode_node_tags, parse_node_tags
from app.services.users import ConfigGroupInput, create_group, update_group


def test_parse_node_tags_deduplicates_and_strips():
    assert parse_node_tags(" alpha, beta\nalpha ,, gamma ") == ["alpha", "beta", "gamma"]


def test_encode_decode_node_tags_roundtrip():
    raw = encode_node_tags(["node-a", "node-b"])
    assert decode_node_tags(raw) == ["node-a", "node-b"]


def test_decode_node_tags_handles_bad_json():
    assert decode_node_tags("not json") == []


def _reset_user_tables(db):
    db.query(ConfigDeliveryLog).delete()
    db.query(ManagedUser).delete()
    db.query(ConfigGroup).delete()
    db.query(Node).delete()
    db.commit()


def _add_node(db, tag: str, raw_url: str = ""):
    db.add(Node(
        tag=tag,
        protocol="vless",
        raw_url=raw_url or f"vless://{tag}",
        parsed_json=json.dumps({
            "protocol": "vless",
            "tag": tag,
            "raw_url": raw_url or f"vless://{tag}",
            "server": "1.2.3.4",
            "port": 443,
            "uuid": "12345678-abcd-0000-0000-000000000001",
            "security": "none",
        }),
        schema_version=1,
        active=False,
    ))


def test_create_group_rejects_unknown_node_tag():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _reset_user_tables(db)
        result = create_group(db, ConfigGroupInput(name="family", node_tags=["missing-node"]))

        assert result.ok is False
        assert "Unknown node tag" in result.message
        assert db.query(ConfigGroup).count() == 0
    finally:
        _reset_user_tables(db)
        db.close()


def test_update_group_increments_version_and_logs_notification_failure():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _reset_user_tables(db)
        _add_node(db, "node-a")
        _add_node(db, "node-b")
        group = ConfigGroup(name="family", enabled=True, node_tags_json=encode_node_tags(["node-a"]))
        db.add(group)
        db.flush()
        db.add(ManagedUser(telegram_id="123", enabled=True, config_group_id=group.id))
        db.commit()

        result = asyncio.run(update_group(
            db,
            group.id,
            ConfigGroupInput(name="family", node_tags=["node-b"], enabled=True),
        ))

        db.refresh(group)
        log = db.query(ConfigDeliveryLog).filter(ConfigDeliveryLog.action == "notify_config_changed").first()
        assert result.ok is True
        assert group.config_version == 2
        assert decode_node_tags(group.node_tags_json) == ["node-b"]
        assert log is not None
        assert log.success is False
        assert log.config_version == 2
        assert log.config_fingerprint
    finally:
        _reset_user_tables(db)
        db.close()
