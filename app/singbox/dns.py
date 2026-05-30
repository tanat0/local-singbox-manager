from __future__ import annotations

from typing import Any

DEFAULT_DNS_PRESET = "quad9_tls"

# Uses sing-box 1.13+ DNS server format — NOT the deprecated "address": "tls://..." form.
DNS_PRESETS: dict[str, dict[str, Any]] = {
    "quad9_tls": {
        "label": "Quad9 (DoT)",
        "description": "Privacy-focused, blocks malware domains",
        "config": {
            "servers": [{"type": "tls", "tag": "quad9", "server": "9.9.9.9", "server_port": 853}],
            "final": "quad9",
        },
    },
    "cloudflare_tls": {
        "label": "Cloudflare (DoT)",
        "description": "Fast global resolver",
        "config": {
            "servers": [{"type": "tls", "tag": "cf", "server": "1.1.1.1", "server_port": 853}],
            "final": "cf",
        },
    },
    "google_tls": {
        "label": "Google (DoT)",
        "description": "Google Public DNS over TLS",
        "config": {
            "servers": [{"type": "tls", "tag": "google", "server": "8.8.8.8", "server_port": 853}],
            "final": "google",
        },
    },
}
