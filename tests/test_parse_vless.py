import pytest

from app.parsers.vless import VlessNode, parse_vless
from app.singbox.generator import build_outbound

REALITY_URL = (
    "vless://12345678-abcd-1234-efgh-000000000001"
    "@78.40.108.81:8443"
    "?security=reality&sni=www.bing.com&pbk=abcPublicKey&sid=aabbcc&fp=chrome&type=tcp"
    "#mynode"
)


def test_returns_vless_node():
    assert isinstance(parse_vless(REALITY_URL), VlessNode)


def test_parse_uuid():
    assert parse_vless(REALITY_URL).uuid == "12345678-abcd-1234-efgh-000000000001"


def test_parse_server_port():
    n = parse_vless(REALITY_URL)
    assert n.server == "78.40.108.81"
    assert n.port == 8443


def test_parse_tag():
    assert parse_vless(REALITY_URL).tag == "mynode"


def test_parse_reality_params():
    n = parse_vless(REALITY_URL)
    assert n.security == "reality"
    assert n.sni == "www.bing.com"
    assert n.pbk == "abcPublicKey"
    assert n.sid == "aabbcc"
    assert n.fp == "chrome"


def test_no_flow_by_default():
    assert parse_vless(REALITY_URL).flow is None


def test_flow_present_when_in_url():
    url = "vless://uuid@1.2.3.4:443?security=reality&pbk=x&flow=xtls-rprx-vision#t"
    assert parse_vless(url).flow == "xtls-rprx-vision"


def test_outbound_no_flow_field():
    url = "vless://uuid@1.2.3.4:443?security=reality&pbk=pk&sid=sid#t"
    out = build_outbound(parse_vless(url))
    assert "flow" not in out


def test_outbound_has_flow_field():
    url = "vless://uuid@1.2.3.4:443?security=reality&pbk=pk&flow=xtls-rprx-vision#t"
    out = build_outbound(parse_vless(url))
    assert out.get("flow") == "xtls-rprx-vision"


def test_outbound_reality_structure():
    out = build_outbound(parse_vless(REALITY_URL))
    tls = out["tls"]
    assert tls["enabled"] is True
    assert tls["reality"]["enabled"] is True
    assert tls["reality"]["public_key"] == "abcPublicKey"
    assert tls["reality"]["short_id"] == "aabbcc"
    assert tls["utls"]["fingerprint"] == "chrome"


def test_outbound_insecure_false_by_default():
    out = build_outbound(parse_vless(REALITY_URL))
    assert out["tls"]["insecure"] is False


def test_outbound_allow_insecure():
    url = "vless://uuid@1.2.3.4:443?security=reality&pbk=pk&allowInsecure=1#t"
    out = build_outbound(parse_vless(url))
    assert out["tls"]["insecure"] is True


def test_outbound_basic_fields():
    out = build_outbound(parse_vless(REALITY_URL))
    assert out["type"] == "vless"
    assert out["server"] == "78.40.108.81"
    assert out["server_port"] == 8443
    assert "network" not in out


def test_parse_transport_aliases():
    assert parse_vless("vless://uuid@1.2.3.4:443?type=h2#t").transport_type == "http"
    assert parse_vless("vless://uuid@1.2.3.4:443?type=http2#t").transport_type == "http"
    assert parse_vless("vless://uuid@1.2.3.4:443?type=websocket#t").transport_type == "ws"


def test_parse_transport_fields():
    node = parse_vless("vless://uuid@1.2.3.4:443?type=grpc&serviceName=tun&host=edge.example&path=/v#t")
    assert node.transport_type == "grpc"
    assert node.service_name == "tun"
    assert node.host == "edge.example"
    assert node.path == "/v"


def test_tag_url_decoded():
    url = "vless://uuid@1.2.3.4:443?security=reality&pbk=pk#My%20Node"
    assert parse_vless(url).tag == "My Node"


def test_default_tag_without_fragment():
    url = "vless://uuid@1.2.3.4:443?security=reality&pbk=pk"
    assert "1.2.3.4" in parse_vless(url).tag


def test_wrong_scheme_raises():
    with pytest.raises(ValueError, match="vless"):
        parse_vless("hysteria2://pass@1.2.3.4:443")


def test_extra_params_captured():
    url = "vless://uuid@1.2.3.4:443?security=reality&pbk=pk&unknownParam=xyz#t"
    n = parse_vless(url)
    assert "unknownParam" in n.extra_params


def test_roundtrip_serialization():
    n = parse_vless(REALITY_URL)
    d = n.to_dict()
    n2 = VlessNode.model_validate(d)
    assert n2.uuid == n.uuid
    assert n2.pbk == n.pbk
    assert n2.protocol == "vless"
