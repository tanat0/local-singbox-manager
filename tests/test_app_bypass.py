from __future__ import annotations

from pathlib import Path

import pytest

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
        {"usr:firefox.desktop": "/usr/bin/firefox"},
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


@pytest.mark.parametrize("match", ["relative/path", "bad name", "/tmp/../bin/tool", "bad\x00name", ""])
def test_invalid_match_is_rejected(match, tmp_path):
    desktop = tmp_path / "demo.desktop"
    desktop.write_text("[Desktop Entry]\nName=Demo\nExec=/usr/bin/demo\n")
    apps = list_desktop_apps(extra_dirs={"usr": tmp_path})
    with pytest.raises(ValueError):
        build_entries_from_form(["usr:demo.desktop"], {"usr:demo.desktop": match}, "", apps=apps)


def test_explicit_name_does_not_keep_inferred_path(tmp_path):
    (tmp_path / "demo.desktop").write_text("[Desktop Entry]\nName=Demo\nExec=/usr/bin/demo\n")
    apps = list_desktop_apps(extra_dirs={"usr": tmp_path})
    entries = build_entries_from_form(["usr:demo.desktop"], {"usr:demo.desktop": "demo"}, "", apps=apps)
    assert entries[0].process_name == "demo"
    assert entries[0].process_path is None


def test_custom_paths_roundtrip_without_broadening_to_name():
    db = SessionLocal()
    try:
        entries = build_entries_from_form([], {}, "/opt/My App/bin/browser\nhelper\nhelper", apps=[])
        save_bypass_entries(db, entries)
        assert len(load_bypass_entries(db)) == 2
        assert process_bypass_for_config(db) == {
            "process_path": ["/opt/My App/bin/browser"], "process_name": ["helper"],
        }
    finally:
        db.close()


def test_custom_limit_is_rejected_instead_of_truncated():
    with pytest.raises(ValueError, match="40"):
        build_entries_from_form([], {}, "\n".join(f"app-{i}" for i in range(41)), apps=[])


def test_unknown_app_is_rejected_instead_of_dropped():
    with pytest.raises(ValueError, match="no longer available"):
        build_entries_from_form(["usr:missing.desktop"], {}, "", apps=[])
