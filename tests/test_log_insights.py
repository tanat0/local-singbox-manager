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


def test_summarizes_connection_download_remote_dial_timeout():
    text = (
        "2026-06-30T06:07:04+03:00 desperado sing-box[353036]: +0300 "
        "2026-06-30 06:07:04 ERROR [1837328261 10.4s] connection: "
        "connection download closed: remote error: dial tcp4 31.209.137.10:61613: i/o timeout"
    )

    insights = summarize_problem_logs(text)

    assert len(insights) == 1
    assert insights[0].kind == "connection"
    assert insights[0].target == "31.209.137.10:61613"
    assert insights[0].reason == "remote dial timeout"


def test_summarizes_connection_upload_stream_canceled():
    text = "\n".join([
        (
            "2026-06-30T06:07:11+03:00 desperado sing-box[353036]: +0300 "
            "2026-06-30 06:07:11 ERROR [3510248298 607ms] connection: "
            "connection upload closed: stream 152844 canceled by remote with error code 0"
        ),
        (
            "2026-06-30T06:07:12+03:00 desperado sing-box[353036]: +0300 "
            "2026-06-30 06:07:12 ERROR [723609867 618ms] connection: "
            "connection upload closed: stream 152868 canceled by remote with error code 0"
        ),
    ])

    insights = summarize_problem_logs(text)

    assert len(insights) == 1
    assert insights[0].kind == "connection"
    assert insights[0].target is None
    assert insights[0].reason == "stream canceled by remote"
    assert insights[0].count == 2
    assert insights[0].last_seen == "2026-06-30T06:07:12+03:00"


def test_latest_timestamp_wins_for_duplicate_buckets():
    text = "\n".join([
        (
            "2026-06-30T06:07:14+03:00 host sing-box[1]: ERROR [1 1s] "
            "dns: exchange failed for google.com. IN A: read response: EOF"
        ),
        (
            "2026-06-30T06:07:10+03:00 host sing-box[1]: ERROR [2 1s] "
            "dns: exchange failed for google.com. IN A: read response: EOF"
        ),
    ])

    insights = summarize_problem_logs(text)

    assert insights[0].count == 2
    assert insights[0].last_seen == "2026-06-30T06:07:14+03:00"


def test_sorts_by_count_then_latest_timestamp():
    text = "\n".join([
        (
            "2026-06-30T06:07:10+03:00 host sing-box[1]: ERROR [1 1s] "
            "dns: exchange failed for a.example. IN A: read response: EOF"
        ),
        (
            "2026-06-30T06:07:12+03:00 host sing-box[1]: ERROR [2 1s] "
            "dns: exchange failed for b.example. IN A: read response: EOF"
        ),
        (
            "2026-06-30T06:07:13+03:00 host sing-box[1]: ERROR [3 1s] "
            "dns: exchange failed for b.example. IN A: read response: EOF"
        ),
        (
            "2026-06-30T06:07:20+03:00 host sing-box[1]: ERROR [4 1s] "
            "dns: exchange failed for c.example. IN A: read response: EOF"
        ),
    ])

    insights = summarize_problem_logs(text)

    assert [item.target for item in insights] == [
        "b.example. IN A",
        "c.example. IN A",
        "a.example. IN A",
    ]


def test_applies_limit_after_sorting():
    text = "\n".join(
        f"2026-06-30T06:07:{second:02d}+03:00 host sing-box[1]: ERROR [1 1s] "
        f"dns: exchange failed for host{second}.example. IN A: read response: EOF"
        for second in range(10)
    )

    insights = summarize_problem_logs(text, limit=3)

    assert [item.target for item in insights] == [
        "host9.example. IN A",
        "host8.example. IN A",
        "host7.example. IN A",
    ]


def test_ignores_unrecognized_lines():
    assert summarize_problem_logs("INFO outbound/vless[node]: connected") == []
