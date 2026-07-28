from __future__ import annotations

from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

from app.parsers.base import ParsedNode
from app.parsers.registry import register

_KNOWN = {
    "type",
    "security",
    "sni",
    "pbk",
    "sid",
    "fp",
    "flow",
    "allowInsecure",
    "headerType",
    "path",
    "host",
    "serviceName",
}

_TRANSPORT_ALIASES = {
    "tcp": "tcp",
    "http": "http",
    "h2": "http",
    "http2": "http",
    "grpc": "grpc",
    "ws": "ws",
    "websocket": "ws",
    "httpupgrade": "httpupgrade",
    "xhttp": "xhttp",
    "splithttp": "xhttp",
    "quic": "quic",
}


class VlessNode(ParsedNode):
    protocol: str = "vless"
    uuid: str
    network: str = "tcp"
    transport_type: str = "tcp"
    security: str = "none"
    sni: Optional[str] = None
    pbk: Optional[str] = None     # Reality public key
    sid: Optional[str] = None     # Reality short ID
    fp: Optional[str] = None      # uTLS fingerprint
    flow: Optional[str] = None    # Only "xtls-rprx-vision" if explicitly in URL
    insecure: bool = False
    path: Optional[str] = None
    host: Optional[str] = None
    service_name: Optional[str] = None
    header_type: Optional[str] = None


@register("vless://")
def parse_vless(url: str) -> VlessNode:
    parsed = urlparse(url.strip())
    if parsed.scheme != "vless":
        raise ValueError(f"Expected vless://, got {parsed.scheme}://")

    uuid = parsed.username
    if not uuid:
        raise ValueError("Missing UUID in VLESS URL")
    server = parsed.hostname
    if not server:
        raise ValueError("Missing server in VLESS URL")
    port = parsed.port
    if not port:
        raise ValueError("Missing port in VLESS URL")

    tag = unquote(parsed.fragment).strip() if parsed.fragment else f"vless-{server}"
    params = parse_qs(parsed.query)

    def p(key: str) -> Optional[str]:
        v = params.get(key)
        return v[0] if v else None

    return VlessNode(
        raw_url=url,
        tag=tag,
        server=server,
        port=port,
        uuid=uuid,
        network="tcp",
        transport_type=_normalize_transport_type(p("type")),
        security=p("security") or "none",
        sni=p("sni"),
        pbk=p("pbk"),
        sid=p("sid"),
        fp=p("fp") or "chrome",
        flow=p("flow") or None,   # omit if not present — do NOT assume Vision
        insecure=p("allowInsecure") in ("1", "true"),
        path=p("path"),
        host=p("host"),
        service_name=p("serviceName"),
        header_type=p("headerType"),
        extra_params={k: v[0] for k, v in params.items() if k not in _KNOWN},
    )


def _normalize_transport_type(value: Optional[str]) -> str:
    if not value:
        return "tcp"
    return _TRANSPORT_ALIASES.get(value.strip().lower(), value.strip().lower())
