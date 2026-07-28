import json
from typing import Optional

import pytest

from app.models import Node
from app.services.client_configs import build_client_config_document, build_sbclient_bundle_document
from app.services.distribution import UserAssignment


def _node(tag: str, raw_url: Optional[str] = None) -> Node:
    raw_url = raw_url or f"vless://12345678-abcd-0000-0000-000000000001@1.2.3.4:443?type=tcp#{tag}"
    return Node(
        tag=tag,
        protocol="vless",
        raw_url=raw_url,
        parsed_json=json.dumps({
            "protocol": "vless",
            "raw_url": raw_url,
            "tag": tag,
            "server": "1.2.3.4",
            "port": 443,
            "uuid": "12345678-abcd-0000-0000-000000000001",
            "network": "tcp",
            "security": "none",
        }),
        schema_version=1,
    )


def test_build_client_config_document():
    assignment = UserAssignment(
        user=None,
        group=type("Group", (), {"name": "Family Devices"})(),
        nodes=[_node("node-a")],
        config_version=7,
        config_fingerprint="a" * 64,
        route_preset="bypass_lan",
    )

    document = build_client_config_document(assignment)
    payload = json.loads(document.content.decode("utf-8"))

    assert document.filename == "singbox-family-devices-v7.json"
    assert document.mime_type == "application/json"
    assert "Family Devices" in document.caption
    assert payload["route"]["final"] == "node-a"
    assert any(rule.get("ip_is_private") for rule in payload["route"]["rules"])


def test_build_sbclient_bundle_document():
    assignment = UserAssignment(
        user=None,
        group=type("Group", (), {"name": "Family Devices"})(),
        nodes=[_node("node-b"), _node("node-a")],
        config_version=7,
        config_fingerprint="b" * 64,
        route_preset="bypass_ru",
    )

    document = build_sbclient_bundle_document(assignment)
    payload = json.loads(document.content.decode("utf-8"))

    assert document.filename == "singbox-client-family-devices-v7.sbclient"
    assert document.mime_type == "application/json"
    assert "Family Devices" in document.caption
    assert payload["schema_version"] == 1
    assert payload["default_profile"] == "node-a"
    assert [profile["name"] for profile in payload["profiles"]] == ["node-a", "node-b"]
    assert payload["profiles"][0]["dns_preset"] == "quad9_tls"
    assert payload["profiles"][0]["route_preset"] == "bypass_ru"
    assert payload["profiles"][0]["raw_url"].startswith("vless://")


def test_build_sbclient_bundle_rejects_client_incompatible_profile_name():
    assignment = UserAssignment(
        user=None,
        group=type("Group", (), {"name": "Family Devices"})(),
        nodes=[_node("n" * 81)],
        config_version=7,
        config_fingerprint="b" * 64,
        route_preset="bypass_ru",
    )

    with pytest.raises(ValueError, match="too long"):
        build_sbclient_bundle_document(assignment)


def test_generated_documents_reject_unsupported_transport():
    assignment = UserAssignment(
        user=None,
        group=type("Group", (), {"name": "Family Devices"})(),
        nodes=[_node("xhttp-node", raw_url="vless://uuid@1.2.3.4:443?type=xhttp#xhttp-node")],
        config_version=7,
        config_fingerprint="b" * 64,
        route_preset="bypass_ru",
    )

    with pytest.raises(ValueError, match="XHTTP"):
        build_client_config_document(assignment)
    with pytest.raises(ValueError, match="XHTTP"):
        build_sbclient_bundle_document(assignment)
