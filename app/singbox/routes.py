from __future__ import annotations

import copy
from typing import Any, Dict

DEFAULT_ROUTE_PRESET = "full_tunnel"

# sing-box 1.11+ rule_set URLs — binary .srs format from SagerNet's official repo.
# sing-box downloads and caches these on first use; no local geo DB needed.
_GEOIP_RU_SRS = "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-ru.srs"
_GEOSITE_RU_SRS = "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-ru.srs"

_DNS_HIJACK_RULE: dict[str, Any] = {"port": 53, "action": "hijack-dns"}

_ROUTE_GUARD_RULES: list[dict[str, Any]] = [
    {
        "domain": [
            "api.oneme.ru",
            "calls.okcdn.ru",
        ],
        "outbound": "block",
    },
    {
        "domain": [
            "ifconfig.me",
            "api.ipify.org",
            "checkip.amazonaws.com",
            "icanhazip.com",
            "wtfismyip.com",
        ],
        "outbound": "block",
    },
    {
        "domain_suffix": [
            ".ru",
            ".su",
        ],
        "domain": [
            "gosuslugi.ru",
        ],
        "outbound": "direct",
    },
]

# "final" is injected at config-generation time — not stored here.
ROUTE_PRESETS: Dict[str, Dict[str, Any]] = {
    "full_tunnel": {
        "label": "Full Tunnel",
        "description": "All traffic through VPN",
        "route": {
            "rules": [],
            "auto_detect_interface": True,
        },
    },
    "bypass_lan": {
        "label": "Bypass LAN",
        "description": "LAN / RFC1918 addresses go direct; everything else through VPN",
        "route": {
            "rules": [
                {"ip_is_private": True, "outbound": "direct"},
            ],
            "auto_detect_interface": True,
        },
    },
    "bypass_ru": {
        "label": "Bypass Russia",
        "description": (
            "Russian IPs and domains go direct; everything else through VPN. "
            "Rule sets are downloaded by sing-box on first use (~10 MB, cached)."
        ),
        "route": {
            "rule_set": [
                {
                    "tag": "geoip-ru",
                    "type": "remote",
                    "format": "binary",
                    "url": _GEOIP_RU_SRS,
                    "download_detour": "direct",
                    "update_interval": "7d",
                },
                {
                    "tag": "geosite-ru",
                    "type": "remote",
                    "format": "binary",
                    "url": _GEOSITE_RU_SRS,
                    "download_detour": "direct",
                    "update_interval": "7d",
                },
            ],
            "rules": [
                {"rule_set": ["geoip-ru", "geosite-ru"], "outbound": "direct"},
                {"ip_is_private": True, "outbound": "direct"},
            ],
            "auto_detect_interface": True,
        },
    },
}


def build_route_config(route_preset: str) -> Dict[str, Any]:
    """Build a route config with always-on local route guards."""
    if route_preset not in ROUTE_PRESETS:
        raise ValueError(f"Unknown route preset: {route_preset!r}")

    route = copy.deepcopy(ROUTE_PRESETS[route_preset]["route"])
    preset_rules = route.get("rules", [])
    route["rules"] = [
        copy.deepcopy(_DNS_HIJACK_RULE),
        *copy.deepcopy(_ROUTE_GUARD_RULES),
        *preset_rules,
    ]
    return route
