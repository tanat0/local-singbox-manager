from __future__ import annotations

import json
from typing import Iterable, List


def parse_node_tags(raw: str) -> List[str]:
    tags: List[str] = []
    seen = set()
    for part in raw.replace("\n", ",").split(","):
        tag = part.strip()
        if tag and tag not in seen:
            tags.append(tag)
            seen.add(tag)
    return tags


def encode_node_tags(tags: Iterable[str]) -> str:
    return json.dumps(list(tags), ensure_ascii=False)


def decode_node_tags(raw: str) -> List[str]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [str(item) for item in data if str(item).strip()]
    except Exception:
        pass
    return []
