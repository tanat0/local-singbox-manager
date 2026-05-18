from __future__ import annotations
import os
import json
import uuid as _uuid

from app.config import settings
from app.logging_config import get_logger
from app.system_clients import SubprocessCommandRunner

SINGBOX_BIN = settings.system_paths.singbox_bin
_runner = SubprocessCommandRunner()
_log = get_logger(__name__)


def validate_config(config: dict) -> tuple[bool, str]:
    tmppath = f"/tmp/singbox-check-{_uuid.uuid4()}.json"
    try:
        with open(tmppath, "w") as f:
            json.dump(config, f, indent=2)

        result = _runner.run([SINGBOX_BIN, "check", "-c", tmppath], timeout=15)
        if result.ok:
            return True, "Config is valid"
        if result.output.startswith("Command not found"):
            return False, (
                f"sing-box binary not found at {SINGBOX_BIN} — "
                "install sing-box or set the SINGBOX_BIN env var to its path"
            )
        error = result.output.strip()
        return False, error or "Unknown validation error"
    except (OSError, ValueError, TypeError) as exc:
        _log.warning("sing-box config validation failed before check: %s", exc)
        return False, str(exc)
    finally:
        if os.path.exists(tmppath):
            os.unlink(tmppath)
