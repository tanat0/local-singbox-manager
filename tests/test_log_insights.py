from __future__ import annotations

from app.services.log_insights import summarize_problem_logs


def test_summarizes_hysteria2_connection_timeouts():
    text = "\n".join([
        (
            "2026-06-07T00:42:13+03:00 desperado sing-box[1705949]: +0300 "
            "2026-06-07 00:42:13 ERROR [55350367 4.5s] connection: open connection "
            "to 91.105.192.100:80 using outbound/hysteria2[hy kz]: "
            "timeout: no recent network activity"
        ),
        (
            "2026-06-07T00:42:14+03:00 desperado sing-box[1705949]: +0300 "
            "2026-06-07 00:42:14 ERROR [3864551622 4.5s] connection: open connection "
            "to 91.105.192.100:80 using outbound/hysteria2[hy kz]: "
            "timeout: no recent network activity"
        ),
    ])

    insights = summarize_problem_logs(text)

    assert len(insights) == 1
    assert insights[0].kind == "connection"
    assert insights[0].protocol == "hysteria2"
    assert insights[0].outbound_tag == "hy kz"
    assert insights[0].target == "91.105.192.100:80"
    assert insights[0].reason == "timeout: no recent network activity"
    assert insights[0].count == 2


def test_summarizes_dns_exchange_eof():
    text = (
        "2026-06-07T00:42:14+03:00 desperado sing-box[1705949]: +0300 "
        "2026-06-07 00:42:14 ERROR [322533843 125ms] dns: exchange failed "
        "for google.ru. IN A: read response: EOF"
    )

    insights = summarize_problem_logs(text)

    assert len(insights) == 1
    assert insights[0].kind == "dns"
    assert insights[0].target == "google.ru. IN A"
    assert insights[0].reason == "dns response EOF"


def test_ignores_unrecognized_lines():
    assert summarize_problem_logs("INFO outbound/vless[node]: connected") == []
