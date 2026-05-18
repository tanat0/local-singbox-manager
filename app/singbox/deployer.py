from __future__ import annotations
import asyncio
import hashlib
import json
import os
import re
import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from app.config import settings
from app.logging_config import get_logger
from app.notify import fire as _notify
from app.singbox import service as svc
from app.singbox.validator import validate_config
from app.system_clients import SubprocessCommandRunner, SystemServiceClient

_log = get_logger(__name__)

HELPER_BIN = settings.system_paths.helper_bin
_runner = SubprocessCommandRunner()
_system = SystemServiceClient(_runner, HELPER_BIN)

# Module-level lock: only one deploy pipeline runs at a time.
_deploy_lock = asyncio.Lock()


def config_hash(config: dict) -> str:
    """Stable sha256 of the config — keys sorted, no whitespace variance."""
    canonical = json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class DeployResult:
    success: bool
    stage: str = ""          # validate | deploy | restart | health | ok
    error: str = ""
    rolled_back: bool = False
    backup_name: Optional[str] = None
    node_tag: Optional[str] = None
    config_hash: Optional[str] = None

    def user_message(self) -> str:
        if self.success:
            suffix = f" (backup: {self.backup_name})" if self.backup_name else ""
            return f"✓ Active: {self.node_tag}{suffix}"
        base = f"Deploy failed at '{self.stage}': {self.error}"
        if self.rolled_back:
            base += " — automatically rolled back to previous config"
        elif self.backup_name:
            base += f" — manual rollback available: {self.backup_name}"
        return base


def _run_helper(*args: str, timeout: int = 30) -> tuple[bool, str]:
    if not args:
        return False, "Helper action is required"
    result = _system.helper(args[0], *args[1:], timeout=timeout)
    if not result.ok and result.output.startswith("Command not found"):
        return False, f"Helper not found at {HELPER_BIN}. See README install steps."
    return result.ok, result.output


def _extract_backup_name(output: str) -> Optional[str]:
    m = re.search(r'config_\d{8}_\d{6}\.json', output)
    return m.group(0) if m else None


def _service_is_active() -> bool:
    return _system.is_active()


async def _wait_service_active(attempts: int = 6, delay: float = 1.0) -> bool:
    for _ in range(attempts):
        if _service_is_active():
            return True
        await asyncio.sleep(delay)
    return False


def _do_rollback(backup_name: str) -> tuple[bool, str]:
    _log.warning("Rolling back: restoring %s", backup_name)
    ok, out = _run_helper("restore", backup_name)
    if not ok:
        _log.error("Rollback FAILED for %s: %s", backup_name, out)
        _notify("⚠ Rollback FAILED", f"Manual recovery needed. Backup: {backup_name}", "critical")
        return False, f"restore failed: {out}"
    _run_helper("restart")   # best-effort restart after rollback
    _log.info("Rollback successful: restored %s", backup_name)
    _notify("↩ Rolled back", f"Restored {backup_name} after failed deploy", "warning")
    return True, out


async def deploy_with_rollback(
    config: dict,
    node_tag: str,
    health_check: bool = True,
) -> DeployResult:
    if _deploy_lock.locked():
        return DeployResult(
            success=False, stage="lock",
            error="Another deploy is already in progress — try again in a moment",
        )

    async with _deploy_lock:
        return await _run_deploy(config, node_tag, health_check)


async def _run_deploy(config: dict, node_tag: str, health_check: bool) -> DeployResult:
    cfg_hash = config_hash(config)
    deploy_started = datetime.now() - timedelta(seconds=2)
    _log.info("Deploy starting: node=%s hash=%.8s", node_tag, cfg_hash)

    # 1. Validate before touching anything
    ok, err = validate_config(config)
    if not ok:
        _log.warning("Deploy aborted — config invalid: %s", err)
        _notify("✗ Deploy failed", f"Config invalid: {err}", "critical")
        return DeployResult(success=False, stage="validate", error=err,
                            config_hash=cfg_hash)

    # 2. Write temp file and deploy via helper (helper creates the backup)
    tmppath = f"/tmp/singbox-deploy-{_uuid.uuid4()}.json"
    try:
        with open(tmppath, "w") as f:
            json.dump(config, f, indent=2)
        os.chmod(tmppath, 0o644)
        ok, output = _run_helper("deploy", tmppath)
    finally:
        if os.path.exists(tmppath):
            os.unlink(tmppath)

    if not ok:
        _log.warning("Deploy failed at 'deploy' stage: %s", output)
        _notify("✗ Deploy failed", f"Stage: deploy — {output}", "critical")
        return DeployResult(success=False, stage="deploy", error=output,
                            config_hash=cfg_hash)

    backup_name = _extract_backup_name(output)

    # 3. Restart service. TUN configs should not use reload: sing-box may try to
    # re-open the existing TUN interface and fail with TUNSETIFF busy.
    ok, err = _run_helper("restart")
    if not ok:
        _log.warning("Service restart failed: %s", err)
        detail = svc.get_failure_detail(since=deploy_started.strftime("%Y-%m-%d %H:%M:%S"))
        if detail:
            err = f"{err} | {detail}"
        _notify("✗ Deploy failed", f"Stage: restart — {err}", "critical")
        rolled_back = False
        if backup_name:
            rolled_back, _ = _do_rollback(backup_name)
        return DeployResult(
            success=False, stage="restart", error=err,
            rolled_back=rolled_back, backup_name=backup_name,
            config_hash=cfg_hash,
        )

    # 4. Health check — wait for service to stabilise, then verify active
    if health_check:
        if not await _wait_service_active():
            detail = svc.get_failure_detail(since=deploy_started.strftime("%Y-%m-%d %H:%M:%S"))
            error = "sing-box.service not active after restart"
            if detail:
                error = f"{error}: {detail}"
            _log.warning("Health check failed: %s", error)
            _notify("✗ Deploy failed", f"Stage: health — {error}", "critical")
            rolled_back = False
            if backup_name:
                rolled_back, _ = _do_rollback(backup_name)
            return DeployResult(
                success=False, stage="health",
                error=error,
                rolled_back=rolled_back, backup_name=backup_name,
                config_hash=cfg_hash,
            )

    _log.info("Deploy successful: node=%s backup=%s", node_tag, backup_name)
    _notify("✓ Tunnel active", f"Node: {node_tag}", "info")
    return DeployResult(success=True, stage="ok", node_tag=node_tag,
                        backup_name=backup_name, config_hash=cfg_hash)


def list_backups() -> list[str]:
    ok, out = _run_helper("list-backups")
    if not ok:
        return []
    try:
        return json.loads(out)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def restore_backup(name: str) -> tuple[bool, str]:
    return _run_helper("restore", name)


def get_current_config() -> Optional[dict]:
    """Read deployed config directly — readable at 0o644, no sudo needed."""
    try:
        with open("/etc/sing-box/config.json") as f:
            return json.load(f)
    except (FileNotFoundError, PermissionError, json.JSONDecodeError, OSError) as exc:
        _log.debug("Could not read deployed config: %s", exc)
        return None
