# Sing-Box Manager

Local web UI for managing [sing-box](https://sing-box.sagernet.org/) on Manjaro/Arch Linux.

- Paste a proxy URL → parse → validate → deploy with auto-rollback
- Dashboard: service status, external IP, config diff, recent logs
- DNS and route presets (Quad9/Cloudflare/Google DoT, full tunnel / bypass LAN)
- Config backups and one-click restore
- Deploy journal — every deploy attempt is logged to the DB
- Binds to **127.0.0.1:9090 only** — no external exposure

**Supported protocols:** `vless://` (Reality / TLS), `hysteria2://`, `hy2://`

---

## Architecture

```
Browser (localhost only)
        │
        ▼
FastAPI app  127.0.0.1:9090
  │
  ├─ parsers/        URL → Pydantic model (VlessNode, Hysteria2Node)
  │                  stored as parsed_json in SQLite — NOT outbound JSON
  │                  config regenerated dynamically on each activate
  │
  ├─ singbox/
  │   ├─ generator   ParsedNode + DNS preset + route preset → config dict
  │   ├─ deployer    validate → deploy → reload → healthcheck → rollback
  │   │              async.Lock prevents concurrent deploys
  │   ├─ service     start / stop / restart / reload / status / logs
  │   └─ validator   calls `sing-box check` on a temp file (no root)
  │
  ├─ health.py       async DNS + TCP + HTTPS checks, external IP
  │
  └─ models.py       Node, Settings, DeployLog (SQLite via SQLAlchemy)
                     schema managed by Alembic, auto-migrated on startup

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
- Python ≥ 3.8 (tested on 3.8.18 and 3.11)
- A user account that will run the web app (default: `nikita` — change in sudoers if different)

---

## Install

### 1. Clone and enter the directory

```bash
cd ~/path/to/local-singbox-manager
```

### 2. Create virtualenv and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For e2e tests, also install browser binaries (one-time):

```bash
playwright install chromium
```

### 3. Install the privileged helper

The helper is the **only** binary that runs as root. It validates all inputs
and performs only whitelisted operations. Never edit it without reviewing
the security implications.

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

### 6. Run

```bash
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 9090
```

Open **http://127.0.0.1:9090**

The app runs Alembic migrations automatically on startup — the SQLite database
(`singbox_manager.db`) is created on first run.

---

## Run as a systemd service

```bash
# Review WorkingDirectory and ExecStart paths in the unit file first
sudo cp singbox-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now singbox-manager.service
sudo systemctl status singbox-manager.service
```

---

## Upgrade flow

### From any previous version with Alembic

```bash
git pull
source .venv/bin/activate
pip install -r requirements.txt   # picks up any new deps
# migrations run automatically on next app start
```

### From v1 (before Alembic / before parsed_json)

The v1 schema stored `outbound_json` (generated sing-box JSON). v2 stores
`parsed_json` (raw parsed fields) and regenerates config dynamically.

These schemas are incompatible. Delete the old database before starting:

```bash
rm singbox_manager.db
```

Your proxy URLs are not lost — re-add them from the **Nodes** page.
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
3. reload       systemctl reload (falls back to restart if not configured)
4. health       wait 3s → check service is active
5. ok           mark node active in DB, log to DeployLog

on any failure after step 2:
   auto-rollback: helper restore <backup> → restart service
```

If deploy was interrupted before a backup was created (step 1 or early step 2),
there is nothing to roll back — your previous config is still in place.

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

Changes take effect on the next **Activate**.

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

## Deploy journal

Every deploy attempt is recorded in the `deploy_log` table:

| Column | Description |
|--------|-------------|
| `started_at` | Timestamp |
| `node_tag` | Which node was being activated |
| `config_hash` | sha256 of the generated config (canonical JSON) |
| `backup_name` | Backup filename created before deploy |
| `stage_reached` | Last stage: `validate \| deploy \| reload \| health \| ok` |
| `success` | Whether deploy completed successfully |
| `rolled_back` | Whether auto-rollback was triggered |
| `error` | Error message if failed |

Query directly with sqlite3 if needed:

```bash
sqlite3 singbox_manager.db "SELECT started_at, node_tag, stage_reached, success, rolled_back FROM deploy_log ORDER BY id DESC LIMIT 10;"
```

---

## Testing

### Unit tests (no root, no sing-box required)

```bash
source .venv/bin/activate
pytest -v
```

Covers URL parsers, config generator, DNS/route presets, registry dispatch.

### E2e smoke tests (Playwright, no root required)

```bash
source .venv/bin/activate
pytest tests/e2e --browser chromium -v
```

Starts a real uvicorn server on port 19090 with an isolated temp DB and all
system calls mocked. Tests all pages, node CRUD, activate flow, settings
persistence, and HTMX partial endpoints.

---

## Project structure

```
app/
  main.py              FastAPI routes + startup migrations
  db.py                SQLite engine, session, Base
  models.py            Node, Settings, DeployLog
  health.py            async DNS / TCP / HTTPS checks
  parsers/
    base.py            ParsedNode (Pydantic base model)
    registry.py        @register decorator, parse_url() dispatcher
    vless.py           VlessNode + parse_vless()
    hysteria2.py       Hysteria2Node + parse_hysteria2()
  singbox/
    generator.py       build_outbound(), generate_config()
    dns.py             DNS_PRESETS (quad9_tls, cloudflare_tls, google_tls)
    routes.py          ROUTE_PRESETS (full_tunnel, bypass_lan)
    deployer.py        deploy_with_rollback(), config_hash(), DeployResult
    service.py         start / stop / restart / reload / status / logs
    validator.py       validate_config() — calls sing-box check
  templates/           Jinja2 (dashboard, nodes, logs, backups, diagnostics, settings)
  static/style.css     Dark theme

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
  e2e/
    conftest.py            Server fixture + mocks
    test_smoke.py          20 Playwright smoke tests
```

---

## Threat model

**What is protected:**

- The web app binds to `127.0.0.1` only — no network exposure.
- No authentication on the UI — the threat model assumes the local user is trusted.
  Do not expose port 9090 externally (no reverse proxy without adding auth).
- Privileged operations (write to `/etc/sing-box/`, control systemd service) go
  through a single helper binary via a narrow sudoers rule.
- The helper validates all inputs with regex before acting. It does not use
  `shell=True` and does not accept arbitrary commands.
- Config files at `/etc/sing-box/config.json` are readable at mode 0o644 —
  the app reads them directly for diff without sudo.

**What is not protected:**

- A local attacker with access to your session can activate any stored node
  and restart sing-box. This is intentional — the UI is a management tool.
- The backup directory is writable only by root. If the helper is compromised,
  an attacker could write arbitrary configs. Keep the helper binary unmodified.
- Proxy credentials (passwords, UUIDs) are stored in plaintext in `singbox_manager.db`.
  This is a local pet-project tool — encryption at rest is out of scope.

---

## Troubleshooting

**"Helper not found at /usr/local/bin/singbox-manager-helper"**
Run install step 3. Verify: `ls -la /usr/local/bin/singbox-manager-helper`

**sudo password prompt or "no password supplied"**
Check that `/etc/sudoers.d/singbox-manager` exists, is mode 440, and
`sudo visudo -c` reports OK. Check the username matches.

**Deploy fails at 'validate' — sing-box check errors about TUN**
`sing-box check` may warn about the TUN interface not existing during
offline validation. This is a warning, not a hard error. If validation
still fails, the error message shows the actual sing-box output.

**Deploy fails at 'health' — service not active after restart**
Check `journalctl -u sing-box.service -n 50` for the real error.
The previous config has been automatically restored.

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
