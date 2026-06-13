import pytest

from app.parsers.hysteria2 import parse_hysteria2
from app.parsers.vless import parse_vless
from app.singbox.client_generator import generate_client_config

VLESS_A = (
    "vless://12345678-abcd-0000-0000-000000000001@1.2.3.4:443"
    "?security=reality&sni=example.com&pbk=pubkey&sid=shortid&fp=chrome&type=tcp"
    "#node-a"
)
VLESS_B = (
    "vless://12345678-abcd-0000-0000-000000000002@1.2.3.5:443"
    "?security=reality&sni=example.org&pbk=pubkey&sid=shortid&fp=chrome&type=tcp"
    "#node-b"
)
HY2 = "hysteria2://secret@5.5.5.5:8443?sni=hy2.example.com#hy2-node"


def test_client_config_single_node_uses_node_as_final_outbound():
    cfg = generate_client_config([parse_vless(VLESS_A)])

    assert cfg["route"]["final"] == "node-a"
    assert {inbound["type"] for inbound in cfg["inbounds"]} == {"tun"}
    assert {outbound["tag"] for outbound in cfg["outbounds"]} == {"node-a", "direct", "block"}


def test_client_config_includes_route_guards():
    cfg = generate_client_config([parse_vless(VLESS_A)])
    rules = cfg["route"]["rules"]

    assert rules[0] == {"port": 53, "action": "hijack-dns"}
    assert any("api.ipify.org" in rule.get("domain", []) and rule["outbound"] == "block" for rule in rules)
    assert any("gosuslugi.ru" in rule.get("domain", []) and rule["outbound"] == "direct" for rule in rules)


def test_client_config_multi_node_uses_selector():
    cfg = generate_client_config([parse_vless(VLESS_B), parse_hysteria2(HY2), parse_vless(VLESS_A)])
    selector = next(outbound for outbound in cfg["outbounds"] if outbound["type"] == "selector")

    assert cfg["route"]["final"] == "proxy"
    assert selector["tag"] == "proxy"
    assert selector["outbounds"] == ["hy2-node", "node-a", "node-b"]
    assert selector["default"] == "hy2-node"


def test_client_config_rejects_reserved_tags():
    reserved = parse_vless(VLESS_A.replace("#node-a", "#direct"))

    with pytest.raises(ValueError, match="Reserved node tag"):
        generate_client_config([reserved])


def test_client_config_rejects_duplicate_tags():
    node_a = parse_vless(VLESS_A)
    node_b = parse_vless(VLESS_B.replace("#node-b", "#node-a"))

    with pytest.raises(ValueError, match="Duplicate node tag"):
        generate_client_config([node_a, node_b])
