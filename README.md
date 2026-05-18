# Sing-Box Manager

Local web UI for managing [sing-box](https://sing-box.sagernet.org/) on Manjaro/Arch Linux.

- Paste a proxy URL → parse → validate → deploy with auto-rollback
- **Profiles** — bundle node + DNS + route into one-click activate
- **Auth** — optional single-admin password with signed session cookies
- **Notifications** — desktop popups, Telegram, ntfy.sh on key events
- Dashboard: service status, quick node switch, external IP, config diff, recent problems
- Light / dark / system theme switcher
- DNS and route presets (Quad9/Cloudflare/Google DoT, full tunnel / bypass LAN / bypass RU)
- Node metadata: country lookup, provider label, notes
- Config backups and one-click restore
- Deploy journal — every attempt logged to DB
- Health monitoring — background checks every 5 min, latency history charts
- Binds to **127.0.0.1:9090 only** — no external exposure

**Supported protocols:** `vless://` (Reality / TLS), `hysteria2://`, `hy2://`

**Current version:** 1.2.0 · See [CHANGELOG.md](CHANGELOG.md) for history.

---

## Architecture

```
Browser (localhost only)
        │
        ▼
FastAPI app  127.0.0.1:9090
  │
  ├─ auth.py          HMAC-SHA256 signed session cookie, rate limiting, CSRF
  ├─ notify.py        fire-and-forget notifications (notify-send / Telegram / ntfy)
  ├─ version.py       VERSION constant
  │
  ├─ parsers/         URL → Pydantic model (VlessNode, Hysteria2Node)
  │                   stored as parsed_json in SQLite — NOT outbound JSON
  │                   config regenerated dynamically on each activate
  │
  ├─ singbox/
  │   ├─ generator    ParsedNode + DNS preset + route preset → config dict
  │   ├─ deployer     validate → deploy → restart → healthcheck → rollback
  │   │               asyncio.Lock prevents concurrent deploys
  │   ├─ service      start / stop / restart / reload / status / logs / version
  │   └─ validator    calls `sing-box check` on a temp file (no root)
  │
  ├─ health.py        async service + TUN + DNS + TCP + HTTPS checks,
  │                   external IP via fallback chain; runs every 5 min
  │
  ├─ logging_config.py  structured logging (INFO for operations,
  │                     WARNING for degraded/failed conditions, no DEBUG spam)
  │
  └─ models.py        Node, Settings, DeployLog, HealthCheckLog, Profile
                      (SQLite via SQLAlchemy; schema managed by Alembic,
                       auto-migrated on startup)

FastAPI → sudo helper (privileged boundary)
  /usr/local/bin/singbox-manager-helper
       │
       ├─ deploy <tmpfile>    backup current config, install new one
       ├─ restore <backup>    copy backup back to /etc/sing-box/config.json
       ├─ reload              systemctl reload sing-box.service
       ├─ restart / start / stop
       └─ list-backups        JSON list of backup filenames

/etc/sudoers.d/singbox-manager
  → allows only the helper binary, no shell, no other commands
```

---

## Prerequisites

- sing-box ≥ 1.13 at `/usr/bin/sing-box`, running as `sing-box.service`
- Python 3.8+ supported, 3.11 recommended (tested on 3.8.18 and 3.11)
- A user account that will run the web app (default: `nikita` — change in sudoers if different)

---

## Install

### 1. Clone and enter the directory

```bash
cd ~/path/to/local-singbox-manager
```

### 2. Create virtualenv and install dependencies

```bash
make install
```

For e2e tests, also install browser binaries (one-time):

```bash
.venv/bin/playwright install chromium
```

### 3. Install the privileged helper

The helper is the **only** binary that runs as root. It validates all inputs
and performs only whitelisted operations.

```bash
sudo cp scripts/singbox-manager-helper /usr/local/bin/singbox-manager-helper
sudo chmod 755 /usr/local/bin/singbox-manager-helper
sudo chown root:root /usr/local/bin/singbox-manager-helper
```

### 4. Configure sudoers

```bash
sudo cp sudoers.d/singbox-manager /etc/sudoers.d/singbox-manager
sudo chmod 440 /etc/sudoers.d/singbox-manager
sudo visudo -c        # must print "parsed OK" — do not skip this check
```

The rule allows your user to run the helper without a password prompt.
Edit `/etc/sudoers.d/singbox-manager` if your username is not `nikita`.

### 5. Ensure sing-box config directory and backup directory exist

```bash
sudo mkdir -p /etc/sing-box/backups
sudo chown root:root /etc/sing-box
# config.json itself is created on first deploy
```

### 6. Configure environment (optional but recommended)

Create a `.env` file or set these in your systemd unit / shell:

```bash
# Auth — panel is open to anyone on localhost if this is not set
SINGLE_ADMIN_PASSWORD=your-strong-password

# Signs session cookies — generate once and keep. If unset, sessions reset on restart.
SESSION_SECRET=64-char-hex-string   # openssl rand -hex 32

# Notifications (all optional — leave unset to disable a channel)
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=your-chat-id
NTFY_TOPIC=singbox-alerts           # uses ntfy.sh by default
NTFY_SERVER=https://ntfy.myserver.com   # for self-hosted ntfy (optional)

# Tuning
HEALTH_CHECK_INTERVAL=300    # seconds between background health checks (default 300)
SINGBOX_BIN=/usr/bin/sing-box
HELPER_BIN=/usr/local/bin/singbox-manager-helper
```

### 7. Run

```bash
make run
```

Virtualenv activation is not required for normal local use: `make run`
calls `.venv/bin/uvicorn` directly and loads `.env` when present, so it works
the same in every new terminal.

Open **http://127.0.0.1:9090**

The app runs Alembic migrations automatically on startup — the SQLite database
(`singbox_manager.db`) is created on first run.

---

## Run as a systemd service

One-shot install from a normal terminal:

```bash
bash scripts/install-systemd.sh
```

Manual equivalent:

```bash
# Review WorkingDirectory, ExecStart, and EnvironmentFile lines in the unit file first
make install
sudo install -o root -g root -m 755 scripts/singbox-manager-helper /usr/local/bin/singbox-manager-helper
sudo install -o root -g root -m 440 sudoers.d/singbox-manager /etc/sudoers.d/singbox-manager
sudo visudo -c
sudo mkdir -p /etc/sing-box/backups
sudo cp singbox-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now singbox-manager.service
sudo systemctl status singbox-manager.service
```

The service reads environment variables from the project `.env` file via
`EnvironmentFile=-/home/nikita/Documents/projects/own/local-singbox-manager/.env`.
After changing `.env`, restart the service:

```bash
sudo systemctl restart singbox-manager.service
```

---

## Upgrade flow

### From any previous version with Alembic

```bash
git pull
make install   # picks up any new deps
# migrations run automatically on next app start
```

### From v1 (before Alembic / before parsed_json)

The v1 schema stored `outbound_json` (generated sing-box JSON). v2 stores
`parsed_json` (raw parsed fields) and regenerates config dynamically.

These schemas are incompatible. Before deleting the database, export your nodes
if the old UI is still accessible:

```bash
curl http://127.0.0.1:9090/api/nodes/export > nodes_backup.json
```

Then delete the database and restart:

```bash
rm singbox_manager.db
```

After starting with the new schema, re-import from the **Nodes** page
(paste the exported JSON into the import form).
Alembic will create a fresh database with the v2 schema on next startup.

---

## Usage

### Adding a node

1. Open **http://127.0.0.1:9090/nodes**
2. Paste a proxy URL:
   ```
   vless://UUID@HOST:PORT?security=reality&sni=SNI&pbk=PUBKEY&sid=SHORTID&fp=chrome&type=tcp#mynode
   hysteria2://PASSWORD@HOST:PORT?sni=SNI#mynode
   ```
3. Click **Add / Update Node** — the node is parsed and stored; sing-box is not touched yet.

### Activating a node (deploy pipeline)

Click **Activate** on any node. The pipeline runs:

```
1. validate     sing-box check on a temp file (no root, read-only)
2. deploy       helper: backup current config → install new config
3. restart      systemctl restart sing-box.service
4. health       retry/backoff → systemctl is-active sing-box.service
                (lightweight check — not the full diagnostics suite)
5. ok           mark node active in DB, log to DeployLog

on any failure after step 2:
   auto-rollback: helper restore <backup> → restart service
```

A notification is sent on success, on each failure stage, and on rollback.

`reload` is intentionally not used for deploys: TUN configs can fail on reload
with `TUNSETIFF: device or resource busy` while the old interface is still open.

### Profiles

A profile bundles a **node + DNS preset + route preset** into one click.

1. Open **Profiles**, fill in a name and pick a node + presets → **Create Profile**
2. Click **Activate** on a profile — runs the full deploy pipeline and updates
   Settings atomically. No separate steps needed.
3. Switching nodes directly (via Nodes page) or saving Settings manually
   clears the active profile flag — the UI always reflects real state.

Profiles survive node deletion (soft reference, no FK constraint).

### DNS and route presets

Go to **Settings** to choose:

| Preset | DNS | Description |
|--------|-----|-------------|
| `quad9_tls` | 9.9.9.9:853 (DoT) | Default. Blocks malware domains |
| `cloudflare_tls` | 1.1.1.1:853 (DoT) | Fast global resolver |
| `google_tls` | 8.8.8.8:853 (DoT) | Google Public DNS |

| Preset | Route | Description |
|--------|-------|-------------|
| `full_tunnel` | All traffic through VPN | Default |
| `bypass_lan` | RFC1918 addresses go direct | Split tunnel for local network |
| `bypass_ru` | Russian IPs/domains go direct | Route RU traffic locally, rest through VPN |

The `bypass_ru` preset downloads remote `.srs` rule-sets from SagerNet's CDN
(`geoip-ru.srs`, `geosite-ru.srs`). sing-box fetches them automatically on
startup and refreshes every 7 days. No local geo database needed.

Changes take effect on the next **Activate** (or via a Profile).

### sing-box log level

Generated configs use `warn` by default to avoid journald being flooded by
per-connection TUN logs. Change **Settings → sing-box Log Level** to `info` or
`debug` only when diagnosing a problem, then re-activate a node.

The **Logs** page supports `All`, `Warnings/Errors`, `Fatal/Error`, and text
grep filters. Dashboard shows only recent problems.

### Node metadata

Nodes can store country, provider, and notes. Country is looked up once when a
node is added or when **Refresh Geo** is clicked. Provider is manual; automatic
ASN/org data is shown only as a suggestion because provider display names often
differ from registry names.

### Config diff

The dashboard shows a unified diff between the currently deployed
`/etc/sing-box/config.json` and the config that would be generated from the
active node + current presets. Useful to verify what will change before
re-activating.

### Manual rollback

Open **Backups**, find the snapshot you want, click **Restore**. The helper
copies the backup back and restarts sing-box. The active node flag is cleared
in the DB (since the DB is now out of sync with the deployed config).

### Import / Export nodes

- **Export**: Downloads all nodes as JSON (`/api/nodes/export`).
- **Import**: Paste exported JSON into the import form on the Nodes page.
  Nodes are re-parsed from `raw_url`, so they always use the latest parser.

---

## Authentication

Auth is **optional**. The panel is open to any user on localhost if
`SINGLE_ADMIN_PASSWORD` is not set — a large warning banner will be shown.

> **Important:** do not expose the panel through a reverse proxy without setting
> a password first. The `127.0.0.1`-only bind protects against remote access,
> but a reverse proxy removes that protection.

| Env var | Description |
|---------|-------------|
| `SINGLE_ADMIN_PASSWORD` | Enables the login page. Must be set to protect the panel. |
| `SESSION_SECRET` | Signs session cookies with HMAC-SHA256. Generate once and keep. If unset, an ephemeral random key is used — sessions are invalidated on every restart. |

Sessions are stateless signed cookies (no server-side store). They expire after 30 days.

CSRF protection is via `Origin`/`Referer` header validation — no body parsing needed.

API routes (`/api/*`) return `401 JSON` when unauthenticated. Page routes redirect
to `/login?next=<path>`. HTMX requests detect 401 in JS and redirect accordingly.

Rate limiting: 5 failed login attempts per IP per 60 seconds, then locked out.

The `/health` and `/version` endpoints are always open (used for monitoring).

---

## Notifications

Three channels, all **best-effort and fire-and-forget** — a failing notification
channel never blocks the request path.

| Channel | Config | Notes |
|---------|--------|-------|
| `notify-send` | None — always attempted (best effort) | Requires a desktop session with DBUS; silently skipped if unavailable or running headless |
| Telegram | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Messages sent with `parse_mode=HTML` |
| ntfy.sh | `NTFY_TOPIC` (+ `NTFY_SERVER` for self-hosted) | Priority: default / high / urgent |

**Events:**

| Event | Level | Example message |
|-------|-------|-----------------|
| Deploy success | info | ✓ Tunnel active — Node: `my-server` |
| Deploy fail | critical | ✗ Deploy failed — Stage: health — service not active |
| Rollback triggered | warning | ↩ Rolled back — Restored `config_20260513_120000.json` |
| Rollback failed | critical | ⚠ Rollback FAILED — Manual recovery needed |
| Tunnel degraded | warning | ⚠ Tunnel degraded — Failing: DNS (google.com), TCP 1.1.1.1:80 |
| Tunnel recovered | info | ✓ Tunnel recovered — All health checks passing |
| Tunnel failed | critical | ✗ Tunnel failed — All connectivity checks failing |

Health-state notifications fire only on **state transitions** — not every
background polling tick.

Use **Settings → Notifications → Send Test Notification** to verify your channels.

---

## Health monitoring

A background task runs every 5 minutes (configurable via `HEALTH_CHECK_INTERVAL` env var)
and stores results in the `health_check_log` table. Data is retained for 7 days.

Checks performed:
- **Service** — `systemctl is-active sing-box.service`
- **TUN** — `ip link show singtun0` (UP/DOWN)
- **DNS** — resolve `google.com` via the system resolver
- **TCP** — connect to `1.1.1.1:80`
- **HTTPS** — GET `https://www.google.com`
- **External IP** — fetched via ipify / ifconfig.me / ipinfo.io (fallback chain)

The **Diagnostics** page shows live results and latency history charts (Chart.js).

```bash
sqlite3 singbox_manager.db \
  "SELECT checked_at, check_name, ok, latency_ms FROM health_check_log ORDER BY id DESC LIMIT 20;"
```

---

## Deploy journal

Every deploy attempt is recorded in the `deploy_log` table:

| Column | Description |
|--------|-------------|
| `started_at` | Timestamp |
| `node_tag` | Which node was being activated |
| `config_hash` | sha256 of the generated config (canonical JSON) |
| `backup_name` | Backup filename created before deploy |
| `stage_reached` | Last stage: `validate \| deploy \| restart \| health \| ok` |
| `success` | Whether deploy completed successfully |
| `rolled_back` | Whether auto-rollback was triggered |
| `error` | Error message if failed |

```bash
sqlite3 singbox_manager.db \
  "SELECT started_at, node_tag, stage_reached, success, rolled_back FROM deploy_log ORDER BY id DESC LIMIT 10;"
```

---

## Testing

### Unit tests (no root, no sing-box required)

```bash
make test
```

**207 tests** covering:

| File | Coverage |
|------|----------|
| `test_parse_vless.py` | VLESS URL parser edge cases |
| `test_parse_hysteria2.py` | Hysteria2 URL parser edge cases |
| `test_generate_config.py` | Config generator — all DNS/route presets |
| `test_health.py` | Health checks — service, TUN, DNS, TCP, HTTPS, overall |
| `test_metrics.py` | `/api/metrics/latency` — hours clamping, series, uptime |
| `test_deployer.py` | config_hash, lock contention, all failure stages, rollback |
| `test_validator.py` | Binary not found, timeout, invalid config, temp file cleanup |
| `test_registry.py` | Parser dispatch, unsupported scheme, VLESS/Hy2 param edge cases |
| `test_auth.py` | Token roundtrip/expiry, rate limiting, CSRF, HTTP middleware |
| `test_profiles.py` | Profile CRUD, activate/deactivate, state transitions |
| `test_notify.py` | All channels, priority mapping, error resilience, fire() scheduling |

### E2e tests (Playwright, no root required)

```bash
make e2e
```

**50 tests** — starts a real uvicorn server on port 19090 with an isolated temp
DB and all system/helper calls mocked. No sing-box binary, no sudo required.

| Area | Tests |
|------|-------|
| Pages load | Dashboard, Nodes, Profiles, Diagnostics, Logs, Backups, Settings |
| Node CRUD | Add VLESS, add Hy2, activate, delete, re-add (updates) |
| Profile CRUD | Create, activate (badge + dashboard card), delete |
| Service actions | Restart, Stop, Start, Validate Config |
| Settings | Save, persist, bypass_ru preset, restore defaults |
| Import/Export | Export JSON, round-trip import without duplicates |
| Backups | List, restore flow (redirects to dashboard) |
| Nav active state | Correct link highlighted on each page (7 pages) |
| API partials | `/api/logs`, `/api/health`, `/api/ip`, `/api/diff`, `/api/sysinfo`, `/api/metrics/latency` |
| Error cases | Invalid URL, oversized lines param |

---

## Project structure

```
app/
  main.py              FastAPI routes + lifespan + background health task
  auth.py              Auth middleware, session tokens, rate limiting, CSRF
  notify.py            Fire-and-forget notifications (notify-send/Telegram/ntfy)
  version.py           VERSION constant
  db.py                SQLite engine, session, Base
  models.py            Node, Settings, DeployLog, HealthCheckLog, Profile
  health.py            async service/TUN/DNS/TCP/HTTPS checks, external IP
  logging_config.py    setup_logging(), get_logger() — structured, no spam
  parsers/
    base.py            ParsedNode (Pydantic base model)
    registry.py        @register decorator, parse_url() dispatcher
    vless.py           VlessNode + parse_vless()
    hysteria2.py       Hysteria2Node + parse_hysteria2()
  singbox/
    generator.py       build_outbound(), generate_config()
    dns.py             DNS_PRESETS (quad9_tls, cloudflare_tls, google_tls)
    routes.py          ROUTE_PRESETS (full_tunnel, bypass_lan, bypass_ru)
    deployer.py        deploy_with_rollback(), config_hash(), DeployResult
    service.py         start / stop / restart / reload / status / logs / version
    validator.py       validate_config() — calls sing-box check
  templates/           Jinja2 (dashboard, nodes, profiles, login,
                                logs, backups, diagnostics, settings)
  static/style.css     Dark theme + latency chart styles

migrations/            Alembic migrations
  versions/            Migration scripts
  env.py               Alembic env — wired to app.db + all models

scripts/
  singbox-manager-helper   Privileged helper (install to /usr/local/bin/)

sudoers.d/
  singbox-manager          Sudoers rule (install to /etc/sudoers.d/)

singbox-manager.service    systemd unit for the web app

tests/
  test_parse_vless.py
  test_parse_hysteria2.py
  test_generate_config.py
  test_health.py
  test_metrics.py
  test_deployer.py
  test_validator.py
  test_registry.py
  test_auth.py
  test_profiles.py
  test_notify.py
  e2e/
    conftest.py            Uvicorn server fixture + all system mocks
    test_smoke.py          50 Playwright e2e tests
```

---

## Threat model

**What is protected:**

- The web app binds to `127.0.0.1` only — no network exposure.
- Set `SINGLE_ADMIN_PASSWORD` to require a login; without it, the panel is open
  to any local user and a prominent warning banner is shown.
- Session cookies are HMAC-SHA256 signed with `SESSION_SECRET` — forged tokens
  are rejected. Sessions expire after 30 days.
- CSRF protection via `Origin`/`Referer` header validation on all mutating requests.
- Rate limiting prevents brute-force of the login password.
- Privileged operations go through a single helper binary via a narrow sudoers rule.
- The helper validates all inputs and does not use `shell=True`.
- Config files at `/etc/sing-box/config.json` are readable at mode 0o644 —
  the app reads them directly for diff without sudo.

**What is not protected:**

- A local attacker with access to your session can activate any stored node
  and restart sing-box. This is intentional — the UI is a management tool.
- Proxy credentials (passwords, UUIDs) are stored in plaintext in `singbox_manager.db`.
  This is a local pet-project tool — encryption at rest is out of scope.
- Notification channels (Telegram token, ntfy topic) are stored in env vars —
  protect your environment from other local users.

---

## Troubleshooting

**"Helper not found at /usr/local/bin/singbox-manager-helper"**
Run install step 3. Verify: `ls -la /usr/local/bin/singbox-manager-helper`

**"sing-box binary not found … set the SINGBOX_BIN env var"**
sing-box is not at `/usr/bin/sing-box`. Either install it there or:
```bash
SINGBOX_BIN=/usr/local/bin/sing-box make run
```

**sudo password prompt or "no password supplied"**
Check that `/etc/sudoers.d/singbox-manager` exists, is mode 440, and
`sudo visudo -c` reports OK. Check the username matches.

**Login page appears but I didn't set a password**
Check startup logs for `NO PASSWORD SET` warning — if `SINGLE_ADMIN_PASSWORD`
was set somehow (e.g. leftover in your environment), it will enable auth.

**Sessions reset on every restart**
Set `SESSION_SECRET` to a persistent value: `openssl rand -hex 32`.

**notify-send not working**
Requires a running desktop session with an active DBUS connection.
If running as a systemd user service, ensure the service has access to the session bus.
Check: `notify-send "test" "message"` in your terminal.

**Telegram notifications not arriving**
Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set correctly.
Send a manual test via Settings → Notifications → Test. Check logs for HTTP errors.

**Deploy fails at 'validate' — sing-box check errors about TUN**
`sing-box check` may warn about the TUN interface not existing during
offline validation. This is a warning, not a hard error. If validation
still fails, the error message shows the actual sing-box output.

**Deploy fails at 'health' — service not active after restart**
Check `journalctl -u sing-box.service -n 50` for the real error.
The previous config has been automatically restored (and a notification sent).

**Config diff shows changes I didn't make**
The diff compares the deployed file against what *would be generated now*
with current presets. If you changed a preset in Settings without
re-activating, the diff will show that delta.

**External IP shows real IP instead of VPN IP**
sing-box TUN is not capturing traffic. Check:
```bash
systemctl status sing-box.service
ip route show table main | grep singtun0
```

**Port 9090 already in use**
Change `--port` in `singbox-manager.service` or set `PORT=xxxx` in the
environment before starting uvicorn.

**Database schema error on startup**
If you see a column error like `no such column: nodes.parsed_json`, you
are upgrading from v1. Delete `singbox_manager.db` and restart — see
[Upgrade from v1](#from-v1-before-alembic--before-parsed_json).
