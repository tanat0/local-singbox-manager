from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.distribution import UserAssignment
from app.services.nodes import deserialize_node
from app.singbox.client_generator import generate_client_config
from app.singbox.dns import DEFAULT_DNS_PRESET
from app.singbox.generator import build_outbound, config_to_json

_FILENAME_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")
_MAX_SBCLIENT_PROFILE_NAME_LENGTH = 80


@dataclass(frozen=True)
class ClientConfigDocument:
    filename: str
    content: bytes
    mime_type: str
    caption: str


def build_client_config_document(assignment: UserAssignment) -> ClientConfigDocument:
    if assignment.error:
        raise ValueError(assignment.error)
    if not assignment.group:
        raise ValueError("No config group assigned")

    parsed_nodes = [deserialize_node(node) for node in assignment.nodes]
    config = generate_client_config(parsed_nodes, route_preset=assignment.route_preset)
    filename = _client_config_filename(assignment.group.name, assignment.config_version)
    caption = (
        f"sing-box config for {assignment.group.name} "
        f"v{assignment.config_version or 1} ({assignment.config_fingerprint[:12] or '-'})"
    )
    return ClientConfigDocument(
        filename=filename,
        content=config_to_json(config).encode("utf-8"),
        mime_type="application/json",
        caption=caption[:1024],
    )


def build_sbclient_bundle_document(assignment: UserAssignment) -> ClientConfigDocument:
    if assignment.error:
        raise ValueError(assignment.error)
    if not assignment.group:
        raise ValueError("No config group assigned")
    if not assignment.nodes:
        raise ValueError("No nodes assigned")

    profiles = _sbclient_profiles(assignment)
    bundle = {
        "schema_version": 1,
        "default_profile": profiles[0]["name"],
        "profiles": profiles,
    }
    filename = _sbclient_bundle_filename(assignment.group.name, assignment.config_version)
    caption = (
        f"singbox-client bundle for {assignment.group.name} "
        f"v{assignment.config_version or 1} ({assignment.config_fingerprint[:12] or '-'})"
    )
    return ClientConfigDocument(
        filename=filename,
        content=config_to_json(bundle).encode("utf-8"),
        mime_type="application/json",
        caption=caption[:1024],
    )


def _sbclient_profiles(assignment: UserAssignment) -> list[dict[str, str]]:
    profiles: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for node in sorted(assignment.nodes, key=lambda item: item.tag):
        build_outbound(deserialize_node(node))
        name = str(node.tag or "").strip()
        if not name:
            raise ValueError("Node tag is required for .sbclient profile name")
        if len(name) > _MAX_SBCLIENT_PROFILE_NAME_LENGTH:
            raise ValueError("Node tag is too long for .sbclient profile name")
        if name in seen_names:
            raise ValueError("Duplicate .sbclient profile name")
        seen_names.add(name)
        profiles.append({
            "name": name,
            "raw_url": node.raw_url,
            "dns_preset": DEFAULT_DNS_PRESET,
            "route_preset": assignment.route_preset,
        })
    return profiles


def _client_config_filename(group_name: str, version: object) -> str:
    slug = _FILENAME_SAFE.sub("-", group_name.strip()).strip("-._").lower()
    return f"singbox-{slug or 'config'}-v{int(version or 1)}.json"


def _sbclient_bundle_filename(group_name: str, version: object) -> str:
    slug = _FILENAME_SAFE.sub("-", group_name.strip()).strip("-._").lower()
    return f"singbox-client-{slug or 'config'}-v{int(version or 1)}.sbclient"
