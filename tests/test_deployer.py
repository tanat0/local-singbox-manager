"""
Tests for app/singbox/deployer.py:
  - config_hash determinism and collision resistance
  - _extract_backup_name regex
  - deploy_with_rollback lock contention
  - _run_deploy stage failures and rollback logic
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from app.singbox.deployer import (
    DeployResult,
    _extract_backup_name,
    config_hash,
    deploy_with_rollback,
)


@pytest.fixture(autouse=True)
def quiet_notifications():
    with patch("app.singbox.deployer._notify", return_value=None):
        yield


# ── config_hash ───────────────────────────────────────────────────────────────

def test_config_hash_deterministic():
    cfg = {"b": 2, "a": 1}
    assert config_hash(cfg) == config_hash(cfg)


def test_config_hash_key_order_independent():
    assert config_hash({"a": 1, "b": 2}) == config_hash({"b": 2, "a": 1})


def test_config_hash_different_content():
    assert config_hash({"a": 1}) != config_hash({"a": 2})


def test_config_hash_nested():
    assert config_hash({"x": {"y": 3}}) == config_hash({"x": {"y": 3}})


def test_config_hash_returns_hex_string():
    h = config_hash({"k": "v"})
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ── _extract_backup_name ──────────────────────────────────────────────────────

def test_extract_backup_name_found():
    out = "Backup created: /etc/sing-box/backups/config_20240315_123456.json"
    assert _extract_backup_name(out) == "config_20240315_123456.json"


def test_extract_backup_name_not_found():
    assert _extract_backup_name("no backup here") is None


def test_extract_backup_name_at_start():
    assert _extract_backup_name("config_20240101_000000.json saved") == "config_20240101_000000.json"


def test_extract_backup_name_wrong_format():
    assert _extract_backup_name("config_backup.json") is None


# ── deploy_with_rollback lock contention ──────────────────────────────────────

@pytest.mark.asyncio
async def test_deploy_lock_contention():
    """When lock is already held, second call returns immediately with lock error."""
    lock_event = asyncio.Event()
    release_event = asyncio.Event()

    async def slow_validate(_config):
        lock_event.set()
        await release_event.wait()
        return True, "ok"

    with ExitStack() as stack:
        stack.enter_context(patch("app.singbox.deployer.validate_config",
                                  side_effect=lambda c: (True, "ok")))
        stack.enter_context(patch("app.singbox.deployer._run_helper",
                                  return_value=(True, "config_20240101_120000.json")))
        stack.enter_context(patch("app.singbox.deployer._service_is_active",
                                  return_value=True))

        # Hold the lock in a background task
        async def hold_lock():
            from app.singbox.deployer import _deploy_lock
            async with _deploy_lock:
                lock_event.set()
                await release_event.wait()

        holder = asyncio.create_task(hold_lock())
        await lock_event.wait()

        result = await deploy_with_rollback({"a": 1}, "test-node", health_check=False)
        release_event.set()
        await holder

    assert result.success is False
    assert result.stage == "lock"
    assert "in progress" in result.error


# ── _run_deploy stage failures ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deploy_validate_failure():
    with ExitStack() as stack:
        stack.enter_context(patch("app.singbox.deployer.validate_config",
                                  return_value=(False, "bad inbound type")))
        result = await deploy_with_rollback({"a": 1}, "node", health_check=False)

    assert result.success is False
    assert result.stage == "validate"
    assert "bad inbound type" in result.error


@pytest.mark.asyncio
async def test_deploy_helper_failure_no_rollback():
    with ExitStack() as stack:
        stack.enter_context(patch("app.singbox.deployer.validate_config",
                                  return_value=(True, "ok")))
        stack.enter_context(patch("app.singbox.deployer._run_helper",
                                  return_value=(False, "permission denied")))
        result = await deploy_with_rollback({"a": 1}, "node", health_check=False)

    assert result.success is False
    assert result.stage == "deploy"
    assert "permission denied" in result.error
    assert result.rolled_back is False


@pytest.mark.asyncio
async def test_deploy_restart_failure_triggers_rollback():
    call_count = {"n": 0}

    def helper_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if args[0] == "deploy":
            return True, "Backup: config_20240101_120000.json"
        if args[0] == "restart":
            return False, "unit failed"
        if args[0] == "restore":
            return True, "restored"
        return True, ""

    with ExitStack() as stack:
        stack.enter_context(patch("app.singbox.deployer.validate_config",
                                  return_value=(True, "ok")))
        stack.enter_context(patch("app.singbox.deployer._run_helper",
                                  side_effect=helper_side_effect))
        stack.enter_context(patch("app.singbox.service.get_failure_detail",
                                  return_value="FATAL TUNSETIFF busy"))
        result = await deploy_with_rollback({"a": 1}, "node", health_check=False)

    assert result.success is False
    assert result.stage == "restart"
    assert result.rolled_back is True
    assert result.backup_name == "config_20240101_120000.json"
    assert "TUNSETIFF" in result.error


@pytest.mark.asyncio
async def test_deploy_health_check_failure_triggers_rollback():
    def helper_side_effect(*args, **kwargs):
        if args[0] == "deploy":
            return True, "config_20240101_120000.json"
        if args[0] == "restart":
            return True, "ok"
        if args[0] == "restore":
            return True, "restored"
        return True, ""

    with ExitStack() as stack:
        stack.enter_context(patch("app.singbox.deployer.validate_config",
                                  return_value=(True, "ok")))
        stack.enter_context(patch("app.singbox.deployer._run_helper",
                                  side_effect=helper_side_effect))
        stack.enter_context(patch("app.singbox.deployer._service_is_active",
                                  return_value=False))
        stack.enter_context(patch("app.singbox.service.get_failure_detail",
                                  return_value="FATAL bad outbound"))
        stack.enter_context(patch("asyncio.sleep", return_value=None))
        result = await deploy_with_rollback({"a": 1}, "node", health_check=True)

    assert result.success is False
    assert result.stage == "health"
    assert result.rolled_back is True
    assert "bad outbound" in result.error


@pytest.mark.asyncio
async def test_deploy_success_no_health_check():
    def helper_side_effect(*args, **kwargs):
        if args[0] == "deploy":
            return True, "config_20240101_120000.json"
        return True, "ok"

    with ExitStack() as stack:
        stack.enter_context(patch("app.singbox.deployer.validate_config",
                                  return_value=(True, "ok")))
        stack.enter_context(patch("app.singbox.deployer._run_helper",
                                  side_effect=helper_side_effect))
        result = await deploy_with_rollback({"a": 1}, "my-node", health_check=False)

    assert result.success is True
    assert result.stage == "ok"
    assert result.node_tag == "my-node"
    assert result.backup_name == "config_20240101_120000.json"


@pytest.mark.asyncio
async def test_deploy_success_with_health_check():
    def helper_side_effect(*args, **kwargs):
        if args[0] == "deploy":
            return True, "config_20240101_120000.json"
        return True, "ok"

    with ExitStack() as stack:
        stack.enter_context(patch("app.singbox.deployer.validate_config",
                                  return_value=(True, "ok")))
        stack.enter_context(patch("app.singbox.deployer._run_helper",
                                  side_effect=helper_side_effect))
        stack.enter_context(patch("app.singbox.deployer._service_is_active",
                                  return_value=True))
        stack.enter_context(patch("asyncio.sleep", return_value=None))
        result = await deploy_with_rollback({"a": 1}, "my-node", health_check=True)

    assert result.success is True
    assert result.node_tag == "my-node"


# ── DeployResult.user_message ─────────────────────────────────────────────────

def test_user_message_success():
    r = DeployResult(success=True, stage="ok", node_tag="vless-1",
                     backup_name="config_20240101_120000.json")
    msg = r.user_message()
    assert "vless-1" in msg
    assert "config_20240101_120000.json" in msg


def test_user_message_failure_with_rollback():
    r = DeployResult(success=False, stage="health",
                     error="service not active", rolled_back=True)
    msg = r.user_message()
    assert "health" in msg
    assert "rolled back" in msg


def test_user_message_failure_without_rollback():
    r = DeployResult(success=False, stage="deploy",
                     error="permission denied", backup_name="config_x.json")
    msg = r.user_message()
    assert "deploy" in msg
    assert "config_x.json" in msg
