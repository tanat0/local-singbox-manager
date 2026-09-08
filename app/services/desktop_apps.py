from __future__ import annotations

import configparser
import re
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

_ID_RE = re.compile(r"^(usr|usr-local|home):[A-Za-z0-9_.+-]+\.desktop$")
_FIELD_CODES_RE = re.compile(r"%[a-zA-Z@]")
_ICON_SUFFIXES = frozenset({".png", ".svg", ".xpm", ".ico", ".webp"})
_LAUNCHERS = frozenset({"flatpak", "snap", "sh", "bash", "dash", "zsh"})

_SOURCE_DIRS = {
    "usr": Path("/usr/share/applications"),
    "usr-local": Path("/usr/local/share/applications"),
    "home": Path.home() / ".local/share/applications",
}

_ICON_ROOTS = (
    Path("/usr/share/icons/hicolor"),
    Path("/usr/local/share/icons/hicolor"),
    Path.home() / ".local/share/icons/hicolor",
    Path("/usr/share/pixmaps"),
    Path("/usr/local/share/pixmaps"),
    Path.home() / ".local/share/pixmaps",
)

_ICON_SIZES = (
    "256x256",
    "128x128",
    "64x64",
    "48x48",
    "32x32",
    "24x24",
    "scalable",
)


@dataclass(frozen=True)
class DesktopApp:
    app_id: str
    name: str
    desktop_path: Path
    icon_name: str
    icon_path: Optional[Path]
    process_name: str
    process_path: Optional[str]
    exec_line: str


def is_valid_app_id(app_id: str) -> bool:
    return bool(_ID_RE.fullmatch(app_id))


def source_dirs(home: Optional[Path] = None) -> dict[str, Path]:
    dirs = dict(_SOURCE_DIRS)
    if home is not None:
        dirs["home"] = home / ".local/share/applications"
    return dirs


def list_desktop_apps(
    *,
    home: Optional[Path] = None,
    extra_dirs: Optional[dict[str, Path]] = None,
) -> list[DesktopApp]:
    dirs = extra_dirs if extra_dirs is not None else source_dirs(home)
    apps: dict[str, DesktopApp] = {}
    for source, directory in dirs.items():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.desktop")):
            app = _parse_desktop_file(source, path)
            if app is None:
                continue
            apps[app.app_id] = app
    return sorted(apps.values(), key=lambda item: (item.name.lower(), item.app_id))


def get_desktop_app(app_id: str, *, home: Optional[Path] = None) -> Optional[DesktopApp]:
    if not is_valid_app_id(app_id):
        return None
    source, filename = app_id.split(":", 1)
    directory = source_dirs(home).get(source)
    if directory is None:
        return None
    path = directory / filename
    if path.parent != directory:
        return None
    return _parse_desktop_file(source, path)


def resolve_icon_path(icon: str, *, extra_roots: Sequence[Path] = ()) -> Optional[Path]:
    if not icon:
        return None
    candidate = Path(icon)
    if candidate.is_absolute():
        return candidate if _is_safe_icon_file(candidate) else None

    if "/" in icon or "\\" in icon or icon in {".", ".."}:
        return None

    stem = Path(icon).stem if Path(icon).suffix else icon
    roots = list(extra_roots) + list(_ICON_ROOTS)
    for root in roots:
        if not root.exists():
            continue
        if root.name == "pixmaps":
            for ext in (".png", ".svg", ".xpm"):
                path = root / f"{stem}{ext}"
                if _is_safe_icon_file(path, extra_roots=extra_roots):
                    return path
            continue
        for size in _ICON_SIZES:
            for ext in (".png", ".svg"):
                path = root / size / "apps" / f"{stem}{ext}"
                if _is_safe_icon_file(path, extra_roots=extra_roots):
                    return path
    return None


def parse_exec(exec_line: str) -> tuple[str, Optional[str]]:
    cleaned = _FIELD_CODES_RE.sub("", exec_line).strip()
    if not cleaned:
        return "", None
    try:
        tokens = shlex.split(cleaned, posix=True)
    except ValueError:
        return "", None
    if not tokens:
        return "", None

    index = 0
    if Path(tokens[0]).name == "env":
        index = 1
        while index < len(tokens) and "=" in tokens[index]:
            index += 1
    if index >= len(tokens):
        return "", None

    binary = tokens[index]
    if binary.startswith("-") or Path(binary).name in _LAUNCHERS or binary.lower().endswith(".appimage"):
        return "", None

    name = Path(binary).name
    path = binary if binary.startswith("/") else None
    return name, path


def _parse_desktop_file(source: str, path: Path) -> Optional[DesktopApp]:
    if not path.is_file() or path.suffix != ".desktop":
        return None
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except (OSError, configparser.Error, UnicodeDecodeError):
        return None
    if not parser.has_section("Desktop Entry"):
        return None
    entry = parser["Desktop Entry"]
    if entry.get("Type", "Application") != "Application":
        return None
    try:
        if entry.getboolean("NoDisplay", fallback=False) or entry.getboolean("Hidden", fallback=False):
            return None
    except ValueError:
        return None
    name = (entry.get("Name") or path.stem).strip()
    exec_line = (entry.get("Exec") or "").strip()
    process_name, process_path = parse_exec(exec_line)
    process_name, process_path = _resolve_process(process_name, process_path)
    icon_name = (entry.get("Icon") or "").strip()
    return DesktopApp(
        app_id=f"{source}:{path.name}",
        name=name,
        desktop_path=path,
        icon_name=icon_name,
        icon_path=resolve_icon_path(icon_name),
        process_name=process_name,
        process_path=process_path,
        exec_line=exec_line,
    )


def _resolve_process(name: str, path: Optional[str]) -> tuple[str, Optional[str]]:
    if not name:
        return "", None
    binary = path or shutil.which(name)
    if not binary:
        return name, path
    try:
        resolved = Path(binary).resolve(strict=True)
        with resolved.open("rb") as handle:
            # Launchers and scripts need an explicit match for the eventual socket owner.
            if handle.read(2) == b"#!":
                return "", None
    except (OSError, RuntimeError):
        return name, path
    return resolved.name, str(resolved)


def _is_safe_icon_file(path: Path, *, extra_roots: Sequence[Path] = ()) -> bool:
    try:
        resolved = path.resolve()
        if resolved.suffix.lower() not in _ICON_SUFFIXES or not resolved.is_file():
            return False
        if resolved.stat().st_size > 2 * 1024 * 1024:
            return False
    except (OSError, RuntimeError):
        return False
    allowed = (
        Path("/usr/share"),
        Path("/usr/local/share"),
        Path.home() / ".local" / "share",
        Path("/usr/share/pixmaps"),
    )
    return any(_is_relative_to(resolved, root.resolve()) for root in (*allowed, *extra_roots))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
