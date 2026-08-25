from __future__ import annotations

import json

import pytest

from app.db import SessionLocal
from app.models import Node
from app.services.nodes import (
    NodeMetadataInput,
    export_nodes_payload,
    normalize_topology_role,
    update_node_metadata,
)


def test_normalize_topology_role_accepts_known_values_and_blank():
    assert normalize_topology_role("") is None
    assert normalize_topology_role(None) is None
    assert normalize_topology_role("entry_relay") == "entry_relay"
    assert normalize_topology_role("upstream_exit") == "upstream_exit"


def test_normalize_topology_role_rejects_unknown_values():
    with pytest.raises(ValueError, match="Invalid topology role"):
        normalize_topology_role("panel")


def _insert_node(tag: str = "role-node") -> int:
    db = SessionLocal()
    try:
        node = Node(
            tag=tag,
            protocol="vless",
            raw_url=f"vless://{tag}",
            parsed_json="{}",
            schema_version=1,
        )
        db.add(node)
        db.commit()
        db.refresh(node)
        return node.id
    finally:
        db.close()


def test_update_node_metadata_stores_and_clears_topology_role():
    node_id = _insert_node("role-save")
    db = SessionLocal()
    try:
        result = update_node_metadata(db, node_id, NodeMetadataInput(topology_role="entry_relay"))
        assert result.ok
        node = db.query(Node).filter(Node.id == node_id).one()
        assert node.topology_role == "entry_relay"

        result = update_node_metadata(db, node_id, NodeMetadataInput(topology_role=""))
        assert result.ok
        node = db.query(Node).filter(Node.id == node_id).one()
        assert node.topology_role is None
    finally:
        db.query(Node).filter(Node.id == node_id).delete()
        db.commit()
        db.close()


def test_update_node_metadata_rejects_unknown_topology_role():
    node_id = _insert_node("role-bad")
    db = SessionLocal()
    try:
        result = update_node_metadata(db, node_id, NodeMetadataInput(topology_role="panel"))
        assert not result.ok
        assert result.message == "Invalid topology role"
        node = db.query(Node).filter(Node.id == node_id).one()
        assert node.topology_role is None
        assert "vless://" not in result.message
    finally:
        db.query(Node).filter(Node.id == node_id).delete()
        db.commit()
        db.close()


def test_export_nodes_payload_includes_topology_role():
    node_id = _insert_node("role-export")
    db = SessionLocal()
    try:
        update_node_metadata(db, node_id, NodeMetadataInput(topology_role="upstream_exit"))
        payload = json.loads(export_nodes_payload(db))
        exported = next(item for item in payload if item["tag"] == "role-export")
        assert exported["topology_role"] == "upstream_exit"
    finally:
        db.query(Node).filter(Node.id == node_id).delete()
        db.commit()
        db.close()
