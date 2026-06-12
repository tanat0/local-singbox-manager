import pytest

from app.parsers.hysteria2 import Hysteria2Node, parse_hysteria2
from app.parsers.vless import VlessNode, parse_vless
from app.singbox.generator import build_outbound, generate_config

VLESS_URL = (
    "vless://some-uuid@1.2.3.4:443"
    "?security=reality&sni=example.com&pbk=pubkey&sid=shortid&fp=chrome&type=tcp"
    "#test-node"
)
HY2_URL = "hysteria2://secret@5.5.5.5:8443?sni=hy2.example.com#hy2-node"


# ---- outbound builders ----

def test_vless_outbound_type():
    out = build_outbound(parse_vless(VLESS_URL))
    assert out["type"] == "vless"


def test_hy2_outbound_type():
    out = build_outbound(parse_hysteria2(HY2_URL))
    assert out["type"] == "hysteria2"


def test_vless_reality_structure():
    out = build_outbound(parse_vless(VLESS_URL))
    assert out["tls"]["reality"]["enabled"] is True
    assert out["tls"]["reality"]["public_key"] == "pubkey"


# ---- full config generation ----

def test_config_required_top_keys():
    cfg = generate_config(parse_vless(VLESS_URL))
    for key in ("log", "dns", "inbounds", "route", "outbounds"):
        assert key in cfg


def test_active_outbound_is_first():
    node = parse_vless(VLESS_URL)
    cfg = generate_config(node)
    assert cfg["outbounds"][0]["tag"] == node.tag


def test_route_final_matches_tag():
    node = parse_vless(VLESS_URL)
    cfg = generate_config(node)
    assert cfg["route"]["final"] == node.tag


def test_has_direct_and_block():
    cfg = generate_config(parse_vless(VLESS_URL))
    tags = {o["tag"] for o in cfg["outbounds"]}
    assert "direct" in tags
    assert "block" in tags


def test_three_outbounds():
    assert len(generate_config(parse_vless(VLESS_URL))["outbounds"]) == 3


def test_dns_new_format():
    cfg = generate_config(parse_vless(VLESS_URL))
    server = cfg["dns"]["servers"][0]
    assert "type" in server and "server" in server and "tag" in server
    assert "address" not in server   # must NOT use deprecated format


def test_tun_inbound():
    cfg = generate_config(parse_vless(VLESS_URL))
    tun = next((i for i in cfg["inbounds"] if i["type"] == "tun"), None)
    assert tun is not None
    assert tun["auto_route"] is True
    assert tun["stack"] == "gvisor"
    assert {i["type"] for i in cfg["inbounds"]} == {"tun"}


def test_dns_hijack_rule():
    cfg = generate_config(parse_vless(VLESS_URL))
    assert cfg["route"]["rules"][0] == {"port": 53, "action": "hijack-dns"}


def test_route_guards_block_telemetry_domains():
    cfg = generate_config(parse_vless(VLESS_URL))
    rule = next(
        (
            r for r in cfg["route"]["rules"]
            if r.get("outbound") == "block" and "api.oneme.ru" in r.get("domain", [])
        ),
        None,
    )
    assert rule is not None
    assert "calls.okcdn.ru" in rule["domain"]


def test_route_guards_block_ip_checker_domains():
    cfg = generate_config(parse_vless(VLESS_URL))
    rule = next(
        (
            r for r in cfg["route"]["rules"]
            if r.get("outbound") == "block" and "api.ipify.org" in r.get("domain", [])
        ),
        None,
    )
    assert rule is not None
    assert "ifconfig.me" in rule["domain"]
    assert "checkip.amazonaws.com" in rule["domain"]
    assert "icanhazip.com" in rule["domain"]
    assert "wtfismyip.com" in rule["domain"]


def test_route_guards_direct_ru_domains():
    cfg = generate_config(parse_vless(VLESS_URL))
    rule = next(
        (
            r for r in cfg["route"]["rules"]
            if r.get("outbound") == "direct" and "gosuslugi.ru" in r.get("domain", [])
        ),
        None,
    )
    assert rule is not None
    assert rule["domain_suffix"] == [".ru", ".su"]


