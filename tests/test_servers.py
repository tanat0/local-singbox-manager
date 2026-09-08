from __future__ import annotations

from unittest.mock import patch

from app.db import SessionLocal
from app.services.servers import inventory, probe_server, save_notes
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
    assert "<ip>" in snapshot.error
    assert "1.2.3.4" not in snapshot.error
