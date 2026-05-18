from sqlalchemy import Column, Float, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.db import Base


class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True, index=True)
    tag = Column(String, unique=True, index=True, nullable=False)
    protocol = Column(String, nullable=False)
    raw_url = Column(Text, nullable=False)
    # Stores JSON of ParsedNode subclass — NOT the generated sing-box outbound JSON.
    # Config is regenerated dynamically so it survives sing-box schema migrations.
    parsed_json = Column(Text, nullable=False)
    schema_version = Column(Integer, default=1, nullable=False)
    active = Column(Boolean, default=False, nullable=False)
    country_code = Column(String(8), nullable=True)
    country_name = Column(String, nullable=True)
    provider_name = Column(String, nullable=True)
    provider_suggestion = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Settings(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)


class HealthCheckLog(Base):
    __tablename__ = "health_check_log"

    id = Column(Integer, primary_key=True)
    checked_at = Column(DateTime, nullable=False, index=True)
    check_name = Column(String, nullable=False)
    category = Column(String, nullable=False, default="connectivity")
    ok = Column(Boolean, nullable=False)
    latency_ms = Column(Float(precision=2), nullable=True)
    detail = Column(Text, nullable=True)


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True, default="")
    # node_tag is a soft reference — no FK so profiles survive node deletion
    node_tag = Column(String, nullable=True)
    dns_preset = Column(String, nullable=False, default="quad9_tls")
    route_preset = Column(String, nullable=False, default="full_tunnel")
    active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DeployLog(Base):
    __tablename__ = "deploy_log"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    node_tag = Column(String, nullable=True)
    config_hash = Column(String(64), nullable=True)    # sha256 hex
    backup_name = Column(String, nullable=True)
    stage_reached = Column(String, nullable=False)     # validate|deploy|restart|health|ok
    success = Column(Boolean, nullable=False)
    rolled_back = Column(Boolean, default=False, nullable=False)
    error = Column(Text, nullable=True)
