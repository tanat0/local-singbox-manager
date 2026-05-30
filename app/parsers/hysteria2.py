from __future__ import annotations

from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

from app.parsers.base import ParsedNode
from app.parsers.registry import register

_KNOWN = {"sni", "insecure", "security", "obfs", "obfs-password", "obfsParam",
          "up", "upmbps", "up_mbps", "down", "downmbps", "down_mbps"}


class Hysteria2Node(ParsedNode):
    protocol: str = "hysteria2"
    auth: str
    sni: Optional[str] = None
    insecure: bool = False
    obfs_type: Optional[str] = None
    obfs_password: Optional[str] = None
    up_mbps: Optional[int] = None
    down_mbps: Optional[int] = None


def _parse_mbps(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    try:
        return int(float(s.strip().upper().rstrip("MBPS").strip()))
    except (ValueError, TypeError):
        return None


@register("hysteria2://", "hy2://")
def parse_hysteria2(url: str) -> Hysteria2Node:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("hysteria2", "hy2"):
        raise ValueError(f"Expected hysteria2:// or hy2://, got {parsed.scheme}://")

    # auth may be in username or password field depending on client
    auth = unquote(parsed.username or parsed.password or "")
    if not auth:
        raise ValueError("Missing auth/password in Hysteria2 URL")
    server = parsed.hostname
    if not server:
        raise ValueError("Missing server in Hysteria2 URL")
    port = parsed.port or 443
    tag = unquote(parsed.fragment).strip() if parsed.fragment else f"hy2-{server}"

    params = parse_qs(parsed.query)

    def p(key: str) -> Optional[str]:
        v = params.get(key)
        return v[0] if v else None

    return Hysteria2Node(
        raw_url=url,
        tag=tag,
        server=server,
        port=port,
        auth=auth,
        sni=p("sni"),
        insecure=p("insecure") in ("1", "true"),
        obfs_type=p("obfs"),
        obfs_password=p("obfs-password") or p("obfsParam"),
        up_mbps=_parse_mbps(p("up") or p("upmbps") or p("up_mbps")),
        down_mbps=_parse_mbps(p("down") or p("downmbps") or p("down_mbps")),
        extra_params={k: v[0] for k, v in params.items() if k not in _KNOWN},
    )
