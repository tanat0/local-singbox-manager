from __future__ import annotations

from app.services.users import decode_node_tags, encode_node_tags, parse_node_tags


def test_parse_node_tags_deduplicates_and_strips():
    assert parse_node_tags(" alpha, beta\nalpha ,, gamma ") == ["alpha", "beta", "gamma"]


def test_encode_decode_node_tags_roundtrip():
    raw = encode_node_tags(["node-a", "node-b"])
    assert decode_node_tags(raw) == ["node-a", "node-b"]


def test_decode_node_tags_handles_bad_json():
    assert decode_node_tags("not json") == []
