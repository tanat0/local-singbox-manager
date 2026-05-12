import pytest
from app.parsers.hysteria2 import parse_hysteria2, Hysteria2Node
from app.singbox.generator import build_outbound

BASE_URL = "hysteria2://mypassword@1.2.3.4:443?sni=example.com#hy2-test"


def test_returns_hysteria2_node():
    assert isinstance(parse_hysteria2(BASE_URL), Hysteria2Node)


def test_parse_auth():
    assert parse_hysteria2(BASE_URL).auth == "mypassword"


def test_parse_server_port():
    n = parse_hysteria2(BASE_URL)
    assert n.server == "1.2.3.4"
    assert n.port == 443


def test_parse_sni():
    assert parse_hysteria2(BASE_URL).sni == "example.com"


def test_parse_tag():
    assert parse_hysteria2(BASE_URL).tag == "hy2-test"


def test_insecure_false_by_default():
    assert parse_hysteria2(BASE_URL).insecure is False


def test_insecure_true():
    url = "hysteria2://pass@1.2.3.4:443?insecure=1#t"
    assert parse_hysteria2(url).insecure is True


def test_hy2_scheme():
    url = "hy2://secret@5.5.5.5:8080#alt"
    n = parse_hysteria2(url)
    assert n.auth == "secret"
    assert n.server == "5.5.5.5"
    assert n.port == 8080


def test_obfs_salamander():
    url = "hysteria2://pass@1.2.3.4:443?obfs=salamander&obfs-password=secret#t"
    n = parse_hysteria2(url)
    assert n.obfs_type == "salamander"
    assert n.obfs_password == "secret"


def test_outbound_no_obfs_when_absent():
    out = build_outbound(parse_hysteria2(BASE_URL))
    assert "obfs" not in out


def test_outbound_obfs_present():
    url = "hysteria2://pass@1.2.3.4:443?obfs=salamander&obfs-password=pw#t"
    out = build_outbound(parse_hysteria2(url))
    assert out["obfs"]["type"] == "salamander"
    assert out["obfs"]["password"] == "pw"


def test_bandwidth():
    url = "hysteria2://pass@1.2.3.4:443?up=10&down=50#t"
    n = parse_hysteria2(url)
    assert n.up_mbps == 10
    assert n.down_mbps == 50


def test_bandwidth_absent():
    n = parse_hysteria2(BASE_URL)
    assert n.up_mbps is None
    assert n.down_mbps is None


def test_outbound_no_bandwidth_when_absent():
    out = build_outbound(parse_hysteria2(BASE_URL))
    assert "up_mbps" not in out
    assert "down_mbps" not in out


def test_outbound_bandwidth_present():
    url = "hysteria2://pass@1.2.3.4:443?up=20&down=100#t"
    out = build_outbound(parse_hysteria2(url))
    assert out["up_mbps"] == 20
    assert out["down_mbps"] == 100


def test_outbound_structure():
    out = build_outbound(parse_hysteria2(BASE_URL))
    assert out["type"] == "hysteria2"
    assert out["password"] == "mypassword"
    assert out["tls"]["enabled"] is True
    assert out["tls"]["server_name"] == "example.com"


def test_outbound_uses_quic_not_tcp():
    # Hysteria2 is QUIC — no "network":"tcp" field should appear
    out = build_outbound(parse_hysteria2(BASE_URL))
    assert out.get("network") is None


def test_wrong_scheme_raises():
    with pytest.raises(ValueError, match="hysteria2"):
        parse_hysteria2("vless://uuid@1.2.3.4:443")


def test_extra_params_captured():
    url = "hysteria2://pass@1.2.3.4:443?unknownField=abc#t"
    n = parse_hysteria2(url)
    assert "unknownField" in n.extra_params


def test_roundtrip_serialization():
    n = parse_hysteria2(BASE_URL)
    d = n.to_dict()
    n2 = Hysteria2Node.model_validate(d)
    assert n2.auth == n.auth
    assert n2.protocol == "hysteria2"
