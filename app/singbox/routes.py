from __future__ import annotations
from typing import Any

DEFAULT_ROUTE_PRESET = "full_tunnel"

# "final" is injected at config-generation time — not stored here.
ROUTE_PRESETS: dict[str, dict[str, Any]] = {
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
}
