from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from app.services.desktop_apps import DesktopApp, is_valid_app_id
from app.services.settings import get_setting, set_setting

APP_BYPASS_SETTING_KEY = "app_bypass_json"
_MAX_ENTRIES = 200
_MAX_PROCESS_LEN = 120
_MAX_CUSTOM_LINES = 40


@dataclass(frozen=True)
class BypassEntry:
    app_id: str
    name: str
    process_name: str
    process_path: Optional[str]
    custom: bool = False


def load_bypass_entries(db: Session) -> list[BypassEntry]:
    raw = get_setting(db, APP_BYPASS_SETTING_KEY, "[]")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    entries: list[BypassEntry] = []
    for item in payload:
        entry = _entry_from_json(item)
        if entry is not None:
            entries.append(entry)
    return entries


def save_bypass_entries(db: Session, entries: Sequence[BypassEntry]) -> None:
    if len(entries) > _MAX_ENTRIES:
        raise ValueError(f"At most {_MAX_ENTRIES} bypass entries are allowed.")
    payload = [
        {
            "app_id": entry.app_id,
            "name": entry.name,
            "process_name": entry.process_name,
            "process_path": entry.process_path,
            "custom": entry.custom,
        }
        for entry in entries
    ]
    set_setting(db, APP_BYPASS_SETTING_KEY, json.dumps(payload, ensure_ascii=False))


def selected_app_ids(entries: Sequence[BypassEntry]) -> set[str]:
    return {entry.app_id for entry in entries if not entry.custom}


def custom_process_text(entries: Sequence[BypassEntry]) -> str:
    return "\n".join(entry.process_path or entry.process_name for entry in entries if entry.custom)


def process_bypass_for_config(db: Session) -> dict[str, list[str]]:
    names: list[str] = []
    paths: list[str] = []
    seen_names: set[str] = set()
    seen_paths: set[str] = set()
    for entry in load_bypass_entries(db):
        if entry.process_path:
            if entry.process_path not in seen_paths:
                paths.append(entry.process_path)
                seen_paths.add(entry.process_path)
            continue
        if entry.process_name and entry.process_name not in seen_names:
            names.append(entry.process_name)
            seen_names.add(entry.process_name)
    return {"process_name": names, "process_path": paths}


def build_entries_from_form(
    selected_ids: Sequence[str],
    process_overrides: dict[str, str],
    custom_text: str,
    *,
    apps: Sequence[DesktopApp],
) -> list[BypassEntry]:
    catalog = {app.app_id: app for app in apps}
    entries: list[BypassEntry] = []
    seen: set[str] = set()
    for app_id in selected_ids:
        if app_id in seen:
            continue
        app = catalog.get(app_id)
        if not is_valid_app_id(app_id) or app is None:
            raise ValueError("An application is no longer available. Reload the page before saving.")
        match = process_overrides.get(app_id, app.process_path or app.process_name)
        process_name, process_path = _parse_process_match(match)
        entries.append(
            BypassEntry(
                app_id=app.app_id,
                name=app.name,
                process_name=process_name,
                process_path=process_path,
            )
        )
        seen.add(app_id)

    custom_count = 0
    for line in custom_text.splitlines():
        if not line.strip():
            continue
        process_name, process_path = _parse_process_match(line)
        custom_id = f"custom:{process_path or process_name}"
        if custom_id in seen:
            continue
        custom_count += 1
        if custom_count > _MAX_CUSTOM_LINES:
            raise ValueError(f"At most {_MAX_CUSTOM_LINES} custom matches are allowed.")
        entries.append(
            BypassEntry(
                app_id=custom_id,
                name=process_name,
                process_name=process_name,
                process_path=process_path,
                custom=True,
            )
        )
        seen.add(custom_id)
    if len(entries) > _MAX_ENTRIES:
        raise ValueError(f"At most {_MAX_ENTRIES} bypass entries are allowed.")
    return entries


def _parse_process_match(value: str) -> tuple[str, Optional[str]]:
    match = value.strip()
    if not match or any(ord(ch) < 32 or ord(ch) == 127 for ch in match):
        raise ValueError("Selected applications need an exact process name or absolute executable path.")
    if match.startswith("/"):
        path = PurePosixPath(match)
        if len(match) > 240 or ".." in path.parts or not path.name or match.endswith("/"):
            raise ValueError("Invalid executable path.")
        return path.name, str(path)
    name = _clean_process(match)
    if not name:
        raise ValueError("Use an exact process name or an absolute executable path, without arguments.")
    return name, None


def _entry_from_json(item: Any) -> Optional[BypassEntry]:
    if not isinstance(item, dict):
        return None
    app_id = str(item.get("app_id") or "")
    raw_path = str(item.get("process_path") or "").strip()
    if raw_path and not raw_path.startswith("/"):
        return None
    try:
        process_name, process_path = _parse_process_match(raw_path or str(item.get("process_name") or ""))
    except ValueError:
        return None
    custom = bool(item.get("custom"))
    if custom:
        app_id = f"custom:{process_path or process_name}"
    elif not is_valid_app_id(app_id):
        return None
    name = str(item.get("name") or process_name).strip()[:80]
    return BypassEntry(
        app_id=app_id,
        name=name or process_name,
        process_name=process_name,
        process_path=process_path,
        custom=custom,
    )


def _clean_process(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or "/" in cleaned or any(ord(ch) < 32 or ord(ch) == 127 for ch in cleaned):
        return ""
    if len(cleaned) > _MAX_PROCESS_LEN:
        return ""
    if any(ch.isspace() for ch in cleaned):
        return ""
    return cleaned
