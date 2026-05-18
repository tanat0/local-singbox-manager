from __future__ import annotations

import json
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.auth import AUTH_ENABLED
from app.version import VERSION

BASE_DIR = Path(__file__).parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["fromjson"] = json.loads
templates.env.filters["tojson"] = json.dumps
templates.env.globals["auth_enabled"] = AUTH_ENABLED
templates.env.globals["app_version"] = VERSION
