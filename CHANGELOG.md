# Changelog

All notable changes to Sing-Box Manager are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- User distribution hardening: selectable node assignments, config versions,
  deterministic fingerprints, refresh limits, delivery log visibility, and
  best-effort Telegram notifications when assigned configs change.
- Managed-user delivery can now attach generated sing-box JSON configs through
  Telegram while keeping raw proxy URLs as fallback.
- Managed-user delivery can now attach `.sbclient` bundles for the local
  `singbox-client` app through a separate `/sbclient` Telegram command, without
  adding a client sync API.
- Operator web download of generated sing-box JSON and `.sbclient` bundles from
  the Users page, using the same assignment and document builders as Telegram
  delivery.
- Local quality gates: check-only git hooks, `make check-fast`, `make check`,
  and `make doctor`.

### Changed
- Background health and Telegram polling can be disabled for tests with
  `BACKGROUND_TASKS_ENABLED=0`.
- Unit tests now use an isolated temp database by default instead of the local
  `singbox_manager.db`.
- README is now a short entrypoint; install, operations, architecture, and
  design notes live in focused `docs/` files.
- CI and local checks now run Ruff in check-only mode with basic bugbear and
  comprehension rules.
- Dependency metadata now lives in `pyproject.toml` with `uv.lock`; tracked
  requirements files are compatibility exports.
- VLESS URL `type` is now treated as a transport selector for generated
  sing-box configs instead of being copied into outbound `network`.

### Fixed
- Generated VLESS configs no longer pin `network=tcp` by default, avoiding
  TUN UDP rejection by TCP-only outbounds.
- Unsupported VLESS transports such as XHTTP/SplitHTTP now fail with a clear
  generator error instead of producing invalid sing-box JSON.
- Telegram managed-user commands keep raw URL fallback text visible when a
  generated JSON or `.sbclient` attachment cannot be prepared.

---

## [1.3.0] — 2026-05-18

### Added
- Node metadata and one-shot country lookup, including provider labels and notes.
- Dashboard quick switch, recent-problems log view, and log filters.
- Light / dark / system theme switcher.
- Telegram admin bot commands for status, node listing, activation, logs,
  health checks, and test notifications.
- User config distribution groundwork: config groups, managed Telegram users,
  `/config`, `/refresh`, `/status`, and delivery audit logs.
- Telegram diagnostics helper: `make telegram-check`.
- GitHub Actions non-e2e test workflow and MIT license.

### Changed
- Deploy pipeline now restarts sing-box for TUN configs, waits with retry/backoff,
  and reports filtered failure details.
- Generated sing-box configs default to `log.level: warn`.
- Application structure split into routes, services, repositories, typed config,
  system clients, and a Telegram package.
- systemd/sudoers install flow now renders user/path-specific files from templates.

### Fixed
- Hysteria2 percent-encoded passwords are decoded correctly.
- Deploy health failures no longer hide the relevant sing-box fatal/error line.

---

## [1.2.0] — 2026-05-13

