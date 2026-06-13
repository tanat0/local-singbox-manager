from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.distribution import UserAssignment
from app.services.nodes import deserialize_node
from app.singbox.client_generator import generate_client_config
from app.singbox.generator import config_to_json

_FILENAME_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


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


def _client_config_filename(group_name: str, version: object) -> str:
    slug = _FILENAME_SAFE.sub("-", group_name.strip()).strip("-._").lower()
    return f"singbox-{slug or 'config'}-v{int(version or 1)}.json"
