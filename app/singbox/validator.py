from __future__ import annotations
import os
import json
import subprocess
import uuid as _uuid

SINGBOX_BIN = os.environ.get("SINGBOX_BIN", "/usr/bin/sing-box")


def validate_config(config: dict) -> tuple[bool, str]:
    tmppath = f"/tmp/singbox-check-{_uuid.uuid4()}.json"
    try:
        with open(tmppath, "w") as f:
            json.dump(config, f, indent=2)

        result = subprocess.run(
            [SINGBOX_BIN, "check", "-c", tmppath],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return True, "Config is valid"
        error = (result.stderr or result.stdout).strip()
        return False, error or "Unknown validation error"
    except subprocess.TimeoutExpired:
        return False, "sing-box check timed out after 15s"
    except FileNotFoundError:
        return False, f"sing-box binary not found at {SINGBOX_BIN}"
    except Exception as e:
        return False, str(e)
    finally:
        if os.path.exists(tmppath):
            os.unlink(tmppath)
