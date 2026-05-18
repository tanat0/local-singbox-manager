from __future__ import annotations

import json

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[assignment]

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DeployLog, Node, Profile
from app.parsers import parse_url
from app.routes.common import redirect
from app.services.nodes import deserialize_node, latest_deploy_logs, refresh_node_geo as refresh_geo
from app.services.settings import presets, singbox_log_level
from app.singbox.deployer import deploy_with_rollback
from app.singbox.generator import generate_config
from app.web import templates

router = APIRouter()


@router.get("/nodes", response_class=HTMLResponse)
async def nodes_page(request: Request, db: Session = Depends(get_db)):
    nodes = db.query(Node).order_by(Node.active.desc(), Node.created_at.desc()).all()
    return templates.TemplateResponse(request, "nodes.html", {
        "nodes": nodes,
        "latest_logs": latest_deploy_logs(db),
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@router.post("/nodes")
async def add_node(url: Annotated[str, Form()], db: Session = Depends(get_db)):
    try:
        parsed = parse_url(url)
    except Exception as e:
        return redirect("/nodes", msg=f"Parse error: {e}", msg_type="error")

    existing = db.query(Node).filter(Node.tag == parsed.tag).first()
    if existing:
        existing.raw_url = parsed.raw_url
        existing.protocol = parsed.protocol
        existing.parsed_json = json.dumps(parsed.to_dict())
        existing.schema_version = parsed.schema_version
        await refresh_geo(existing)
        db.commit()
        return redirect("/nodes", msg=f"Updated '{parsed.tag}'", msg_type="success")

    node = Node(
        tag=parsed.tag,
        protocol=parsed.protocol,
        raw_url=parsed.raw_url,
        parsed_json=json.dumps(parsed.to_dict()),
        schema_version=parsed.schema_version,
        active=False,
    )
    await refresh_geo(node)
    db.add(node)
    db.commit()
    return redirect("/nodes", msg=f"Added '{parsed.tag}'", msg_type="success")


@router.post("/nodes/{node_id}/delete")
async def delete_node(node_id: int, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        return redirect("/nodes", msg="Node not found", msg_type="error")
    was_active, tag = node.active, node.tag
    db.delete(node)
    db.commit()
    msg = f"Deleted '{tag}'"
    if was_active:
        msg += " (was active — sing-box still runs previous config)"
    return redirect("/nodes", msg=msg, msg_type="success")


@router.post("/nodes/{node_id}/metadata")
async def update_node_metadata(
    node_id: int,
    country_code: Annotated[str, Form()] = "",
    country_name: Annotated[str, Form()] = "",
    provider_name: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        return redirect("/nodes", msg="Node not found", msg_type="error")
    node.country_code = country_code.strip().upper()[:8] or None
    node.country_name = country_name.strip() or None
    node.provider_name = provider_name.strip() or None
    node.notes = notes.strip() or None
    db.commit()
    return redirect("/nodes", msg=f"Updated metadata for '{node.tag}'", msg_type="success")


@router.post("/nodes/{node_id}/refresh-geo")
async def refresh_node_geo(node_id: int, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        return redirect("/nodes", msg="Node not found", msg_type="error")
    await refresh_geo(node)
    db.commit()
    return redirect("/nodes", msg=f"Refreshed geo for '{node.tag}'", msg_type="success")


@router.post("/nodes/{node_id}/activate")
async def activate_node(node_id: int, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        return redirect("/nodes", msg="Node not found", msg_type="error")
    try:
        parsed = deserialize_node(node)
    except Exception as e:
        return redirect("/nodes", msg=f"Failed to load node: {e}", msg_type="error")
    try:
        dns_p, route_p = presets(db)
        config = generate_config(
            parsed,
            dns_preset=dns_p,
            route_preset=route_p,
            log_level=singbox_log_level(db),
        )
    except Exception as e:
        return redirect("/nodes", msg=f"Config generation failed: {e}", msg_type="error")

    result = await deploy_with_rollback(config, node.tag, health_check=True)

    db.add(DeployLog(
        node_tag=result.node_tag or node.tag,
        config_hash=result.config_hash,
        backup_name=result.backup_name,
        stage_reached=result.stage,
        success=result.success,
        rolled_back=result.rolled_back,
        error=result.error or None,
    ))

    if not result.success:
        db.commit()
        return redirect("/nodes", msg=result.user_message(), msg_type="error")

    db.query(Node).update({"active": False})
    node.active = True
    db.query(Profile).update({"active": False})
    db.commit()
    return redirect("/", msg=result.user_message(), msg_type="success")


@router.get("/api/nodes/export")
async def export_nodes(db: Session = Depends(get_db)):
    nodes = db.query(Node).all()
    data = [{
        "tag": n.tag,
        "protocol": n.protocol,
        "raw_url": n.raw_url,
        "parsed": json.loads(n.parsed_json),
        "schema_version": n.schema_version,
        "country_code": n.country_code,
        "country_name": n.country_name,
        "provider_name": n.provider_name,
        "provider_suggestion": n.provider_suggestion,
        "notes": n.notes,
    } for n in nodes]
    content = json.dumps(data, indent=2, ensure_ascii=False)
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=singbox-nodes.json"},
    )


@router.post("/api/nodes/import")
async def import_nodes(nodes_json: Annotated[str, Form()], db: Session = Depends(get_db)):
    try:
        data = json.loads(nodes_json)
        if not isinstance(data, list):
            raise ValueError("Expected a JSON array")
    except Exception as e:
        return redirect("/nodes", msg=f"Import error: {e}", msg_type="error")

    imported, errors = 0, []
    for item in data:
        raw_url = item.get("raw_url", "")
        if not raw_url:
            continue
        try:
            parsed = parse_url(raw_url)
            existing = db.query(Node).filter(Node.tag == parsed.tag).first()
            if existing:
                existing.raw_url = parsed.raw_url
                existing.protocol = parsed.protocol
                existing.parsed_json = json.dumps(parsed.to_dict())
                existing.schema_version = parsed.schema_version
                existing.country_code = item.get("country_code") or existing.country_code
                existing.country_name = item.get("country_name") or existing.country_name
                existing.provider_name = item.get("provider_name") or existing.provider_name
                existing.provider_suggestion = item.get("provider_suggestion") or existing.provider_suggestion
                existing.notes = item.get("notes") or existing.notes
            else:
                node = Node(
                    tag=parsed.tag,
                    protocol=parsed.protocol,
                    raw_url=parsed.raw_url,
                    parsed_json=json.dumps(parsed.to_dict()),
                    schema_version=parsed.schema_version,
                    active=False,
                    country_code=item.get("country_code") or None,
                    country_name=item.get("country_name") or None,
                    provider_name=item.get("provider_name") or None,
                    provider_suggestion=item.get("provider_suggestion") or None,
                    notes=item.get("notes") or None,
                )
                if not node.country_code and not node.country_name:
                    await refresh_geo(node)
                db.add(node)
            imported += 1
        except Exception as e:
            errors.append(f"{raw_url[:40]}: {e}")
    db.commit()
    msg = f"Imported {imported} nodes"
    if errors:
        msg += f". Skipped: {'; '.join(errors[:3])}"
    return redirect("/nodes", msg=msg, msg_type="success" if imported else "error")
