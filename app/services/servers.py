from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.services.settings import get_setting, set_setting
from app.system_clients import CommandResult

SERVER_NOTES_SETTING_KEY = "server_notes_json"
_ALIAS_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_SSH_TIMEOUT = 12

_REMOTE_PROBE = r"""
import json, os, re, subprocess

def run(args):
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=5)
        return (proc.stdout or "").strip()
    except Exception:
        return ""

def units():
    text = run(["systemctl", "list-units", "--type=service", "--state=running", "--no-legend", "--no-pager"])
    names = []
    for line in text.splitlines():
        name = line.split()[0] if line.split() else ""
        if re.search(r"(sing-box|xray|x-ui|hysteria|3x-ui|fail2ban|docker)", name, re.I):
            names.append(name)
    return names[:20]

def listen():
    text = run(["ss", "-lntu"])
    rows = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 5:
            rows.append(parts[0] + " " + parts[4])
    return rows[:30]

def hysteria():
    path = "/etc/hysteria/config.yaml"
    if not os.path.isfile(path):
        return None
    try:
        raw = open(path, encoding="utf-8").read()
    except OSError:
        return None
    info = {}
    m = re.search(r"^listen:\s*(\S+)", raw, re.M)
    if m:
        info["listen"] = m.group(1)
    up = re.search(r"^\s+up:[ \t]*([0-9.]+[ \t]*[kKmMgGtT]?[bB](?:ps)?)[ \t]*(?:#.*)?$", raw, re.M)
    down = re.search(r"^\s+down:[ \t]*([0-9.]+[ \t]*[kKmMgGtT]?[bB](?:ps)?)[ \t]*(?:#.*)?$", raw, re.M)
    if up and down:
        info["bandwidth_up"] = up.group(1).strip()
        info["bandwidth_down"] = down.group(1).strip()
    info["ignore_client_bandwidth"] = bool(re.search(r"^ignoreClientBandwidth:\s*true", raw, re.M | re.I))
    info["has_obfs"] = bool(re.search(r"^obfs\s*:", raw, re.M))
    info["has_auth"] = bool(re.search(r"^auth\s*:", raw, re.M))
    return info

def nstat():
    text = run(["cat", "/proc/net/snmp"])
    out = {}
    lines = text.splitlines()
    for header, values in zip(lines[::2], lines[1::2]):
        names = header.split()
        numbers = values.split()
        for name, value in zip(names[1:], numbers[1:]):
            key = names[0].rstrip(":") + name
            if key in ("UdpInErrors", "UdpRcvbufErrors", "UdpSndbufErrors", "TcpRetransSegs"):
                out[key] = int(value)
    return out

mem_avail = ""
mem_total = ""
try:
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable:"):
            mem_avail = line.split()[1]
        elif line.startswith("MemTotal:"):
            mem_total = line.split()[1]
except OSError:
    pass

payload = {
    "hostname": run(["hostname"]),
    "uname": run(["uname", "-srm"]),
    "load": open("/proc/loadavg").read().split()[:3] if os.path.isfile("/proc/loadavg") else [],
    "uptime": run(["uptime", "-p"]) or run(["uptime"]),
    "mem_total_kb": mem_total,
    "mem_available_kb": mem_avail,
    "units": units(),
    "listen": listen(),
    "hysteria": hysteria(),
    "nstat": nstat(),
    "journal_err_24h": run(["bash", "-lc", "journalctl --since '24 hours ago' -p err --no-pager -q | wc -l"]),
}
print(json.dumps(payload, ensure_ascii=True))
"""


@dataclass(frozen=True)
class ServerSpec:
    alias: str
    label: str
    role: str
    kind: str
    location: str


DEFAULT_SERVERS: tuple[ServerSpec, ...] = (
    ServerSpec("hykz", "Kazakhstan Hysteria2", "exit", "hysteria2", "KZ"),
    ServerSpec("aeza", "Aeza 3x-ui relay", "entry_relay", "3x-ui", "RU"),
    ServerSpec("swvps", "Switzerland VLESS", "upstream_exit", "vless", "CH"),
    ServerSpec("ge_vps", "Germany VLESS", "upstream_exit", "vless", "DE"),
)

ALLOWED_ALIASES = frozenset(spec.alias for spec in DEFAULT_SERVERS)


@dataclass
class ServerSnapshot:
    spec: ServerSpec
    notes: str = ""
    reachable: Optional[bool] = None
    error: str = ""
    hostname: str = ""
    uname: str = ""
    load: list[str] = field(default_factory=list)
    uptime: str = ""
    mem_available_kb: str = ""
    mem_total_kb: str = ""
    units: list[str] = field(default_factory=list)
    listen: list[str] = field(default_factory=list)
    hysteria: Optional[dict] = None
    nstat: dict = field(default_factory=dict)
    journal_err_24h: Optional[int] = None


def inventory(db: Session) -> list[ServerSnapshot]:
    notes = _load_notes(db)
    return [ServerSnapshot(spec=spec, notes=notes.get(spec.alias, "")) for spec in DEFAULT_SERVERS]


