from __future__ import annotations

import copy
from typing import Any, Sequence

from app.parsers.base import ParsedNode
from app.singbox.dns import DEFAULT_DNS_PRESET, DNS_PRESETS
from app.singbox.generator import build_outbound
from app.singbox.inbounds import build_tun_inbound
from app.singbox.routes import DEFAULT_ROUTE_PRESET, ROUTE_PRESETS, build_route_config

RESERVED_CLIENT_OUTBOUND_TAGS = frozenset({"direct", "block", "proxy"})
_ALLOWED_LOG_LEVELS = {"error", "warn", "info", "debug"}


def generate_client_config(
    nodes: Sequence[ParsedNode],
    route_preset: str = DEFAULT_ROUTE_PRESET,
    dns_preset: str = DEFAULT_DNS_PRESET,
    log_level: str = "warn",
) -> dict[str, Any]:
    if not nodes:
        raise ValueError("At least one node is required")
    if dns_preset not in DNS_PRESETS:
        raise ValueError(f"Unknown DNS preset: {dns_preset!r}")
    if route_preset not in ROUTE_PRESETS:
        raise ValueError(f"Unknown route preset: {route_preset!r}")
    if log_level not in _ALLOWED_LOG_LEVELS:
        raise ValueError(f"Unknown sing-box log level: {log_level!r}")

    sorted_nodes = sorted(nodes, key=lambda item: item.tag)
    tags = [node.tag for node in sorted_nodes]
    _validate_node_tags(tags)

    proxy_outbounds = [build_outbound(node) for node in sorted_nodes]
    final_tag = tags[0]
    if len(proxy_outbounds) > 1:
        proxy_outbounds.append({
            "type": "selector",
            "tag": "proxy",
            "outbounds": tags,
            "default": tags[0],
        })
        final_tag = "proxy"

    route = build_route_config(route_preset)
    route["final"] = final_tag

    return {
        "log": {"level": log_level, "timestamp": True},
        "dns": copy.deepcopy(DNS_PRESETS[dns_preset]["config"]),
        "inbounds": [build_tun_inbound()],
        "route": route,
        "outbounds": [
            *proxy_outbounds,
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ],
    }


def _validate_node_tags(tags: Sequence[str]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for tag in tags:
        if tag in seen:
            duplicates.add(tag)
        seen.add(tag)

    if duplicates:
        raise ValueError(f"Duplicate node tag(s): {', '.join(sorted(duplicates)[:5])}")

    reserved = sorted(tag for tag in tags if tag in RESERVED_CLIENT_OUTBOUND_TAGS)
    if reserved:
        raise ValueError(f"Reserved node tag(s) cannot be used for client configs: {', '.join(reserved)}")
