from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.repositories import HealthLogRepository


def latency_series(db: Session, hours: int) -> Dict[str, object]:
    bounded_hours = _bounded_hours(hours)
    cutoff = datetime.utcnow() - timedelta(hours=bounded_hours)
    rows = HealthLogRepository(db).recent_connectivity(cutoff)

    by_name: Dict[str, List[object]] = {}
    for row in rows:
        by_name.setdefault(row.check_name, []).append(row)

    series = []
    for name, checks in by_name.items():
        total = len(checks)
        ok_count = sum(1 for check in checks if check.ok)
        latencies = [check.latency_ms for check in checks if check.ok and check.latency_ms is not None]
        series.append({
            "name": name,
            "points": [_latency_point(check) for check in checks],
            "uptime_pct": round(ok_count / total * 100, 1) if total else None,
            "avg_ms": round(statistics.mean(latencies), 1) if latencies else None,
            "p95_ms": _p95(latencies),
            "sample_count": total,
        })

    return {"hours": bounded_hours, "series": series}


def connectivity_summary(db: Session, hours: int) -> Dict[str, object]:
    bounded_hours = _bounded_hours(hours)
    cutoff = datetime.utcnow() - timedelta(hours=bounded_hours)
    rows = HealthLogRepository(db).recent_connectivity(cutoff)
    return _summary(rows, bounded_hours)


def node_health_summary(db: Session, hours: int) -> Dict[str, Dict[str, object]]:
    bounded_hours = _bounded_hours(hours)
    cutoff = datetime.utcnow() - timedelta(hours=bounded_hours)
    rows = HealthLogRepository(db).recent_connectivity(cutoff)

    by_tag: Dict[str, List[object]] = {}
    for row in rows:
        if row.node_tag:
            by_tag.setdefault(row.node_tag, []).append(row)

    return {tag: _summary(checks, bounded_hours) for tag, checks in by_tag.items()}


def _latency_point(check) -> Dict[str, object]:
    ts = check.checked_at.strftime("%H:%M") if check.checked_at else "?"
    return {
        "t": ts,
        "ms": round(check.latency_ms, 1) if check.latency_ms is not None else None,
        "ok": check.ok,
    }


def _bounded_hours(hours: int) -> int:
    return min(max(hours, 1), 168)


def _summary(checks: List[object], hours: int) -> Dict[str, object]:
    total = len(checks)
    ok_count = sum(1 for check in checks if check.ok)
    latencies = [check.latency_ms for check in checks if check.ok and check.latency_ms is not None]
    return {
        "hours": hours,
        "uptime_pct": round(ok_count / total * 100, 1) if total else None,
        "avg_ms": round(statistics.mean(latencies), 1) if latencies else None,
        "p95_ms": _p95(latencies),
        "sample_count": total,
    }


def _p95(latencies: List[float]) -> Optional[float]:
    if len(latencies) < 2:
        return None
    return round(sorted(latencies)[int(len(latencies) * 0.95)], 1)