def save_notes(db: Session, notes: dict[str, str]) -> None:
    cleaned = {
        alias: value.strip()[:500]
        for alias, value in notes.items()
        if alias in ALLOWED_ALIASES
    }
    set_setting(db, SERVER_NOTES_SETTING_KEY, json.dumps(cleaned, ensure_ascii=False))


def probe_server(alias: str) -> ServerSnapshot:
    spec = _spec_by_alias(alias)
    if spec is None:
        return ServerSnapshot(
            spec=ServerSpec(alias, alias, "unknown", "unknown", ""),
            reachable=False,
            error="Unknown SSH alias",
        )
    result = _ssh_python(spec.alias, _REMOTE_PROBE, timeout=_SSH_TIMEOUT)
    snapshot = ServerSnapshot(spec=spec)
    if not result.ok:
        snapshot.reachable = False
        snapshot.error = _safe_error(result.output or f"ssh failed ({result.returncode})")
        return snapshot
    try:
        payload = json.loads(result.output.splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        snapshot.reachable = False
        snapshot.error = "Probe returned non-JSON output"
        return snapshot
    if not isinstance(payload, dict):
        snapshot.reachable = False
        snapshot.error = "Probe payload was not an object"
        return snapshot
    snapshot.reachable = True
    snapshot.hostname = str(payload.get("hostname") or "")[:80]
    snapshot.uname = str(payload.get("uname") or "")[:80]
    snapshot.uptime = str(payload.get("uptime") or "")[:80]
    snapshot.mem_available_kb = str(payload.get("mem_available_kb") or "")[:16]
    snapshot.mem_total_kb = str(payload.get("mem_total_kb") or "")[:16]
    snapshot.load = [str(item)[:12] for item in _as_list(payload.get("load"))[:3]]
    snapshot.units = [str(item)[:80] for item in _as_list(payload.get("units"))[:20]]
    snapshot.listen = [str(item)[:80] for item in _as_list(payload.get("listen"))[:30]]
    snapshot.nstat = _safe_nstat(payload.get("nstat"))
    hysteria = payload.get("hysteria")
    snapshot.hysteria = _safe_hysteria(hysteria) if isinstance(hysteria, dict) else None
    try:
        snapshot.journal_err_24h = int(str(payload.get("journal_err_24h", "")).strip())
    except (TypeError, ValueError):
        snapshot.journal_err_24h = None
    return snapshot


def _ssh_python(alias: str, script: str, timeout: int) -> CommandResult:
    if not _ALIAS_RE.fullmatch(alias) or alias not in ALLOWED_ALIASES:
        return CommandResult(False, "invalid alias")
    try:
        proc = subprocess.run(
            [
                "ssh",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=8",
                "-o", "StrictHostKeyChecking=yes",
                "-o", "UpdateHostKeys=no",
                alias,
                "python3",
                "-u",
                "-",
            ],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (proc.stdout or "").strip()
        if proc.returncode != 0:
            err = (proc.stderr or output or "ssh failed").strip()
            return CommandResult(False, err, proc.returncode)
        return CommandResult(True, output, proc.returncode)
    except subprocess.TimeoutExpired:
        return CommandResult(False, f"SSH timed out after {timeout}s")
    except FileNotFoundError:
        return CommandResult(False, "Command not found: ssh")
    except OSError as exc:
        return CommandResult(False, str(exc))


def _spec_by_alias(alias: str) -> Optional[ServerSpec]:
    for spec in DEFAULT_SERVERS:
        if spec.alias == alias:
            return spec
    return None


def _load_notes(db: Session) -> dict[str, str]:
    raw = get_setting(db, SERVER_NOTES_SETTING_KEY, "{}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(alias): str(note)[:500]
        for alias, note in payload.items()
        if alias in ALLOWED_ALIASES
    }


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _safe_nstat(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    out = {}
    for key in ("UdpInErrors", "UdpRcvbufErrors", "UdpSndbufErrors", "TcpRetransSegs"):
        try:
            out[key] = int(value.get(key))
        except (TypeError, ValueError):
            continue
    return out


def _safe_hysteria(value: dict) -> dict:
    out = {}
    listen = str(value.get("listen", ""))
    if re.fullmatch(r"[0-9a-fA-F.:\[\]]{1,80}", listen):
        out["listen"] = listen
    for key in ("bandwidth_up", "bandwidth_down"):
        bandwidth = str(value.get(key, ""))
        if re.fullmatch(r"[0-9.]+\s*[kmgt]?b(?:ps)?", bandwidth, re.I):
            out[key] = bandwidth
    out["ignore_client_bandwidth"] = bool(value.get("ignore_client_bandwidth"))
    out["has_obfs"] = bool(value.get("has_obfs"))
    out["has_auth"] = bool(value.get("has_auth"))
    return out


def _safe_error(text: str) -> str:
    message = text.lower()
    if "host key verification failed" in message or "host identification has changed" in message:
        return "SSH host key verification failed. Check the alias in a terminal."
    if "permission denied" in message:
        return "SSH authentication failed. Check the key and remote user."
    if "timed out" in message:
        return "SSH connection or probe timed out."
    if "could not resolve hostname" in message:
        return "SSH hostname could not be resolved."
    if "connection refused" in message or "connection closed" in message:
        return "SSH connection refused or closed."
    return "SSH probe failed. Check the alias and access in a terminal."
