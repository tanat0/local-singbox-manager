from __future__ import annotations

from pathlib import Path

from app.services.desktop_apps import list_desktop_apps, parse_exec, resolve_icon_path


def test_parse_exec_strips_field_codes_and_keeps_absolute_path():
    name, path = parse_exec("/usr/bin/firefox %u")
    assert name == "firefox"
    assert path == "/usr/bin/firefox"


def test_parse_exec_skips_env_prefix():
    name, path = parse_exec("env FOO=1 /usr/bin/telegram-desktop -- %u")
    assert name == "telegram-desktop"
    assert path == "/usr/bin/telegram-desktop"


def test_parse_exec_flatpak_uses_app_id():
    name, path = parse_exec("/usr/bin/flatpak run --branch=stable org.mozilla.firefox")
    assert name == "org.mozilla.firefox"
    assert path is None


def test_list_desktop_apps_skips_nodisplay(tmp_path: Path):
    apps_dir = tmp_path / "applications"
    apps_dir.mkdir()
    (apps_dir / "visible.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Visible\nExec=/usr/bin/visible\nIcon=visible\n",
        encoding="utf-8",
    )
    (apps_dir / "hidden.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Hidden\nNoDisplay=true\nExec=/usr/bin/hidden\n",
        encoding="utf-8",
    )
    apps = list_desktop_apps(extra_dirs={"usr": apps_dir})
    assert [app.app_id for app in apps] == ["usr:visible.desktop"]
    assert apps[0].process_name == "visible"
    assert apps[0].process_path == "/usr/bin/visible"


def test_resolve_icon_from_pixmaps(tmp_path: Path):
    pixmaps = tmp_path / "pixmaps"
    pixmaps.mkdir()
    icon = pixmaps / "demo.png"
    icon.write_bytes(b"png")
    assert resolve_icon_path("demo", extra_roots=(pixmaps,)) == icon
