from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import unquote

from sqlalchemy.orm import Session

from app.geo import lookup_node_geo
from app.models import DeployLog, Node
from app.parsers import Hysteria2Node, ParsedNode, VlessNode, parse_url
from app.repositories import DeployLogRepository, NodeRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NodeMutationResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class NodeMetadataInput:
    country_code: str = ""
    country_name: str = ""
    provider_name: str = ""
    notes: str = ""


def deserialize_node(node: Node) -> ParsedNode:
    data = json.loads(node.parsed_json)
    proto = data.get("protocol", "")
    if proto == "vless":
        return VlessNode.model_validate(_normalize_vless_payload(node, data))
    if proto in ("hysteria2", "hy2"):
        return Hysteria2Node.model_validate(_normalize_hysteria2_payload(node, data))
    raise ValueError(
        f"Unknown protocol {proto!r} stored for node '{node.tag}' — "
        "delete and re-add this node from /nodes"
    )


def _normalize_vless_payload(node: Node, data: Dict[str, object]) -> Dict[str, object]:
    raw_url = str(getattr(node, "raw_url", "") or data.get("raw_url") or "")
    if raw_url:
        try:
            parsed = parse_url(raw_url)
        except Exception as exc:
            logger.debug(
                "Could not reparse stored VLESS raw URL for node '%s': %s",
                getattr(node, "tag", "<unknown>"),
                exc,
            )
        else:
            if isinstance(parsed, VlessNode):
                return parsed.to_dict()
    return data


