"""Tests for app/singbox/validator.py."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from app.singbox.validator import SINGBOX_BIN, validate_config


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_valid_config_returns_true():
    with patch("subprocess.run", return_value=_proc(0)):
        ok, msg = validate_config({"inbounds": []})
    assert ok is True
    assert "valid" in msg.lower()


def test_invalid_config_returns_stderr():
    with patch("subprocess.run", return_value=_proc(1, stderr="unknown field 'foo'")):
        ok, msg = validate_config({"bad": "config"})
    assert ok is False
    assert "foo" in msg


def test_invalid_config_falls_back_to_stdout():
    with patch("subprocess.run", return_value=_proc(1, stdout="syntax error", stderr="")):
        ok, msg = validate_config({})
    assert ok is False
    assert "syntax error" in msg


def test_timeout_returns_specific_message():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="sing-box", timeout=15)):
        ok, msg = validate_config({})
    assert ok is False
    assert "timed out" in msg.lower()
    assert "15s" in msg


def test_binary_not_found_mentions_path_and_env_var():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        ok, msg = validate_config({})
    assert ok is False
    assert SINGBOX_BIN in msg
    assert "SINGBOX_BIN" in msg


def test_unknown_exception_returned_as_string():
    with patch("subprocess.run", side_effect=OSError("disk full")):
        ok, msg = validate_config({})
    assert ok is False
    assert "disk full" in msg


def test_temp_file_cleaned_up_on_success(tmp_path):
    with patch("subprocess.run", return_value=_proc(0)):
        validate_config({"a": 1})
    # All /tmp/singbox-check-*.json files should be gone
    leftovers = list(tmp_path.glob("singbox-check-*.json"))
    assert leftovers == []


def test_temp_file_cleaned_up_on_failure():
    import glob
    with patch("subprocess.run", return_value=_proc(1, stderr="err")):
        validate_config({"a": 1})
    leftovers = glob.glob("/tmp/singbox-check-*.json")
    assert leftovers == []
