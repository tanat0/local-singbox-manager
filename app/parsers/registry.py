from __future__ import annotations
from typing import Callable, Dict, List
from app.parsers.base import ParsedNode

_REGISTRY: Dict[str, Callable[[str], ParsedNode]] = {}


def register(*schemes: str) -> Callable:
    """Decorator: register a parser for one or more URL schemes."""
    def decorator(fn: Callable[[str], ParsedNode]) -> Callable[[str], ParsedNode]:
        for scheme in schemes:
            _REGISTRY[scheme] = fn
        return fn
    return decorator


def parse_url(url: str) -> ParsedNode:
    url = url.strip()
    for scheme, parser in _REGISTRY.items():
        if url.startswith(scheme):
            return parser(url)
    supported = ", ".join(sorted(_REGISTRY.keys()))
    raise ValueError(f"Unsupported URL scheme. Supported: {supported}")


def supported_schemes() -> List[str]:
    return sorted(_REGISTRY.keys())
