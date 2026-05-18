from __future__ import annotations

from types import SimpleNamespace

from app.services.distribution import UserAssignment, format_user_configs, format_user_status


def test_format_user_status_shows_assignment():
    assignment = UserAssignment(
        user=SimpleNamespace(telegram_id="123", display_name="Alex"),
        group=SimpleNamespace(name="family"),
        nodes=[SimpleNamespace(), SimpleNamespace()],
    )

    text = format_user_status(assignment)

    assert "Alex" in text
    assert "family" in text
    assert "2" in text


def test_format_user_configs_includes_raw_urls():
    assignment = UserAssignment(
        user=SimpleNamespace(telegram_id="123", display_name="Alex"),
        group=SimpleNamespace(name="family"),
        nodes=[
            SimpleNamespace(tag="node-a", protocol="vless", raw_url="vless://node-a"),
            SimpleNamespace(tag="node-b", protocol="hysteria2", raw_url="hysteria2://node-b"),
        ],
    )

    text = format_user_configs(assignment)

    assert "Config group: family" in text
    assert "vless://node-a" in text
    assert "hysteria2://node-b" in text


def test_format_user_configs_returns_error():
    assignment = UserAssignment(user=None, group=None, nodes=[], error="No config group assigned.")

    assert format_user_configs(assignment) == "No config group assigned."
