from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.geo import lookup_node_geo
from app.models import DeployLog, Node
from app.parsers import Hysteria2Node, ParsedNode, VlessNode


def deserialize_node(node: Node) -> ParsedNode:
    data = json.loads(node.parsed_json)
    proto = data.get("protocol", "")
    if proto == "vless":
        return VlessNode.model_validate(data)
    if proto in ("hysteria2", "hy2"):
        return Hysteria2Node.model_validate(data)
    raise ValueError(
        f"Unknown protocol {proto!r} stored for node '{node.tag}' — "
        "delete and re-add this node from /nodes"
    )


async def refresh_node_geo(node: Node) -> None:
    parsed = json.loads(node.parsed_json)
    info = await lookup_node_geo(parsed.get("server", ""))
    if info.country_code:
        node.country_code = info.country_code
    if info.country_name:
        node.country_name = info.country_name
    if info.provider_suggestion:
        node.provider_suggestion = info.provider_suggestion


def latest_deploy_logs(db: Session) -> dict[str, DeployLog]:
    latest: dict[str, DeployLog] = {}
    rows = db.query(DeployLog).order_by(DeployLog.started_at.desc(), DeployLog.id.desc()).all()
    for row in rows:
        if row.node_tag and row.node_tag not in latest:
            latest[row.node_tag] = row
    return latest
