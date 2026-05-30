"""Tests for app/parsers/registry.py and parse_url dispatch."""
from __future__ import annotations

import pytest

from app.parsers import parse_url, supported_schemes
from app.parsers.hysteria2 import Hysteria2Node
from app.parsers.vless import VlessNode

_VLESS_URL = (
    "vless://some-uuid-here@example.com:443"
    "?type=tcp&security=reality&sni=example.com"
    "&pbk=pubkey123&sid=shortid&fp=chrome"
    "#my-node"
)

_HY2_URL = "hysteria2://password@example.com:443#hy2-node"


# ── supported_schemes ─────────────────────────────────────────────────────────

def test_supported_schemes_sorted():
    schemes = supported_schemes()
    assert schemes == sorted(schemes)


def test_supported_schemes_contains_vless_and_hy2():
    schemes = supported_schemes()
    assert any("vless" in s for s in schemes)
    assert any("hysteria2" in s or "hy2" in s for s in schemes)


# ── parse_url dispatch ────────────────────────────────────────────────────────

def test_parse_vless_dispatches_to_vless_node():
    node = parse_url(_VLESS_URL)
    assert isinstance(node, VlessNode)
    assert node.protocol == "vless"
    assert node.tag == "my-node"
    assert node.server == "example.com"
    assert node.port == 443


def test_parse_hy2_dispatches_to_hysteria2_node():
    node = parse_url(_HY2_URL)
    assert isinstance(node, Hysteria2Node)
    assert node.protocol in ("hysteria2", "hy2")
    assert node.tag == "hy2-node"
    assert node.server == "example.com"
    assert node.port == 443


def test_unsupported_scheme_raises_with_supported_list():
    with pytest.raises(ValueError) as exc_info:
        parse_url("wireguard://peer@host:51820")
    msg = str(exc_info.value)
    assert "Unsupported" in msg
    assert "vless" in msg.lower() or "hysteria" in msg.lower()


def test_empty_url_raises():
    with pytest.raises((ValueError, Exception)):
        parse_url("")


def test_whitespace_stripped_before_matching():
    node = parse_url("  " + _VLESS_URL + "  ")
    assert isinstance(node, VlessNode)


def test_parse_url_strips_trailing_newline():
    node = parse_url(_VLESS_URL + "\n")
    assert isinstance(node, VlessNode)


# ── VLESS edge cases ──────────────────────────────────────────────────────────

def test_vless_missing_uuid_raises():
    url = "vless://@host.com:443?type=tcp#no-uuid"
    with pytest.raises(ValueError, match="UUID"):
        parse_url(url)


def test_vless_missing_server_raises():
    url = "vless://uuid@:443?type=tcp#no-host"
    with pytest.raises((ValueError, Exception)):
        parse_url(url)


def test_vless_missing_port_raises():
    url = "vless://uuid@host.com?type=tcp#no-port"
    with pytest.raises(ValueError, match="port"):
        parse_url(url)


def test_vless_allow_insecure_string_true():
    # Param must go before the # fragment
    url = (
        "vless://some-uuid-here@example.com:443"
        "?type=tcp&security=tls&sni=example.com&fp=chrome&allowInsecure=1"
        "#my-node"
    )
    node = parse_url(url)
    assert isinstance(node, VlessNode)
    assert node.insecure is True


def test_vless_allow_insecure_false_by_default():
    node = parse_url(_VLESS_URL)
    assert node.insecure is False


def test_vless_no_fragment_uses_server_as_tag():
    url = "vless://some-uuid@myserver.com:443?type=tcp&security=none"
    node = parse_url(url)
    assert "myserver.com" in node.tag


def test_vless_flow_omitted_when_not_in_url():
    node = parse_url(_VLESS_URL)
    assert node.flow is None


def test_vless_flow_set_when_in_url():
    url = (
        "vless://some-uuid-here@example.com:443"
        "?type=tcp&security=reality&sni=example.com"
        "&pbk=pubkey123&sid=shortid&fp=chrome&flow=xtls-rprx-vision"
        "#my-node"
    )
    node = parse_url(url)
    assert node.flow == "xtls-rprx-vision"


# ── Hysteria2 edge cases ──────────────────────────────────────────────────────

def test_hy2_port_from_url():
    node = parse_url("hysteria2://pass@host.com:8443#hy2")
    assert node.port == 8443


def test_hy2_sni_from_params():
    node = parse_url("hysteria2://pass@host.com:443?sni=custom.sni#hy2")
    assert node.sni == "custom.sni"


def test_hy2_insecure_from_params():
    node = parse_url("hysteria2://pass@host.com:443?insecure=1#hy2")
    assert node.insecure is True
