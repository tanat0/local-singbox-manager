import json

from app.models import Node
from app.services.client_configs import build_client_config_document
from app.services.distribution import UserAssignment


def _node(tag: str) -> Node:
    return Node(
        tag=tag,
        protocol="vless",
        raw_url=f"vless://12345678-abcd-0000-0000-000000000001@1.2.3.4:443?type=tcp#{tag}",
        parsed_json=json.dumps({
            "protocol": "vless",
            "raw_url": f"vless://12345678-abcd-0000-0000-000000000001@1.2.3.4:443?type=tcp#{tag}",
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
