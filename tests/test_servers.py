from __future__ import annotations

from unittest.mock import patch

from app.db import SessionLocal
from app.services.servers import _safe_error, _ssh_python, inventory, probe_server, save_notes
from app.system_clients import CommandResult


def test_inventory_includes_named_aliases():
    db = SessionLocal()
    try:
        aliases = [item.spec.alias for item in inventory(db)]
        assert aliases == ["hykz", "aeza", "swvps", "ge_vps"]
    finally:
        db.close()


def test_save_notes_ignores_unknown_aliases():
    db = SessionLocal()
    try:
        save_notes(db, {"hykz": "active hy2", "evil;rm": "nope"})
        notes = {item.spec.alias: item.notes for item in inventory(db)}
        assert notes["hykz"] == "active hy2"
        assert "evil;rm" not in notes
    finally:
        db.close()


def test_probe_parses_safe_json_and_redacts_errors():
    payload = (
        '{"hostname":"kz","units":["hysteria-server.service"],'
        '"listen":["udp *:443"],"hysteria":{"listen":":443","bandwidth_up":"100 mbps",'
        '"bandwidth_down":"100 mbps","has_auth":true,"password":"secret"},'
        '"nstat":{"UdpSndbufErrors":12},"journal_err_24h":"4"}'
    )
    with patch("app.services.servers._ssh_python", return_value=CommandResult(True, payload, 0)):
        snapshot = probe_server("hykz")
    assert snapshot.reachable is True
    assert snapshot.hostname == "kz"
    assert snapshot.hysteria["bandwidth_up"] == "100 mbps"
    assert "password" not in snapshot.hysteria
    assert snapshot.hysteria["has_auth"] is True
    assert snapshot.nstat["UdpSndbufErrors"] == 12


def test_probe_unknown_alias_is_rejected():
    snapshot = probe_server("not-a-host")
    assert snapshot.reachable is False
    assert snapshot.error == "Unknown SSH alias"


def test_probe_timeout_is_safe():
    with patch(
        "app.services.servers._ssh_python",
        return_value=CommandResult(False, "Connection to 1.2.3.4 port 22 timed out", 255),
    ):
        snapshot = probe_server("swvps")
    assert snapshot.reachable is False
    assert "timed out" in snapshot.error
    assert "1.2.3.4" not in snapshot.error


def test_ssh_requires_known_host_and_does_not_update_keys():
    with patch("app.services.servers.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "{}"
        assert _ssh_python("hykz", "print('{}')", 12).ok
    args = run.call_args.args[0]
    assert "StrictHostKeyChecking=yes" in args
    assert "UpdateHostKeys=no" in args
    assert "BatchMode=yes" in args
    assert "shell" not in run.call_args.kwargs


def test_unknown_ssh_error_does_not_echo_remote_output():
    assert _safe_error("banner token=abc vless://user:pass@example.com") == (
        "SSH probe failed. Check the alias and access in a terminal."
    )


def test_missing_journal_count_is_not_reported_as_zero():
    with patch("app.services.servers._ssh_python", return_value=CommandResult(True, "{}", 0)):
        assert probe_server("hykz").journal_err_24h is None
