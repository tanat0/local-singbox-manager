from __future__ import annotations

from pathlib import Path

import pytest

from app.services.desktop_apps import list_desktop_apps, parse_exec, resolve_icon_path


def test_parse_exec_strips_field_codes_and_keeps_absolute_path():
    name, path = parse_exec("/usr/bin/firefox %u")
    assert name == "firefox"
    assert path == "/usr/bin/firefox"


def test_parse_exec_skips_env_prefix():
    name, path = parse_exec("env FOO=1 /usr/bin/telegram-desktop -- %u")
    assert name == "telegram-desktop"
    assert path == "/usr/bin/telegram-desktop"


def test_parse_exec_flatpak_needs_explicit_process_match():
    name, path = parse_exec("/usr/bin/flatpak run --branch=stable org.mozilla.firefox")
    assert name == ""
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


@pytest.mark.parametrize("command", [
    'sh -c "exec browser"', '/opt/Browser.AppImage %U', 'env -u FOO browser', '"broken',
])
def test_ambiguous_launcher_has_no_guessed_match(command):
    assert parse_exec(command) == ("", None)


def test_absolute_env_launcher():
    assert parse_exec("/usr/bin/env FOO=1 /usr/bin/browser %U") == ("browser", "/usr/bin/browser")


def test_binary_symlinks_use_real_executable_path(tmp_path):
    binary = tmp_path / "browser-real"
    binary.write_bytes(b"\x7fELF")
    link = tmp_path / "browser"
    link.symlink_to(binary)
    (tmp_path / "browser.desktop").write_text(f"[Desktop Entry]\nName=Browser\nExec={link}\n")
    app = list_desktop_apps(extra_dirs={"usr": tmp_path})[0]
    assert app.process_name == "browser-real"
    assert app.process_path == str(binary)


def test_shell_script_launcher_is_visible_but_needs_match(tmp_path):
    script = tmp_path / "browser"
    script.write_text("#!/bin/sh\nexec /opt/browser-bin\n")
    (tmp_path / "browser.desktop").write_text(f"[Desktop Entry]\nName=Browser\nExec={script}\n")
    app = list_desktop_apps(extra_dirs={"usr": tmp_path})[0]
    assert app.name == "Browser"
    assert app.process_name == ""
    assert app.process_path is None


def test_malformed_boolean_does_not_break_catalog(tmp_path):
    (tmp_path / "bad.desktop").write_text("[Desktop Entry]\nName=Bad\nNoDisplay=maybe\nExec=bad\n")
    assert list_desktop_apps(extra_dirs={"usr": tmp_path}) == []


def test_icon_traversal_and_symlink_escape_are_rejected(tmp_path):
    pixmaps = tmp_path / "pixmaps"
    pixmaps.mkdir()
    private = tmp_path / "private.svg"
    private.write_text("private contents")
    (pixmaps / "leak.svg").symlink_to(private)
    assert resolve_icon_path("../private.svg", extra_roots=(pixmaps,)) is None
    assert resolve_icon_path("leak", extra_roots=(pixmaps,)) is None


def test_icon_cannot_serve_arbitrary_file_types(tmp_path):
    private = tmp_path / "private.db"
    private.write_bytes(b"database")
    assert resolve_icon_path(str(private), extra_roots=(tmp_path,)) is None
