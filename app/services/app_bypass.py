from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from app.services.desktop_apps import DesktopApp, is_valid_app_id, list_desktop_apps
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
    limited = list(entries)[:_MAX_ENTRIES]
    payload = [
        {
            "app_id": entry.app_id,
            "name": entry.name,
            "process_name": entry.process_name,
            "process_path": entry.process_path,
            "custom": entry.custom,
        }
        for entry in limited
    ]
    set_setting(db, APP_BYPASS_SETTING_KEY, json.dumps(payload, ensure_ascii=False))


def selected_app_ids(entries: Sequence[BypassEntry]) -> set[str]:
    return {entry.app_id for entry in entries if not entry.custom}


def custom_process_text(entries: Sequence[BypassEntry]) -> str:
    return "\n".join(entry.process_name for entry in entries if entry.custom)


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
    apps: Optional[Sequence[DesktopApp]] = None,
) -> list[BypassEntry]:
    catalog = {app.app_id: app for app in (apps if apps is not None else list_desktop_apps())}
    entries: list[BypassEntry] = []
    seen: set[str] = set()
    for app_id in selected_ids:
        if app_id in seen or not is_valid_app_id(app_id):
            continue
        app = catalog.get(app_id)
        if app is None:
            continue
        override = _clean_process(process_overrides.get(app_id, ""))
        if override and override != app.process_name:
            process_name = override
            process_path = None
        else:
            process_name = app.process_name
            process_path = app.process_path
        entries.append(
            BypassEntry(
                app_id=app.app_id,
                name=app.name,
                process_name=process_name,
                process_path=process_path,
            )
        )
        seen.add(app_id)

    for line in custom_text.splitlines():
        process_name = _clean_process(line)
        if not process_name:
            continue
        custom_id = f"custom:{process_name}"
        if custom_id in seen:
            continue
        if len([entry for entry in entries if entry.custom]) >= _MAX_CUSTOM_LINES:
            break
        entries.append(
            BypassEntry(
                app_id=custom_id,
                name=process_name,
                process_name=process_name,
                process_path=None,
                custom=True,
            )
        )
        seen.add(custom_id)
    return entries


def _entry_from_json(item: Any) -> Optional[BypassEntry]:
    if not isinstance(item, dict):
        return None
    app_id = str(item.get("app_id") or "")
    process_name = _clean_process(str(item.get("process_name") or ""))
    if not process_name:
        return None
    custom = bool(item.get("custom"))
    if custom:
        app_id = f"custom:{process_name}"
    elif not is_valid_app_id(app_id):
        return None
    process_path = str(item.get("process_path") or "").strip() or None
    if process_path and (not process_path.startswith("/") or len(process_path) > 240):
        process_path = None
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
    if not cleaned or "/" in cleaned or "\x00" in cleaned:
        return ""
    if len(cleaned) > _MAX_PROCESS_LEN:
        return ""
    if any(ch.isspace() for ch in cleaned):
        return ""
    return cleaned