def _normalize_hysteria2_payload(node: Node, data: Dict[str, object]) -> Dict[str, object]:
    raw_url = str(getattr(node, "raw_url", "") or data.get("raw_url") or "")
    if raw_url:
        try:
            parsed = parse_url(raw_url)
        except Exception as exc:
            logger.debug(
                "Could not reparse stored Hysteria2 raw URL for node '%s': %s",
                getattr(node, "tag", "<unknown>"),
                exc,
            )
        else:
            if isinstance(parsed, Hysteria2Node):
                return parsed.to_dict()

    normalized = dict(data)
    for field in ("auth", "obfs_password"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = unquote(value)
    return normalized


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
    return DeployLogRepository(db).latest_by_node_tag()


def list_nodes_for_dashboard(db: Session) -> List[Node]:
    return NodeRepository(db).list_for_dashboard()


def list_nodes_by_tag(db: Session) -> List[Node]:
    return NodeRepository(db).list_by_tag()


async def add_or_update_node(db: Session, url: str) -> NodeMutationResult:
    try:
        parsed = parse_url(url)
    except Exception as exc:
        return NodeMutationResult(False, f"Parse error: {exc}")

    repo = NodeRepository(db)
    existing = repo.get_by_tag(parsed.tag)
    if existing:
        existing.raw_url = parsed.raw_url
        existing.protocol = parsed.protocol
        existing.parsed_json = json.dumps(parsed.to_dict())
        existing.schema_version = parsed.schema_version
        await refresh_node_geo(existing)
        db.commit()
        return NodeMutationResult(True, f"Updated '{parsed.tag}'")

    node = Node(
        tag=parsed.tag,
        protocol=parsed.protocol,
        raw_url=parsed.raw_url,
        parsed_json=json.dumps(parsed.to_dict()),
        schema_version=parsed.schema_version,
        active=False,
    )
    await refresh_node_geo(node)
    db.add(node)
    db.commit()
    return NodeMutationResult(True, f"Added '{parsed.tag}'")


def delete_node(db: Session, node_id: int) -> NodeMutationResult:
    node = NodeRepository(db).get_by_id(node_id)
    if not node:
        return NodeMutationResult(False, "Node not found")

    was_active, tag = node.active, node.tag
    db.delete(node)
    db.commit()
    msg = f"Deleted '{tag}'"
    if was_active:
        msg += " (was active — sing-box still runs previous config)"
    return NodeMutationResult(True, msg)


def update_node_metadata(db: Session, node_id: int, data: NodeMetadataInput) -> NodeMutationResult:
    node = NodeRepository(db).get_by_id(node_id)
    if not node:
        return NodeMutationResult(False, "Node not found")

    node.country_code = data.country_code.strip().upper()[:8] or None
    node.country_name = data.country_name.strip() or None
    node.provider_name = data.provider_name.strip() or None
    node.notes = data.notes.strip() or None
    db.commit()
    return NodeMutationResult(True, f"Updated metadata for '{node.tag}'")


async def refresh_geo_by_id(db: Session, node_id: int) -> NodeMutationResult:
    node = NodeRepository(db).get_by_id(node_id)
    if not node:
        return NodeMutationResult(False, "Node not found")

    await refresh_node_geo(node)
    db.commit()
    return NodeMutationResult(True, f"Refreshed geo for '{node.tag}'")


def export_nodes_payload(db: Session) -> str:
    data = [_serialize_node(node) for node in NodeRepository(db).list_all()]
    return json.dumps(data, indent=2, ensure_ascii=False)


async def import_nodes_payload(db: Session, raw_json: str) -> NodeMutationResult:
    try:
        data = json.loads(raw_json)
        if not isinstance(data, list):
            raise ValueError("Expected a JSON array")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return NodeMutationResult(False, f"Import error: {exc}")

    imported = 0
    errors: List[str] = []
    repo = NodeRepository(db)
    for item in data:
        if not isinstance(item, dict):
            errors.append("non-object item")
            continue
        raw_url = str(item.get("raw_url") or "")
        if not raw_url:
            continue
        try:
            parsed = parse_url(raw_url)
            existing = repo.get_by_tag(parsed.tag)
            if existing:
                _apply_import_update(existing, parsed, item)
            else:
                node = _node_from_import(parsed, item)
                if not node.country_code and not node.country_name:
                    await refresh_node_geo(node)
                db.add(node)
            imported += 1
        except Exception as exc:
            errors.append(f"{raw_url[:40]}: {exc}")

    db.commit()
    msg = f"Imported {imported} nodes"
    if errors:
        msg += f". Skipped: {'; '.join(errors[:3])}"
    return NodeMutationResult(imported > 0, msg)


def _serialize_node(node: Node) -> Dict[str, object]:
    return {
        "tag": node.tag,
        "protocol": node.protocol,
        "raw_url": node.raw_url,
        "parsed": json.loads(node.parsed_json),
        "schema_version": node.schema_version,
        "country_code": node.country_code,
        "country_name": node.country_name,
        "provider_name": node.provider_name,
        "provider_suggestion": node.provider_suggestion,
        "notes": node.notes,
    }


def _apply_import_update(node: Node, parsed: ParsedNode, item: Dict[str, object]) -> None:
    node.raw_url = parsed.raw_url
    node.protocol = parsed.protocol
    node.parsed_json = json.dumps(parsed.to_dict())
    node.schema_version = parsed.schema_version
    node.country_code = _str_or_existing(item.get("country_code"), node.country_code)
    node.country_name = _str_or_existing(item.get("country_name"), node.country_name)
    node.provider_name = _str_or_existing(item.get("provider_name"), node.provider_name)
    node.provider_suggestion = _str_or_existing(item.get("provider_suggestion"), node.provider_suggestion)
    node.notes = _str_or_existing(item.get("notes"), node.notes)


def _node_from_import(parsed: ParsedNode, item: Dict[str, object]) -> Node:
    return Node(
        tag=parsed.tag,
        protocol=parsed.protocol,
        raw_url=parsed.raw_url,
        parsed_json=json.dumps(parsed.to_dict()),
        schema_version=parsed.schema_version,
        active=False,
        country_code=_str_or_none(item.get("country_code")),
        country_name=_str_or_none(item.get("country_name")),
        provider_name=_str_or_none(item.get("provider_name")),
        provider_suggestion=_str_or_none(item.get("provider_suggestion")),
        notes=_str_or_none(item.get("notes")),
    )


def _str_or_existing(value: object, existing: Optional[str]) -> Optional[str]:
    parsed = _str_or_none(value)
    return parsed or existing


def _str_or_none(value: object) -> Optional[str]:
    if value is None:
        return None
    parsed = str(value).strip()
    return parsed or None