def test_route_guards_precede_preset_specific_rules():
    cfg = generate_config(parse_vless(VLESS_URL), route_preset="bypass_lan")
    rules = cfg["route"]["rules"]
    ru_guard_index = next(
        i for i, rule in enumerate(rules)
        if "gosuslugi.ru" in rule.get("domain", [])
    )
    private_rule_index = next(
        i for i, rule in enumerate(rules)
        if rule.get("ip_is_private")
    )
    assert ru_guard_index < private_rule_index


def test_base_not_mutated():
    n1 = parse_vless(VLESS_URL)
    n2 = parse_hysteria2(HY2_URL)
    c1 = generate_config(n1)
    c2 = generate_config(n2)
    assert c1["route"]["final"] == "test-node"
    assert c2["route"]["final"] == "hy2-node"


def test_log_timestamp():
    assert generate_config(parse_vless(VLESS_URL))["log"]["timestamp"] is True


def test_log_level_defaults_to_warn():
    assert generate_config(parse_vless(VLESS_URL))["log"]["level"] == "warn"


def test_log_level_can_be_info():
    assert generate_config(parse_vless(VLESS_URL), log_level="info")["log"]["level"] == "info"


def test_invalid_log_level_raises():
    with pytest.raises(ValueError, match="log level"):
        generate_config(parse_vless(VLESS_URL), log_level="verbose")


def test_bypass_lan_preset_has_private_ip_rule():
    cfg = generate_config(parse_vless(VLESS_URL), route_preset="bypass_lan")
    rules = cfg["route"]["rules"]
    private_rule = next((r for r in rules if r.get("ip_is_private")), None)
    assert private_rule is not None
    assert private_rule["outbound"] == "direct"


def test_bypass_ru_preset_has_rule_set():
    cfg = generate_config(parse_vless(VLESS_URL), route_preset="bypass_ru")
    assert "rule_set" in cfg["route"]
    tags = {rs["tag"] for rs in cfg["route"]["rule_set"]}
    assert "geoip-ru" in tags
    assert "geosite-ru" in tags


def test_bypass_ru_rule_set_remote_binary():
    cfg = generate_config(parse_vless(VLESS_URL), route_preset="bypass_ru")
    for rs in cfg["route"]["rule_set"]:
        assert rs["type"] == "remote"
        assert rs["format"] == "binary"
        assert rs["url"].endswith(".srs")


def test_bypass_ru_has_ruleset_direct_rule():
    cfg = generate_config(parse_vless(VLESS_URL), route_preset="bypass_ru")
    ruleset_rule = next(
        (r for r in cfg["route"]["rules"] if "rule_set" in r), None
    )
    assert ruleset_rule is not None
    assert ruleset_rule["outbound"] == "direct"
    assert set(ruleset_rule["rule_set"]) == {"geoip-ru", "geosite-ru"}


def test_bypass_ru_has_lan_bypass():
    cfg = generate_config(parse_vless(VLESS_URL), route_preset="bypass_ru")
    rules = cfg["route"]["rules"]
    private_rule = next((r for r in rules if r.get("ip_is_private")), None)
    assert private_rule is not None
    assert private_rule["outbound"] == "direct"


def test_bypass_ru_download_detour_is_direct():
    cfg = generate_config(parse_vless(VLESS_URL), route_preset="bypass_ru")
    for rs in cfg["route"]["rule_set"]:
        assert rs["download_detour"] == "direct"


def test_invalid_dns_preset_raises():
    with pytest.raises(ValueError, match="DNS"):
        generate_config(parse_vless(VLESS_URL), dns_preset="nonexistent")


def test_invalid_route_preset_raises():
    with pytest.raises(ValueError, match="route"):
        generate_config(parse_vless(VLESS_URL), route_preset="nonexistent")


def test_parse_url_registry():
    from app.parsers import parse_url
    n = parse_url(VLESS_URL)
    assert isinstance(n, VlessNode)
    n2 = parse_url(HY2_URL)
    assert isinstance(n2, Hysteria2Node)
