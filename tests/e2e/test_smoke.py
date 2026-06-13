"""
Playwright smoke tests — UI golden paths.

Tests run sequentially against a single shared server + DB session.
State accumulated across tests (e.g. nodes added in test_add_vless_node
are present for test_activate_node). Restore-flow test is last because
it clears the active-node flag.

Coverage:
  Pages:       dashboard, nodes, diagnostics, logs, backups, settings, profiles
  Node CRUD:   add VLESS, add Hy2, activate, delete, re-add (update)
  Service:     restart, stop, start, validate-config
  Settings:    save, persist, bypass_ru preset available, restore defaults
  Diagnostics: hours selector, latency API clamping
  Profiles:    page loads, create, activate, delete
  Backups:     list, restore flow
  Import/Export: export JSON, round-trip import
  Nav:         active link highlighted on each page
  API partials: /api/logs, /api/health, /api/ip, /api/diff,
                /api/sysinfo, /api/metrics/latency
  Error cases: invalid URL, oversized lines param
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

VLESS_URL = (
    "vless://12345678-abcd-0000-0000-000000000001"
    "@1.2.3.4:443"
    "?security=reality&sni=example.com&pbk=fakepubkey&sid=aabbcc&fp=chrome&type=tcp"
    "#smoke-vless"
)
HY2_URL = "hysteria2://secret@5.5.5.5:8443?sni=hy2.example.com#smoke-hy2"


# ── Pages load ───────────────────────────────────────────────────────────────

def test_dashboard_title(page: Page, base_url: str):
    page.goto(base_url + "/")
    expect(page).to_have_title("Dashboard — Sing-Box Manager")


def test_dashboard_has_nav(page: Page, base_url: str):
    page.goto(base_url + "/")
    nav = page.locator("nav")
    for label in ("Dashboard", "Nodes", "Logs", "Backups", "Settings"):
        expect(nav.get_by_role("link", name=label, exact=True)).to_be_visible()


def test_nodes_page_loads(page: Page, base_url: str):
    page.goto(base_url + "/nodes")
    expect(page).to_have_title("Nodes — Sing-Box Manager")
    expect(page.locator("textarea[name='url']")).to_be_visible()


def test_logs_page_loads(page: Page, base_url: str):
    page.goto(base_url + "/logs")
    expect(page).to_have_title("Logs — Sing-Box Manager")


def test_backups_page_loads(page: Page, base_url: str):
    page.goto(base_url + "/backups")
    expect(page).to_have_title("Backups — Sing-Box Manager")


def test_settings_page_loads(page: Page, base_url: str):
    page.goto(base_url + "/settings")
    expect(page).to_have_title("Settings — Sing-Box Manager")
    expect(page.locator("select[name='dns_preset']")).to_be_visible()
    expect(page.locator("select[name='route_preset']")).to_be_visible()


def test_diagnostics_page_loads(page: Page, base_url: str):
    page.goto(base_url + "/diagnostics")
    expect(page).to_have_title("Diagnostics — Sing-Box Manager")


def test_users_route_preset_selector_visible(page: Page, base_url: str):
    page.goto(base_url + "/users")
    expect(page.locator("select[name='route_preset']").first).to_be_visible()


# ── Node management ──────────────────────────────────────────────────────────

def test_add_vless_node(page: Page, base_url: str):
    page.goto(base_url + "/nodes")
    page.fill("textarea[name='url']", VLESS_URL)
    page.click("button[type='submit']")
    # Check the node appears in the table
    expect(page.locator("tbody td strong", has_text="smoke-vless")).to_be_visible()
    expect(page.locator("tbody .badge-blue", has_text="vless")).to_be_visible()


def test_add_hy2_node(page: Page, base_url: str):
    page.goto(base_url + "/nodes")
    page.fill("textarea[name='url']", HY2_URL)
    page.click("button[type='submit']")
    expect(page.locator("tbody td strong", has_text="smoke-hy2")).to_be_visible()


def test_node_count_after_adding(page: Page, base_url: str):
    page.goto(base_url + "/nodes")
    rows = page.locator("tbody tr")
    assert rows.count() >= 2


def test_activate_node(page: Page, base_url: str):
    page.goto(base_url + "/nodes")
    # Click Activate on the first node that has an Activate button
    activate_btn = page.locator("button:has-text('Activate')").first
    activate_btn.click()
    # Redirect to dashboard — URL may include ?msg=... query params
    expect(page).to_have_url(re.compile(r".*/\?msg="))
    expect(page.locator(".alert-success")).to_be_visible()


def test_dashboard_shows_active_node(page: Page, base_url: str):
    page.goto(base_url + "/")
    # After activation, active node card should not show "No active node"
    active_card = page.locator(".card").filter(has_text="Active Node")
    expect(active_card.get_by_text("No active node.")).not_to_be_visible()


def test_delete_node(page: Page, base_url: str):
    page.goto(base_url + "/nodes")
    # Count rows before delete
    rows_before = page.locator("tbody tr").count()

    # Find a non-active node's delete button
    inactive_row = page.locator("tbody tr").filter(
        has=page.locator(".badge-gray")
    ).first
    delete_btn = inactive_row.locator("button:has-text('Delete')")

    # Accept the confirm() dialog
    page.on("dialog", lambda d: d.accept())
    delete_btn.click()

    expect(page.locator(".alert-success")).to_be_visible()
    rows_after = page.locator("tbody tr").count()
    assert rows_after == rows_before - 1


# ── Settings ─────────────────────────────────────────────────────────────────

def test_settings_save(page: Page, base_url: str):
    page.goto(base_url + "/settings")
    page.select_option("select[name='dns_preset']", "cloudflare_tls")
    page.select_option("select[name='route_preset']", "bypass_lan")
    page.click("button[type='submit']")
    expect(page.locator(".alert-success")).to_be_visible()


def test_settings_persisted(page: Page, base_url: str):
    page.goto(base_url + "/settings")
    assert page.input_value("select[name='dns_preset']") == "cloudflare_tls"
    assert page.input_value("select[name='route_preset']") == "bypass_lan"


# ── HTMX partial endpoints ───────────────────────────────────────────────────

def test_api_logs_partial(page: Page, base_url: str):
    response = page.request.get(base_url + "/api/logs?lines=10")
    assert response.status == 200
    assert "<pre" in response.text()


def test_api_diff_partial(page: Page, base_url: str):
    response = page.request.get(base_url + "/api/diff")
    assert response.status == 200


def test_api_health_partial(page: Page, base_url: str):
    response = page.request.get(base_url + "/api/health")
    assert response.status == 200
    assert "<table" in response.text()


def test_api_ip_partial(page: Page, base_url: str):
    response = page.request.get(base_url + "/api/ip")
    assert response.status == 200


# ── Add invalid URL — error shown ────────────────────────────────────────────

def test_add_invalid_url_shows_error(page: Page, base_url: str):
    page.goto(base_url + "/nodes")
    page.fill("textarea[name='url']", "not-a-valid-url")
    page.click("button[type='submit']")
    expect(page.locator(".alert-error")).to_be_visible()


# ── API: sysinfo and metrics ──────────────────────────────────────────────────

def test_api_sysinfo_returns_version(page: Page, base_url: str):
    response = page.request.get(base_url + "/api/sysinfo")
    assert response.status == 200
    assert "1.13.11" in response.text()


def test_api_metrics_latency_structure(page: Page, base_url: str):
    response = page.request.get(base_url + "/api/metrics/latency")
    assert response.status == 200
    data = response.json()
    assert "hours" in data
    assert "series" in data
    assert data["hours"] == 24
    assert isinstance(data["series"], list)


def test_api_metrics_hours_clamp_max(page: Page, base_url: str):
    response = page.request.get(base_url + "/api/metrics/latency?hours=9999")
    assert response.json()["hours"] == 168


def test_api_metrics_hours_clamp_min(page: Page, base_url: str):
    response = page.request.get(base_url + "/api/metrics/latency?hours=0")
    assert response.json()["hours"] == 1


def test_api_logs_line_clamp(page: Page, base_url: str):
    response = page.request.get(base_url + "/api/logs?lines=9999")
    assert response.status == 200
    assert "<pre" in response.text()


# ── Nav active state ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("path,label", [
    ("/",            "Dashboard"),
    ("/nodes",       "Nodes"),
    ("/profiles",    "Profiles"),
    ("/diagnostics", "Diagnostics"),
    ("/logs",        "Logs"),
    ("/backups",     "Backups"),
    ("/settings",    "Settings"),
])
def test_nav_active_link(page: Page, base_url: str, path: str, label: str):
    page.goto(base_url + path)
    active = page.locator("nav a.nav-active")
    expect(active).to_have_text(label)


# ── Service actions ───────────────────────────────────────────────────────────

def test_service_restart(page: Page, base_url: str):
    page.goto(base_url + "/")
    page.locator("form[action='/service/restart'] button").click()
    expect(page.locator(".alert-success")).to_be_visible()


def test_service_stop(page: Page, base_url: str):
    page.goto(base_url + "/")
    page.locator("form[action='/service/stop'] button").click()
    expect(page.locator(".alert-success")).to_be_visible()


def test_service_start(page: Page, base_url: str):
    page.goto(base_url + "/")
    page.locator("form[action='/service/start'] button").click()
    expect(page.locator(".alert-success")).to_be_visible()


def test_validate_config_success(page: Page, base_url: str):
    page.goto(base_url + "/")
    page.locator("form[action='/validate'] button").click()
    expect(page.locator(".alert-success")).to_be_visible()


# ── Settings extras ───────────────────────────────────────────────────────────

def test_settings_bypass_ru_option_available(page: Page, base_url: str):
    page.goto(base_url + "/settings")
    opts = page.locator("select[name='route_preset'] option")
    values = [opts.nth(i).get_attribute("value") for i in range(opts.count())]
    assert "bypass_ru" in values


def test_settings_restore_defaults(page: Page, base_url: str):
    page.goto(base_url + "/settings")
    page.select_option("select[name='dns_preset']", "quad9_tls")
    page.select_option("select[name='route_preset']", "full_tunnel")
    page.click("button[type='submit']")
    expect(page.locator(".alert-success")).to_be_visible()
    # Verify persisted
    page.goto(base_url + "/settings")
    assert page.input_value("select[name='dns_preset']") == "quad9_tls"
    assert page.input_value("select[name='route_preset']") == "full_tunnel"


# ── Diagnostics ───────────────────────────────────────────────────────────────

def test_diagnostics_hours_selector_visible(page: Page, base_url: str):
    page.goto(base_url + "/diagnostics")
    expect(page.locator("#hours-select")).to_be_visible()


def test_diagnostics_hours_selector_options(page: Page, base_url: str):
    page.goto(base_url + "/diagnostics")
    opts = page.locator("#hours-select option")
    values = [opts.nth(i).get_attribute("value") for i in range(opts.count())]
    assert "6" in values
    assert "24" in values
    assert "168" in values


# ── Export / Import ──────────────────────────────────────────────────────────

def test_export_nodes_returns_json_list(page: Page, base_url: str):
    response = page.request.get(base_url + "/api/nodes/export")
    assert response.status == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "raw_url" in data[0]
    assert "tag" in data[0]


def test_import_nodes_round_trip_no_duplicates(page: Page, base_url: str):
    export_resp = page.request.get(base_url + "/api/nodes/export")
    export_json = export_resp.text()
    before_count = len(export_resp.json())

    page.goto(base_url + "/nodes")
    page.fill("textarea[name='nodes_json']", export_json)
    page.locator("form[action='/api/nodes/import'] button[type='submit']").click()
    expect(page.locator(".alert")).to_be_visible()

    page.goto(base_url + "/nodes")
    assert page.locator("tbody tr").count() == before_count


def test_add_duplicate_node_shows_updated(page: Page, base_url: str):
    page.goto(base_url + "/nodes")
    page.fill("textarea[name='url']", HY2_URL)
    page.click("button[type='submit']")
    expect(page.locator(".alert-success")).to_be_visible()

    page.goto(base_url + "/nodes")
    page.fill("textarea[name='url']", HY2_URL)
    page.click("button[type='submit']")
    alert = page.locator(".alert-success")
    expect(alert).to_be_visible()
    assert "Updated" in alert.inner_text()


# ── Profiles ─────────────────────────────────────────────────────────────────

def test_profiles_page_loads(page: Page, base_url: str):
    page.goto(base_url + "/profiles")
    expect(page).to_have_title("Profiles — Sing-Box Manager")
    expect(page.locator("select[name='node_tag']")).to_be_visible()
    expect(page.locator("select[name='dns_preset']")).to_be_visible()
    expect(page.locator("select[name='route_preset']")).to_be_visible()


def test_profiles_create(page: Page, base_url: str):
    page.goto(base_url + "/profiles")
    page.fill("input[name='name']", "e2e-profile")
    page.fill("input[name='description']", "E2E test profile")
    # smoke-hy2 node is in the DB from earlier tests
    page.select_option("select[name='node_tag']", label="smoke-hy2 (hysteria2)")
    page.select_option("select[name='dns_preset']", "cloudflare_tls")
    page.select_option("select[name='route_preset']", "bypass_lan")
    page.click("button[type='submit']")
    # Profile should appear in the table
    expect(page.locator("td >> text=e2e-profile")).to_be_visible()


def test_profiles_activate(page: Page, base_url: str):
    page.goto(base_url + "/profiles")
    row = page.locator("tr", has=page.locator("td >> text=e2e-profile"))
    row.locator("button:has-text('Activate')").click()
    # Activate redirects to dashboard with success msg
    expect(page.locator(".alert-success")).to_be_visible()
    # Navigate back to profiles to verify active badge
    page.goto(base_url + "/profiles")
    row_after = page.locator("tr", has=page.locator("td >> text=e2e-profile"))
    expect(row_after.locator(".badge-green")).to_be_visible()


def test_profiles_active_shown_on_dashboard(page: Page, base_url: str):
    page.goto(base_url + "/")
    expect(page.locator("text=e2e-profile")).to_be_visible()


def test_profiles_delete(page: Page, base_url: str):
    page.goto(base_url + "/profiles")
    row = page.locator("tr", has=page.locator("td >> text=e2e-profile"))
    page.on("dialog", lambda d: d.accept())
    row.locator("button:has-text('Delete')").click()
    expect(page.locator(".alert-success")).to_be_visible()
    expect(page.locator("td >> text=e2e-profile")).not_to_be_visible()


# ── Backups (restore clears active node — keep last) ─────────────────────────

def test_backups_shows_mock_backup(page: Page, base_url: str):
    page.goto(base_url + "/backups")
    expect(page.get_by_text("config_20240101_120000.json")).to_be_visible()


def test_backup_restore_redirects_to_dashboard(page: Page, base_url: str):
    page.goto(base_url + "/backups")
    page.on("dialog", lambda d: d.accept())
    page.locator("button:has-text('Restore')").first.click()
    expect(page).to_have_url(re.compile(r".*/\?msg="))
    expect(page.locator(".alert-success")).to_be_visible()
