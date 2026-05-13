from __future__ import annotations
from typing import Any, Dict

DEFAULT_ROUTE_PRESET = "full_tunnel"

# sing-box 1.11+ rule_set URLs — binary .srs format from SagerNet's official repo.
# sing-box downloads and caches these on first use; no local geo DB needed.
_GEOIP_RU_SRS = "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-ru.srs"
_GEOSITE_RU_SRS = "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-ru.srs"

# "final" is injected at config-generation time — not stored here.
ROUTE_PRESETS: Dict[str, Dict[str, Any]] = {
    "full_tunnel": {
        "label": "Full Tunnel",
        "description": "All traffic through VPN",
        "route": {
            "rules": [
                {"port": 53, "action": "hijack-dns"},
            ],
            "auto_detect_interface": True,
        },
    },
    "bypass_lan": {
        "label": "Bypass LAN",
        "description": "LAN / RFC1918 addresses go direct; everything else through VPN",
        "route": {
            "rules": [
                {"port": 53, "action": "hijack-dns"},
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
                {"port": 53, "action": "hijack-dns"},
                {"rule_set": ["geoip-ru", "geosite-ru"], "outbound": "direct"},
                {"ip_is_private": True, "outbound": "direct"},
            ],
            "auto_detect_interface": True,
        },
    },
}
