from __future__ import annotations

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated  # type: ignore[assignment]

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories import NodeRepository
from app.routes.common import redirect
from app.services import nodes as node_service
from app.services.deploy import activate_node as activate_node_service
from app.services.nodes import NodeMetadataInput
from app.web import templates

router = APIRouter()


@router.get("/nodes", response_class=HTMLResponse)
async def nodes_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "nodes.html", {
        "nodes": node_service.list_nodes_for_dashboard(db),
        "latest_logs": node_service.latest_deploy_logs(db),
        "topology_role_choices": node_service.TOPOLOGY_ROLE_CHOICES,
        "msg": request.query_params.get("msg", ""),
        "msg_type": request.query_params.get("msg_type", "info"),
    })


@router.post("/nodes")
async def add_node(url: Annotated[str, Form()], db: Session = Depends(get_db)):
    return _nodes_redirect(await node_service.add_or_update_node(db, url))


@router.post("/nodes/{node_id}/delete")
async def delete_node(node_id: int, db: Session = Depends(get_db)):
    return _nodes_redirect(node_service.delete_node(db, node_id))


@router.post("/nodes/{node_id}/metadata")
async def update_node_metadata(
    node_id: int,
    country_code: Annotated[str, Form()] = "",
    country_name: Annotated[str, Form()] = "",
    provider_name: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    topology_role: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    data = NodeMetadataInput(
        country_code=country_code,
        country_name=country_name,
        provider_name=provider_name,
        notes=notes,
        topology_role=topology_role,
    )
    return _nodes_redirect(node_service.update_node_metadata(db, node_id, data))


@router.post("/nodes/{node_id}/refresh-geo")
async def refresh_node_geo(node_id: int, db: Session = Depends(get_db)):
    return _nodes_redirect(await node_service.refresh_geo_by_id(db, node_id))


@router.post("/nodes/{node_id}/activate")
async def activate_node(node_id: int, db: Session = Depends(get_db)):
    node = NodeRepository(db).get_by_id(node_id)
    if not node:
        return redirect("/nodes", msg="Node not found", msg_type="error")
    result = await activate_node_service(db, node)
    return redirect("/" if result.ok else "/nodes", msg=result.message, msg_type="success" if result.ok else "error")


@router.get("/api/nodes/export")
async def export_nodes(db: Session = Depends(get_db)):
    content = node_service.export_nodes_payload(db)
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=singbox-nodes.json"},
    )


@router.post("/api/nodes/import")
async def import_nodes(nodes_json: Annotated[str, Form()], db: Session = Depends(get_db)):
    return _nodes_redirect(await node_service.import_nodes_payload(db, nodes_json))


def _nodes_redirect(result: node_service.NodeMutationResult):
    return redirect("/nodes", msg=result.message, msg_type="success" if result.ok else "error")
