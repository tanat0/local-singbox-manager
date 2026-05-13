"""
Playwright smoke tests — UI golden paths.

Coverage:
  - all main pages load (200, correct title)
  - add VLESS node
  - add Hysteria2 node
  - activate node (full deploy pipeline, mocked)
  - delete node
  - logs page loads log output
  - settings page shows preset selects
  - backups page renders
  - HTMX partials: /api/logs, /api/health, /api/diff return HTML
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
