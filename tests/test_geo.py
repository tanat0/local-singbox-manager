from unittest.mock import patch

import httpx
import pytest

from app.geo import lookup_node_geo


@pytest.mark.asyncio
async def test_geo_lookup_failure_returns_empty():
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("no route")):
        info = await lookup_node_geo("1.2.3.4")
    assert info.country_code is None
    assert info.provider_suggestion is None
