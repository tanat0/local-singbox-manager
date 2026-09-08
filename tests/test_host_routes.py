import asyncio
import threading
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app import auth
from app.db import SessionLocal
from app.main import app
from app.services.app_bypass import BypassEntry, load_bypass_entries, save_bypass_entries
from app.services.servers import DEFAULT_SERVERS, ServerSnapshot


def test_invalid_app_form_preserves_saved_matches():
    with SessionLocal() as db:
        save_bypass_entries(db, [BypassEntry("custom:keep", "keep", "keep", None, custom=True)])
    with patch.object(auth, "AUTH_ENABLED", False), TestClient(app) as client:
        response = client.post("/apps", data={"custom_processes": "invalid relative/path"})
        assert "without arguments" in response.text
    with SessionLocal() as db:
        assert [entry.process_name for entry in load_bypass_entries(db)] == ["keep"]


def test_missing_launcher_match_remains_visible():
    with SessionLocal() as db:
        save_bypass_entries(db, [BypassEntry("usr:removed.desktop", "Removed", "keep", "/opt/keep")])
    with patch.object(auth, "AUTH_ENABLED", False), TestClient(app) as client:
        with patch("app.routes.apps.list_desktop_apps", return_value=[]):
            response = client.get("/apps")
        assert "/opt/keep" in response.text


@pytest.mark.asyncio
async def test_slow_ssh_probe_does_not_block_health():
    started = threading.Event()
    release = threading.Event()

    def slow_probe(alias):
        started.set()
        release.wait(timeout=2)
        return ServerSnapshot(DEFAULT_SERVERS[0], reachable=True)

    with patch.object(auth, "AUTH_ENABLED", False), patch("app.routes.servers.probe_server", side_effect=slow_probe):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            probe = asyncio.create_task(client.post("/servers/hykz/probe"))
            try:
                loop = asyncio.get_running_loop()
                assert await asyncio.wait_for(loop.run_in_executor(None, started.wait, 1), timeout=1.5)
                health = await asyncio.wait_for(client.get("/health"), timeout=0.5)
                assert health.status_code == 200
            finally:
                release.set()
                response = await probe
            assert response.status_code == 200
            assert (await client.get("/servers/hykz/probe")).status_code == 405
