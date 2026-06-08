from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class LogInsight:
    kind: str
    reason: str
    count: int
    last_seen: str
    protocol: Optional[str] = None
    outbound_tag: Optional[str] = None
    target: Optional[str] = None


_CONNECTION_RE = re.compile(
    r"connection: open connection to (?P<target>\S+) "
    r"using outbound/(?P<protocol>[^\[]+)\[(?P<tag>[^\]]+)\]: (?P<reason>.+)$"
)
_DNS_RE = re.compile(r"dns: exchange failed for (?P<target>[^:]+): (?P<reason>.+)$")


def summarize_problem_logs(text: str, limit: int = 8) -> List[LogInsight]:
    buckets: Dict[Tuple[object, ...], LogInsight] = {}
    for line in text.splitlines():
        parsed = _parse_line(line)
        if not parsed:
            continue
        key = (
            parsed.kind,
            parsed.protocol,
            parsed.outbound_tag,
            parsed.target,
            parsed.reason,
        )
        existing = buckets.get(key)
        if existing:
            existing.count += 1
            existing.last_seen = parsed.last_seen
        else:
            buckets[key] = parsed

    return sorted(buckets.values(), key=lambda item: (-item.count, item.last_seen))[:limit]


def _parse_line(line: str) -> Optional[LogInsight]:
    connection = _CONNECTION_RE.search(line)
    if connection:
        return LogInsight(
            kind="connection",
            protocol=connection.group("protocol").strip(),
            outbound_tag=connection.group("tag").strip(),
            target=connection.group("target").strip(),
            reason=_normalize_reason(connection.group("reason")),
            count=1,
            last_seen=_timestamp_hint(line),
        )

    dns = _DNS_RE.search(line)
    if dns:
        return LogInsight(
            kind="dns",
            target=dns.group("target").strip(),
            reason=_normalize_reason(dns.group("reason")),
            count=1,
            last_seen=_timestamp_hint(line),
        )

    return None


def _normalize_reason(reason: str) -> str:
    text = " ".join(reason.strip().split())
    if "no recent network activity" in text:
        return "timeout: no recent network activity"
    if "read response: EOF" in text:
        return "dns response EOF"
    return text[:160]


def _timestamp_hint(line: str) -> str:
    first = line.split(maxsplit=1)[0] if line else ""
    return first if first and first[0].isdigit() else ""
