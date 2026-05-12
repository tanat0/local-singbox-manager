from __future__ import annotations
from typing import Any, Dict
from pydantic import BaseModel

SCHEMA_VERSION = 1


class ParsedNode(BaseModel):
    """
    Canonical in-DB representation of a proxy node.

    Rationale for NOT storing generated sing-box JSON:
    - sing-box schemas evolve; raw parsed fields outlive any one schema version
    - config can be regenerated without re-importing URLs
    - easier to validate, diff, and migrate
    """
    protocol: str
    raw_url: str
    tag: str
    server: str
    port: int
    schema_version: int = SCHEMA_VERSION
    extra_params: Dict[str, Any] = {}

    model_config = {"frozen": False}

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
