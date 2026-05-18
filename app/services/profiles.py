from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Node, Profile
from app.repositories import NodeRepository, ProfileRepository
from app.services.deploy import activate_node as activate_node_service
from app.services.settings import set_setting
from app.singbox.dns import DNS_PRESETS
from app.singbox.routes import ROUTE_PRESETS


@dataclass(frozen=True)
class ProfileInput:
    name: str
    description: str = ""
    node_tag: str = ""
    dns_preset: str = "quad9_tls"
    route_preset: str = "full_tunnel"


@dataclass(frozen=True)
class ProfilePageData:
    profiles: List[Profile]
    nodes: List[Node]
    dns_preset: str
    route_preset: str


@dataclass(frozen=True)
class ProfileMutationResult:
    ok: bool
    message: str
    redirect_to: str = "/profiles"


def profiles_page_data(db: Session, dns_preset: str, route_preset: str) -> ProfilePageData:
    return ProfilePageData(
        profiles=ProfileRepository(db).list_all(),
        nodes=NodeRepository(db).list_by_tag(),
        dns_preset=dns_preset,
        route_preset=route_preset,
    )


def create_profile(db: Session, data: ProfileInput) -> ProfileMutationResult:
    repo = ProfileRepository(db)
    name = data.name.strip()
    if not name:
        return ProfileMutationResult(False, "Profile name is required")
    invalid = _validate_presets(data.dns_preset, data.route_preset)
    if invalid:
        return invalid
    if repo.get_by_name(name):
        return ProfileMutationResult(False, f"Profile '{name}' already exists")

    db.add(Profile(
        name=name,
        description=data.description.strip() or None,
        node_tag=data.node_tag.strip() or None,
        dns_preset=data.dns_preset,
        route_preset=data.route_preset,
        active=False,
    ))
    db.commit()
    return ProfileMutationResult(True, f"Created profile '{name}'")


async def activate_profile(db: Session, profile_id: int) -> ProfileMutationResult:
    profile = ProfileRepository(db).get_by_id(profile_id)
    if not profile:
        return ProfileMutationResult(False, "Profile not found")
    if not profile.node_tag:
        return ProfileMutationResult(False, f"Profile '{profile.name}' has no node — edit or delete it")

    node = NodeRepository(db).get_by_tag(profile.node_tag)
    if not node:
        return ProfileMutationResult(False, f"Node '{profile.node_tag}' no longer exists — update the profile")

    result = await activate_node_service(db, node, profile=profile)
    if not result.ok:
        return ProfileMutationResult(False, result.message)

    set_setting(db, "dns_preset", profile.dns_preset)
    set_setting(db, "route_preset", profile.route_preset)
    db.commit()
    return ProfileMutationResult(True, f"✓ Profile '{profile.name}' activated", redirect_to="/")


def delete_profile(db: Session, profile_id: int) -> ProfileMutationResult:
    profile = ProfileRepository(db).get_by_id(profile_id)
    if not profile:
        return ProfileMutationResult(False, "Profile not found")
    name = profile.name
    db.delete(profile)
    db.commit()
    return ProfileMutationResult(True, f"Deleted profile '{name}'")


def _validate_presets(dns_preset: str, route_preset: str) -> Optional[ProfileMutationResult]:
    if dns_preset not in DNS_PRESETS:
        return ProfileMutationResult(False, f"Invalid DNS preset: {dns_preset!r}")
    if route_preset not in ROUTE_PRESETS:
        return ProfileMutationResult(False, f"Invalid route preset: {route_preset!r}")
    return None