### Added
- **Notifications** — fire-and-forget alerts to three independent channels:
  - `notify-send` — desktop popups, always attempted, no config required
  - **Telegram** — set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` env vars
  - **ntfy.sh** — set `NTFY_TOPIC`; `NTFY_SERVER` for self-hosted instances
- Notification events: deploy success/fail, rollback triggered/failed,
  health state transitions (connected ↔ degraded ↔ failed)
- Health-state change tracking in background loop — notifies only on actual
  transitions, no spam on every polling tick
- `POST /settings/notify-test` — send a test notification to all active channels
- Settings page **Notifications** card — shows channel status (available/inactive)
  and Test button
- 24 unit tests for all channels, priority mapping, and error resilience

---

## [1.1.0] — 2026-05-13

### Added
- **Profile system** — bundle a node + DNS preset + route preset into one click
  - `GET /profiles` — list and create profiles
  - `POST /profiles/{id}/activate` — full deploy pipeline, sets node active,
    updates Settings atomically
  - `POST /profiles/{id}/delete`
  - Soft node reference (no FK) — profiles survive node deletion
- Profile active state cleared automatically when:
  - A node is activated directly from the Nodes page
  - Settings are saved manually
- Dashboard **Active Node** card shows the active profile name and its presets
- Profiles page linked in nav
- Alembic migration `d4e9c1a2f7b3` — `profiles` table
- 18 unit tests (all CRUD paths, error cases, state transitions)
- 6 e2e tests (page loads, create, activate, dashboard card, delete, nav active state)

---

## [1.0.0] — 2026-05-12

### Added
- **Authentication** — optional single-admin password via env vars
  - `SINGLE_ADMIN_PASSWORD` — enables the login page; absent = open panel
    with a large warning banner (panel is not disabled, just unprotected)
  - `SESSION_SECRET` — signs session cookies with HMAC-SHA256; absent = ephemeral
    random key (sessions reset on restart)
  - Stateless signed session cookie — no server-side session store
  - CSRF protection via `Origin`/`Referer` header check (no body parsing needed)
  - Rate limiting — 5 failed attempts per IP per 60 s; cleanup at > 500 tracked IPs
  - `AuthMiddleware`: API routes → 401 JSON; page routes → redirect to `/login?next=`
  - HTMX requests intercepted in JS: 401 → redirect to login
  - `GET /login`, `POST /login`, `POST /logout`
- **Semantic versioning** — `app/version.py`, `VERSION = "1.0.0"`
- `GET /health` — `{"status":"ok","version":"..."}` (open, unauthenticated)
- `GET /version` — `{"app":"...","singbox":"..."}` (open, unauthenticated)
- `/api/sysinfo` partial — sing-box version shown in footer
- Security banner in nav when auth is disabled
- Logout button in nav when auth is enabled
- App version in footer
- 38 unit tests for auth (token roundtrip, expiry, rate limiting, CSRF,
  middleware, password verification)

---

## [0.5.0] — 2026-05-12 (pre-release)

### Added
- Structured logging via `app/logging_config.py` — INFO for operations,
  WARNING for degraded/failed conditions, no DEBUG spam
- Specific error messages for all failure cases (validator, deployer,
  helper-not-found, unknown-protocol)
- 46 new unit tests: `test_deployer.py` (19), `test_validator.py` (8),
  `test_registry.py` (19)
- 24 new e2e tests: API endpoints, nav active state, service actions,
  settings extras, diagnostics, export/import, backups

---

## [0.4.0] — 2026-05-11 (pre-release)

### Added
- Latency history charts (Chart.js) on Diagnostics page
- `/api/metrics/latency?hours=N` endpoint with hours clamping (1–168)
- Nav active state highlighting (CSS class on current link)
- Auto-dismiss flash alerts after 5 s
- 20 Playwright e2e smoke tests

---

## [0.3.0] — 2026-05-11 (pre-release)

### Added
- `bypass_ru` route preset — Russian IPs/domains go direct, rest through VPN;
  uses remote `.srs` rule-sets, no local geo database
- Health checks — service + TUN + DNS + TCP + HTTPS, background loop every 5 min
- Health check log stored in SQLite, 7-day retention
- External IP fallback chain (ipify / ifconfig.me / ipinfo.io)
- Diagnostics page with live health results and latency history
- `/api/sysinfo` endpoint

---

## [0.2.0] — 2026-05-10 (pre-release)

### Added
- Alembic migrations — `DeployLog` model, schema auto-migrated on startup
- Deploy locking — `asyncio.Lock()` prevents concurrent deploys
- Config hash — sha256 of canonical JSON; duplicate deploys detected
- IP provider fallback chain for external IP check

---

## [0.1.0] — 2026-05-10 (pre-release)

### Added
- Initial implementation
- FastAPI + Jinja2 + HTMX, SQLite via SQLAlchemy
- VLESS (Reality/TLS) and Hysteria2 URL parsers
- Deploy pipeline: validate → deploy → reload → health → rollback
- Privileged helper binary (`/usr/local/bin/singbox-manager-helper`)
- Config backups and one-click restore
- DNS presets: `quad9_tls`, `cloudflare_tls`, `google_tls`
- Route presets: `full_tunnel`, `bypass_lan`
- Dashboard, Nodes, Logs, Backups, Settings pages
