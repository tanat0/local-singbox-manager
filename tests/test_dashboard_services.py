from __future__ import annotations

from app.health import CheckResult, HealthReport
from app.services.dashboard import (
    render_external_ip,
    render_health_report,
    render_log_output,
    render_sysinfo,
)


def test_render_external_ip_escapes_error_text():
    html = render_external_ip(None, "<script>alert(1)</script>")

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_log_output_escapes_log_text():
    html = render_log_output("fatal <bad>")

    assert "<bad>" not in html
    assert "fatal &lt;bad&gt;" in html
    assert html.startswith('<pre class="log-output">')


def test_render_health_report_splits_system_and_connectivity_checks():
    report = HealthReport(
        overall="degraded",
        external_ip="1.2.3.4",
        checks=[
            CheckResult("Service", True, None, "active", category="system"),
            CheckResult("DNS", False, None, "timeout", category="connectivity"),
        ],
    )

    html = render_health_report(report)

    assert "badge-warning" in html
    assert "DEGRADED" in html
    assert "Service" in html
    assert "DNS" in html
    assert "check-ok" in html
    assert "check-fail" in html
    assert "1.2.3.4" in html


def test_render_sysinfo_handles_missing_version():
    html = render_sysinfo("")

    assert "unavailable" in html
    assert "sing-box" in html
