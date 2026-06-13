from __future__ import annotations

import copy
from typing import Any

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


def build_tun_inbound() -> dict[str, Any]:
    return copy.deepcopy(_TUN_INBOUND)
