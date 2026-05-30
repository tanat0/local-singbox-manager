from __future__ import annotations

import copy
import json
from typing import Any

from app.parsers.base import ParsedNode
from app.parsers.hysteria2 import Hysteria2Node
from app.parsers.vless import VlessNode
from app.singbox.dns import DEFAULT_DNS_PRESET, DNS_PRESETS
from app.singbox.routes import DEFAULT_ROUTE_PRESET, ROUTE_PRESETS

_TUN_INBOUND: dict[str, Any] = {
    "type": "tun",
    "tag": "tun-in",
    "interface_name": "singtun0",
    "address": ["172.19.0.1/30"],
    "mtu": 1500,
    "auto_route": True,
    "strict_route": True,
    "auto_redirect": True,
    "stack": "gvisor",
}


def _build_vless_outbound(node: VlessNode) -> dict[str, Any]:
    out: dict[str, Any] = {
        "type": "vless",
        "tag": node.tag,
        "server": node.server,
        "server_port": node.port,
        "uuid": node.uuid,
        "network": node.network,
    }
    # flow is ONLY added when explicitly present in the URL
    if node.flow:
        out["flow"] = node.flow

    if node.security == "reality":
        if not node.pbk:
            raise ValueError("VLESS Reality requires pbk (public_key) in URL")
        out["tls"] = {
            "enabled": True,
            "server_name": node.sni or node.server,
            "insecure": node.insecure,
            "utls": {"enabled": True, "fingerprint": node.fp or "chrome"},
            "reality": {
                "enabled": True,
                "public_key": node.pbk,
                "short_id": node.sid or "",
            },
        }
    elif node.security == "tls":
        out["tls"] = {
            "enabled": True,
            "server_name": node.sni or node.server,
            "insecure": node.insecure,
        }

    return out


def _build_hysteria2_outbound(node: Hysteria2Node) -> dict[str, Any]:
    # Hysteria2 uses QUIC/UDP — do not apply TCP-specific assumptions
    out: dict[str, Any] = {
        "type": "hysteria2",
        "tag": node.tag,
        "server": node.server,
        "server_port": node.port,
        "password": node.auth,
    }

    tls: dict[str, Any] = {"enabled": True, "insecure": node.insecure}
    if node.sni:
        tls["server_name"] = node.sni
    out["tls"] = tls

    if node.obfs_type:
        out["obfs"] = {"type": node.obfs_type, "password": node.obfs_password or ""}

    if node.up_mbps is not None:
        out["up_mbps"] = node.up_mbps
    if node.down_mbps is not None:
        out["down_mbps"] = node.down_mbps

    return out


def build_outbound(node: ParsedNode) -> dict[str, Any]:
    if isinstance(node, VlessNode):
        return _build_vless_outbound(node)
    if isinstance(node, Hysteria2Node):
        return _build_hysteria2_outbound(node)
    raise ValueError(f"No outbound builder registered for protocol: {node.protocol!r}")


def generate_config(
    node: ParsedNode,
    dns_preset: str = DEFAULT_DNS_PRESET,
    route_preset: str = DEFAULT_ROUTE_PRESET,
    log_level: str = "warn",
) -> dict[str, Any]:
    if dns_preset not in DNS_PRESETS:
        raise ValueError(f"Unknown DNS preset: {dns_preset!r}")
    if route_preset not in ROUTE_PRESETS:
        raise ValueError(f"Unknown route preset: {route_preset!r}")

    active = build_outbound(node)

    route = copy.deepcopy(ROUTE_PRESETS[route_preset]["route"])
    route["final"] = active["tag"]

    if log_level not in {"error", "warn", "info", "debug"}:
        raise ValueError(f"Unknown sing-box log level: {log_level!r}")

    return {
        "log": {"level": log_level, "timestamp": True},
        "dns": copy.deepcopy(DNS_PRESETS[dns_preset]["config"]),
        "inbounds": [copy.deepcopy(_TUN_INBOUND)],
        "route": route,
        "outbounds": [
            active,
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ],
    }


def config_to_json(config: dict[str, Any]) -> str:
    return json.dumps(config, ensure_ascii=False, indent=2)
