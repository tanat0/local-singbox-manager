# Install And Upgrade

This document covers local installation, systemd setup, environment variables,
and upgrade notes.

## Requirements

- Linux host with systemd and sudo
- sing-box 1.13 or newer
- `sing-box.service` installed on the same host
- Python 3.8 or newer
- `uv` for normal install and development workflows
- a normal user account for the web app

Default paths:

| Path | Purpose |
| --- | --- |
| `/usr/bin/sing-box` | sing-box binary |
| `/etc/sing-box/config.json` | deployed client config |
| `/etc/sing-box/backups` | helper-created config backups |
| `/usr/local/bin/singbox-manager-helper` | privileged helper |
| `./singbox_manager.db` | local SQLite database |

Override binary paths with `SINGBOX_BIN` and `HELPER_BIN` when needed.

## Local Checkout

```bash
git clone https://github.com/tanat0/local-singbox-manager.git
cd local-singbox-manager
make install
```

`make install` runs `uv sync --no-dev` and creates `.venv` with runtime
dependencies only.

For development checks and tests:

```bash
make dev-install
.venv/bin/playwright install chromium
```

`pyproject.toml` is the dependency source of truth and `uv.lock` is tracked for
reproducible installs. `requirements.txt` and `requirements-dev.txt` are
compatibility exports for pip-based environments:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-dev.txt
```

When changing dependencies, update the lock and exports:

```bash
make lock
make export-requirements
```

## Environment

The app reads environment variables from the process. `make run` and the
installed systemd service load `.env` from the project root.

Start from the example file:

```bash
cp .env.example .env
chmod 600 .env
```

Recommended minimum for normal use:

```bash
SINGLE_ADMIN_PASSWORD=change-me
SESSION_SECRET=64-char-hex-string
```

Generate `SESSION_SECRET` once:

```bash
openssl rand -hex 32
```

Important variables:

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./singbox_manager.db` | SQLite is the expected deployment mode |
| `SINGLE_ADMIN_PASSWORD` | empty | empty means the panel is open to local users |
| `SESSION_SECRET` | random per process | empty invalidates sessions on restart |
| `SINGBOX_BIN` | `/usr/bin/sing-box` | used for validation and version checks |
| `HELPER_BIN` | `/usr/local/bin/singbox-manager-helper` | used for privileged operations |
| `HEALTH_CHECK_INTERVAL` | `300` | seconds between background health checks |
| `MIGRATIONS_ENABLED` | `1` | set `0` only for tests/tooling |
| `BACKGROUND_TASKS_ENABLED` | `1` | set `0` only for tests/tooling |
| `TELEGRAM_BOT_TOKEN` | empty | optional notifications/admin/user bot |
| `TELEGRAM_CHAT_ID` | empty | optional Telegram notification target |
| `TELEGRAM_ADMIN_IDS` | empty | comma-separated numeric Telegram admin IDs |
| `TELEGRAM_ADMIN_BOT_ENABLED` | `1` | set `0` to disable polling |
| `NTFY_TOPIC` | empty | optional ntfy notifications |
| `NTFY_SERVER` | `https://ntfy.sh` | override for self-hosted ntfy |

## Manual Run

```bash
make run
```

The app binds to `127.0.0.1:9090`. Alembic migrations run on startup unless
`MIGRATIONS_ENABLED=0`.

## Systemd Install

Preview rendered files:

```bash
bash scripts/install-systemd.sh --dry-run
```

Install helper, sudoers rule, systemd unit, and `.env` if missing:

```bash
bash scripts/install-systemd.sh
```

Useful options:

```bash
bash scripts/install-systemd.sh --user "$USER" --port 9090
bash scripts/install-systemd.sh --helper-bin /usr/local/bin/singbox-manager-helper
```

The installer:

- creates `.env` from `.env.example` if missing
- installs `scripts/singbox-manager-helper` as root
- renders `/etc/sudoers.d/singbox-manager`
- validates sudoers with `visudo -c`
- creates `/etc/sing-box/backups`
- installs `/etc/systemd/system/singbox-manager.service`
- enables and starts `singbox-manager.service`

After editing `.env`:

```bash
sudo systemctl restart singbox-manager.service
```

## Manual Helper Install

If not using the installer:

```bash
sudo cp scripts/singbox-manager-helper /usr/local/bin/singbox-manager-helper
sudo chmod 755 /usr/local/bin/singbox-manager-helper
sudo chown root:root /usr/local/bin/singbox-manager-helper
```

Render and review sudoers:

```bash
bash scripts/install-systemd.sh --dry-run
```

Install a matching sudoers file manually only after reviewing the rendered
username and helper path.

## Upgrade

For current Alembic-based versions:

```bash
git pull
make install
sudo systemctl restart singbox-manager.service
```

Migrations run automatically on next startup.

For older pre-Alembic/pre-`parsed_json` versions, export nodes before deleting
the old database if the old UI is still reachable:

```bash
curl http://127.0.0.1:9090/api/nodes/export > nodes_backup.json
rm singbox_manager.db
```

Start the app and import the exported JSON from the Nodes page. Old schemas
that stored generated outbound JSON are not migrated in place.
