from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models import DeployLog, Node, Profile
from app.services.nodes import deserialize_node
from app.services.settings import presets, singbox_log_level
from app.singbox.deployer import DeployResult, deploy_with_rollback
from app.singbox.generator import generate_config


@dataclass
class ActivationResult:
    ok: bool
    message: str
    deploy_result: Optional[DeployResult] = None


async def activate_node(db: Session, node: Node, profile: Optional[Profile] = None) -> ActivationResult:
    try:
        parsed = deserialize_node(node)
    except Exception as e:
        return ActivationResult(False, f"Failed to load node: {e}")

    try:
        if profile:
            config = generate_config(
                parsed,
                dns_preset=profile.dns_preset,
                route_preset=profile.route_preset,
                log_level=singbox_log_level(db),
            )
        else:
            dns_p, route_p = presets(db)
            config = generate_config(
                parsed,
                dns_preset=dns_p,
                route_preset=route_p,
                log_level=singbox_log_level(db),
            )
    except Exception as e:
        return ActivationResult(False, f"Config generation failed: {e}")

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
        return ActivationResult(False, result.user_message(), result)

    db.query(Node).update({"active": False})
    node.active = True
    db.query(Profile).update({"active": False})
    if profile:
        profile.active = True
    db.commit()
    return ActivationResult(True, result.user_message(), result)
