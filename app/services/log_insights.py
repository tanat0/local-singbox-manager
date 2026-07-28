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


_OPEN_CONNECTION_RE = re.compile(
    r"connection: open (?:outbound )?connection to (?P<target>\S+) "
    r"using outbound/(?P<protocol>[^\[]+)\[(?P<tag>[^\]]+)\]: (?P<reason>.+)$"
)
_CLOSED_CONNECTION_RE = re.compile(
    r"connection: connection (?P<direction>download|upload) closed: (?P<reason>.+)$"
)
_DIAL_TIMEOUT_RE = re.compile(
    r"dial tcp(?:4|6)? (?P<target>(?:\[[^\]]+\]|[^:\s]+):\d+): i/o timeout"
)
_DNS_RE = re.compile(r"dns: exchange failed for (?P<target>[^:]+): (?P<reason>.+)$")
_UNSUPPORTED_UDP_RE = re.compile(r"router: UDP is not supported by outbound: (?P<tag>\S+)")


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
            existing.last_seen = max(existing.last_seen, parsed.last_seen)
        else:
            buckets[key] = parsed

    return sorted(buckets.values(), key=lambda item: (item.count, item.last_seen), reverse=True)[:limit]


def _parse_line(line: str) -> Optional[LogInsight]:
    connection = _OPEN_CONNECTION_RE.search(line)
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

    closed = _CLOSED_CONNECTION_RE.search(line)
    if closed:
        reason = closed.group("reason")
        return LogInsight(
            kind="connection",
            target=_target_from_reason(reason),
            reason=_normalize_reason(reason),
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

    unsupported_udp = _UNSUPPORTED_UDP_RE.search(line)
    if unsupported_udp:
        return LogInsight(
            kind="routing",
            outbound_tag=unsupported_udp.group("tag").strip(),
            reason="UDP is not supported by outbound",
            count=1,
            last_seen=_timestamp_hint(line),
        )

    return None


def _normalize_reason(reason: str) -> str:
    text = " ".join(reason.strip().split())
    text = _strip_reason_wrapper(text)
    if "no recent network activity" in text:
        return "timeout: no recent network activity"
    if "read response: EOF" in text:
        return "dns response EOF"
    if _DIAL_TIMEOUT_RE.search(text):
        return "remote dial timeout"
    if "canceled by remote" in text:
        return "stream canceled by remote"
    if "operation was canceled" in text:
        return "operation canceled"
    return text[:160]


def _strip_reason_wrapper(text: str) -> str:
    for prefix in ("remote error: ", "remote: "):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def _target_from_reason(reason: str) -> Optional[str]:
    match = _DIAL_TIMEOUT_RE.search(reason)
    if match:
        return match.group("target")
    return None


def _timestamp_hint(line: str) -> str:
    first = line.split(maxsplit=1)[0] if line else ""
    return first if first and first[0].isdigit() else ""
