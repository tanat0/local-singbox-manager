# Import parsers to trigger @register() decorators — order matters for scheme matching
from app.parsers import hysteria2 as _hy2  # noqa: F401
from app.parsers import vless as _vless  # noqa: F401
from app.parsers.base import ParsedNode
from app.parsers.hysteria2 import Hysteria2Node
from app.parsers.registry import parse_url, supported_schemes
from app.parsers.vless import VlessNode

__all__ = [
    "parse_url", "supported_schemes",
    "ParsedNode", "VlessNode", "Hysteria2Node",
]
