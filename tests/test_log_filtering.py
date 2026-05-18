from app.singbox.service import _filter_log_lines


def test_log_filter_problems_extracts_noisy_errors():
    text = "\n".join([
        "INFO inbound/tun[tun-in]: inbound connection to 1.1.1.1:443",
        "FATAL start service: open tun: TUNSETIFF: device or resource busy",
        "INFO outbound/vless[node]: outbound connection",
    ])
    filtered = _filter_log_lines(text, mode="problems")
    assert "TUNSETIFF" in filtered
    assert "outbound connection" not in filtered


def test_log_filter_grep_is_case_insensitive():
    text = "WARNING Hysteria obfs failed\nINFO ok"
    filtered = _filter_log_lines(text, mode="all", grep="hysteria")
    assert filtered == "WARNING Hysteria obfs failed"
