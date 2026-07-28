import json
from types import SimpleNamespace
from typing import Dict

from app.services.nodes import deserialize_node
from app.singbox.generator import build_outbound


def _stored_node(raw_url: str, parsed_payload: Dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        tag=parsed_payload["tag"],
        raw_url=raw_url,
        parsed_json=json.dumps(parsed_payload),
    )


def test_deserialize_legacy_hysteria2_decodes_percent_encoded_auth():
    encoded_auth = "pa%24%40%5E%25ss"
    raw_url = (
        f"hysteria2://{encoded_auth}@1.2.3.4:443"
        "?obfs=salamander&obfs-password=pa%40ss#hy2-legacy"
    )
    node = _stored_node(
        raw_url,
        {
            "protocol": "hysteria2",
            "raw_url": raw_url,
            "tag": "hy2-legacy",
            "server": "1.2.3.4",
            "port": 443,
            "schema_version": 1,
            "extra_params": {},
            "auth": encoded_auth,
            "obfs_type": "salamander",
            "obfs_password": "pa%40ss",
        },
    )

    outbound = build_outbound(deserialize_node(node))

    assert outbound["password"] == "pa$@^%ss"
    assert outbound["obfs"]["password"] == "pa@ss"


def test_deserialize_hysteria2_does_not_double_decode_current_payload():
    raw_url = "hysteria2://%2524literal@1.2.3.4:443#hy2-current"
    node = _stored_node(
        raw_url,
        {
            "protocol": "hysteria2",
            "raw_url": raw_url,
            "tag": "hy2-current",
            "server": "1.2.3.4",
            "port": 443,
            "schema_version": 1,
            "extra_params": {},
            "auth": "%24literal",
        },
    )

    parsed = deserialize_node(node)

    assert parsed.auth == "%24literal"


def test_deserialize_legacy_vless_reparses_transport_from_raw_url():
    raw_url = "vless://uuid@1.2.3.4:443?type=grpc&serviceName=tun#vless-legacy"
    node = _stored_node(
        raw_url,
        {
            "protocol": "vless",
            "raw_url": raw_url,
            "tag": "vless-legacy",
            "server": "1.2.3.4",
            "port": 443,
            "schema_version": 1,
            "extra_params": {},
            "uuid": "uuid",
            "network": "grpc",
            "security": "none",
        },
    )

    outbound = build_outbound(deserialize_node(node))

    assert "network" not in outbound
    assert outbound["transport"] == {"type": "grpc", "service_name": "tun"}
