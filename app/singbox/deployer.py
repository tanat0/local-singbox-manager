from __future__ import annotations
import asyncio
import hashlib
import json
import os
import re
import subprocess
import uuid as _uuid
from dataclasses import dataclass
from typing import Optional

from app.logging_config import get_logger
from app.singbox.validator import validate_config

_log = get_logger(__name__)

HELPER_BIN = os.environ.get("HELPER_BIN", "/usr/local/bin/singbox-manager-helper")

# Module-level lock: only one deploy pipeline runs at a time.
_deploy_lock = asyncio.Lock()


def config_hash(config: dict) -> str:
    """Stable sha256 of the config — keys sorted, no whitespace variance."""
    canonical = json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class DeployResult:
    success: bool
    stage: str = ""          # validate | deploy | reload | health | ok
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
    try:
        result = subprocess.run(
            ["sudo", HELPER_BIN, *args],
            capture_output=True, text=True, timeout=timeout,
        )
        out = (result.stdout + result.stderr).strip()
        return result.returncode == 0, out
    except subprocess.TimeoutExpired:
        return False, f"Helper timed out after {timeout}s"
    except FileNotFoundError:
        return False, f"Helper not found at {HELPER_BIN}. See README install steps."
    except Exception as e:
        return False, str(e)


def _extract_backup_name(output: str) -> Optional[str]:
    m = re.search(r'config_\d{8}_\d{6}\.json', output)
    return m.group(0) if m else None


def _service_is_active() -> bool:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "sing-box.service"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() == "active"
    except Exception:
        return False


def _do_rollback(backup_name: str) -> tuple[bool, str]:
    _log.warning("Rolling back: restoring %s", backup_name)
    ok, out = _run_helper("restore", backup_name)
    if not ok:
        _log.error("Rollback FAILED for %s: %s", backup_name, out)
        return False, f"restore failed: {out}"
    _run_helper("restart")   # best-effort restart after rollback
    _log.info("Rollback successful: restored %s", backup_name)
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
    _log.info("Deploy starting: node=%s hash=%.8s", node_tag, cfg_hash)

    # 1. Validate before touching anything
    ok, err = validate_config(config)
    if not ok:
        _log.warning("Deploy aborted — config invalid: %s", err)
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
        return DeployResult(success=False, stage="deploy", error=output,
                            config_hash=cfg_hash)

    backup_name = _extract_backup_name(output)

    # 3. Reload/restart service
    ok, err = _run_helper("reload")
    if not ok:
        ok, err = _run_helper("restart")  # fallback if ExecReload not configured
    if not ok:
        _log.warning("Service reload/restart failed: %s", err)
        rolled_back = False
        if backup_name:
            rolled_back, _ = _do_rollback(backup_name)
        return DeployResult(
            success=False, stage="reload", error=err,
            rolled_back=rolled_back, backup_name=backup_name,
            config_hash=cfg_hash,
        )

    # 4. Health check — wait for service to stabilise, then verify active
    if health_check:
        await asyncio.sleep(3)
        if not _service_is_active():
            _log.warning("Health check failed: sing-box.service not active after restart")
            rolled_back = False
            if backup_name:
                rolled_back, _ = _do_rollback(backup_name)
            return DeployResult(
                success=False, stage="health",
                error="sing-box.service not active after restart",
                rolled_back=rolled_back, backup_name=backup_name,
                config_hash=cfg_hash,
            )

    _log.info("Deploy successful: node=%s backup=%s", node_tag, backup_name)
    return DeployResult(success=True, stage="ok", node_tag=node_tag,
                        backup_name=backup_name, config_hash=cfg_hash)


def list_backups() -> list[str]:
    ok, out = _run_helper("list-backups")
    if not ok:
        return []
    try:
        return json.loads(out)
    except Exception:
        return []


def restore_backup(name: str) -> tuple[bool, str]:
    return _run_helper("restore", name)


def get_current_config() -> Optional[dict]:
    """Read deployed config directly — readable at 0o644, no sudo needed."""
    try:
        with open("/etc/sing-box/config.json") as f:
            return json.load(f)
    except Exception:
        return None
