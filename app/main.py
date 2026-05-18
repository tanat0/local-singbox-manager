from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

from app import notify
from app.auth import AuthMiddleware, emit_startup_warnings
from app.db import SessionLocal
from app.health import run_health_checks
from app.logging_config import get_logger, setup_logging
from app.models import HealthCheckLog
from app.routes import dashboard, logs, nodes, profiles, settings, system
from app.telegram_admin import create_bot_from_env
from app.version import VERSION
from app.web import BASE_DIR

_log = get_logger(__name__)

_HEALTH_CHECK_INTERVAL = int(os.environ.get("HEALTH_CHECK_INTERVAL", "300"))
_HEALTH_RETAIN_DAYS = 7
_last_health_state: str = "unknown"


def _run_migrations() -> None:
    ini = Path(__file__).parent.parent / "alembic.ini"
    cfg = AlembicConfig(str(ini))
    alembic_command.upgrade(cfg, "head")


async def _health_check_loop() -> None:
    global _last_health_state
    await asyncio.sleep(15)
    while True:
        try:
            report = await run_health_checks()
            now = datetime.utcnow()
            cutoff = now - timedelta(days=_HEALTH_RETAIN_DAYS)
            db = SessionLocal()
            try:
                for check in report.checks:
                    db.add(HealthCheckLog(
                        checked_at=now,
                        check_name=check.name,
                        category=check.category,
                        ok=check.ok,
                        latency_ms=check.latency_ms,
                        detail=check.detail,
                    ))
                db.query(HealthCheckLog).filter(HealthCheckLog.checked_at < cutoff).delete()
                db.commit()
            finally:
                db.close()

            _notify_health_change(_last_health_state, report.overall, report)
            _last_health_state = report.overall
        except Exception as e:
            _log.warning("Health check loop error: %s", e, exc_info=True)
        await asyncio.sleep(_HEALTH_CHECK_INTERVAL)


def _notify_health_change(prev: str, current: str, report: "HealthReport") -> None:  # type: ignore[name-defined]
    if prev == current or prev == "unknown":
        return
    if current == "connected":
        notify.fire("✓ Tunnel recovered", "All health checks passing", "info")
    elif current == "degraded":
        failing = [check.name for check in report.checks if not check.ok]
        notify.fire("⚠ Tunnel degraded", f"Failing: {', '.join(failing)}", "warning")
    elif current == "failed":
        notify.fire("✗ Tunnel failed", "All connectivity checks failing", "critical")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    _log.info("Sing-Box Manager v%s starting up", VERSION)
    emit_startup_warnings()
    _run_migrations()
    health_task = asyncio.create_task(_health_check_loop())
    telegram_bot = create_bot_from_env()
    telegram_task = asyncio.create_task(telegram_bot.run_forever()) if telegram_bot else None
    yield
    tasks = [health_task]
    if telegram_task:
        tasks.append(telegram_task)
    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Sing-Box Manager", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(AuthMiddleware)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(system.router)
app.include_router(dashboard.router)
app.include_router(nodes.router)
app.include_router(logs.router)
app.include_router(settings.router)
app.include_router(profiles.router)
