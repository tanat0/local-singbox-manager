from __future__ import annotations

from pathlib import Path

from app.db import SessionLocal
from app.parsers.vless import parse_vless
from app.services.app_bypass import (
    BypassEntry,
    build_entries_from_form,
    load_bypass_entries,
    process_bypass_for_config,
    save_bypass_entries,
)
from app.services.desktop_apps import list_desktop_apps
from app.singbox.generator import generate_config

VLESS_URL = (
    "vless://some-uuid@1.2.3.4:443"
    "?security=reality&sni=example.com&pbk=pubkey&sid=shortid&fp=chrome&type=tcp"
    "#test-node"
)


def test_form_keeps_process_path_when_name_unchanged(tmp_path: Path):
    apps_dir = tmp_path / "applications"
    apps_dir.mkdir()
    (apps_dir / "firefox.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Firefox\nExec=/usr/bin/firefox %u\n",
        encoding="utf-8",
    )
    apps = list_desktop_apps(extra_dirs={"usr": apps_dir})
    entries = build_entries_from_form(
        ["usr:firefox.desktop"],
        {"usr:firefox.desktop": "firefox"},
        "",
        apps=apps,
    )
    assert entries[0].process_path == "/usr/bin/firefox"
    assert entries[0].process_name == "firefox"


def test_form_override_drops_path(tmp_path: Path):
    apps_dir = tmp_path / "applications"
    apps_dir.mkdir()
    (apps_dir / "firefox.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Firefox\nExec=/usr/bin/firefox %u\n",
        encoding="utf-8",
    )
    apps = list_desktop_apps(extra_dirs={"usr": apps_dir})
    entries = build_entries_from_form(
        ["usr:firefox.desktop"],
        {"usr:firefox.desktop": "firefox-bin"},
        "custom-proc\n",
        apps=apps,
    )
    assert entries[0].process_path is None
    assert entries[0].process_name == "firefox-bin"
    assert entries[1].custom is True
    assert entries[1].process_name == "custom-proc"


def test_process_bypass_roundtrip_and_host_config():
    db = SessionLocal()
    try:
        save_bypass_entries(db, [
            BypassEntry("usr:firefox.desktop", "Firefox", "firefox", "/usr/bin/firefox"),
            BypassEntry("custom:steam", "steam", "steam", None, custom=True),
        ])
        loaded = load_bypass_entries(db)
        assert [entry.process_name for entry in loaded] == ["firefox", "steam"]
        bypass = process_bypass_for_config(db)
        assert bypass["process_path"] == ["/usr/bin/firefox"]
        assert bypass["process_name"] == ["steam"]
        cfg = generate_config(parse_vless(VLESS_URL), process_bypass=bypass)
        assert cfg["route"]["rules"][0] == {"process_path": ["/usr/bin/firefox"], "outbound": "direct"}
        assert cfg["route"]["rules"][1] == {"process_name": ["steam"], "outbound": "direct"}
        assert cfg["route"]["rules"][2] == {"port": 53, "action": "hijack-dns"}
    finally:
        db.close()
