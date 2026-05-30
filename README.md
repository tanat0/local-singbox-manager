# Sing-Box Manager

[![Tests](https://github.com/tanat0/local-singbox-manager/actions/workflows/tests.yml/badge.svg)](https://github.com/tanat0/local-singbox-manager/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)

Local web UI for managing a personal [sing-box](https://sing-box.sagernet.org/)
client on Linux. It is intended to run on the same host as sing-box and bind to
`127.0.0.1:9090`.

This is not a hosted control plane. It stores local proxy URLs, generates a
sing-box config for one selected node/profile, deploys that config through a
small sudo helper, and keeps local audit logs in SQLite.

Current released version: `1.3.0`. `main` also contains the unreleased `1.3.1`
hardening work listed in [CHANGELOG.md](CHANGELOG.md).

## Implemented

- Parse and store `vless://`, `hysteria2://`, and `hy2://` node URLs.
- Generate sing-box client configs with DNS and route presets.
- Activate a node or profile through validate, deploy, restart, health check,
  and rollback steps.
- Keep deploy, health, admin action, and user config delivery logs in SQLite.
- Optional single-admin web auth with signed cookies and basic CSRF checks.
- Optional notifications through `notify-send`, Telegram, and ntfy.sh.
- Optional Telegram admin bot for status, logs, node listing, and activation.
- Optional managed-user config delivery over Telegram with group versions,
  deterministic fingerprints, delivery logs, and refresh limits.
- Local diagnostics pages for logs, service state, health checks, and latency
  history.

## Known Limitations

- The panel is a local management tool. Do not expose it to the LAN or Internet
  without adding a trusted reverse proxy and authentication.
- Proxy credentials are stored in plaintext in `singbox_manager.db`.
- User distribution sends raw proxy URLs. It does not enforce actual VPN usage
  server-side.
- Telegram notifications and desktop notifications are best effort.
- Device binding, bandwidth accounting, server-side session control, MTProto,
  and multi-server management are not implemented.
- The app targets Linux hosts with `systemd`, `sudo`, and a local sing-box
  service.

## Quick Start

Prerequisites:

- sing-box 1.13 or newer, normally at `/usr/bin/sing-box`
- `sing-box.service` managed by systemd
- Python 3.8 or newer
- `uv` for dependency installation
- a normal Linux user that will run the web app

Install runtime dependencies:

```bash
git clone https://github.com/tanat0/local-singbox-manager.git
cd local-singbox-manager
make install
```

For development checks and tests:

```bash
make dev-install
```

Preview the systemd service and sudoers rule:

```bash
bash scripts/install-systemd.sh --dry-run
```

Install the helper, sudoers rule, service file, and initial `.env`:

```bash
bash scripts/install-systemd.sh
```

For manual local runs:

```bash
make run
```

Open `http://127.0.0.1:9090`.

Set at least these values in `.env` before using the panel for anything more
than local testing:

```bash
SINGLE_ADMIN_PASSWORD=change-me
SESSION_SECRET=64-char-hex-string
```

Generate a persistent session secret with:

```bash
openssl rand -hex 32
```

Full install and upgrade notes are in [docs/install.md](docs/install.md).

## Basic Use

1. Open **Nodes**.
2. Paste a supported proxy URL.
3. Save it.
4. Click **Activate** on a node or create a **Profile** that combines a node
   with DNS and route presets.
5. Check **Dashboard**, **Logs**, and **Diagnostics** if activation fails.

Deploys are serialized with an in-process lock. Each deploy writes a backup
before replacing `/etc/sing-box/config.json`. If restart or the lightweight
service health check fails after deploy, the previous config is restored.

Operational details are in [docs/ops.md](docs/ops.md).

## Configuration

The app reads `.env` when started by `make run` or the installed systemd unit.
Common settings:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLite URL, defaults to `sqlite:///./singbox_manager.db` |
| `SINGLE_ADMIN_PASSWORD` | Enables the login page |
| `SESSION_SECRET` | Signs session cookies |
| `SINGBOX_BIN` | sing-box binary path |
| `HELPER_BIN` | privileged helper path |
| `HEALTH_CHECK_INTERVAL` | background health interval in seconds |
| `MIGRATIONS_ENABLED` | set `0` only for tests/tooling |
| `BACKGROUND_TASKS_ENABLED` | set `0` only for tests/tooling |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token for notifications and bot flows |
| `TELEGRAM_CHAT_ID` | Telegram notification chat ID |
| `TELEGRAM_ADMIN_IDS` | comma-separated admin Telegram user IDs |
| `NTFY_TOPIC` | enables ntfy notifications |

See `.env.example` and [docs/install.md](docs/install.md) for the full list.

## Architecture Summary

The web app is FastAPI with Jinja templates and SQLite via SQLAlchemy/Alembic.
Routes orchestrate request handling, service modules hold business logic,
repositories isolate common database queries, and `app/singbox` contains the
sing-box config/deploy boundary.

Privileged work is limited to `scripts/singbox-manager-helper`, installed as
root and allowed through a narrow sudoers rule. The web app does not run as
root.

More detail:

- [docs/architecture.md](docs/architecture.md)
- [docs/design-decisions.md](docs/design-decisions.md)
- [docs/roadmap.md](docs/roadmap.md)

## Threat Model

Protected:

- remote network access by default, because uvicorn binds to `127.0.0.1`
- optional login when `SINGLE_ADMIN_PASSWORD` is set
- signed session cookies
- Origin/Referer checks on mutating web requests
- privileged operations constrained to one helper binary

Not protected:

- local users who can reach the panel while auth is disabled
- plaintext proxy credentials in the SQLite database
- notification tokens stored in the process environment
- server-side enforcement of client usage for distributed configs

The default systemd unit also uses `IPAddressAllow=127.0.0.1/8` as a second
local-only guard. It is still your responsibility not to publish the panel.

## Tests And Checks

```bash
make lint
make test
make e2e
make check-fast
make check
```

Dependencies are defined in `pyproject.toml` and locked in `uv.lock`.
`requirements.txt` and `requirements-dev.txt` are compatibility exports for
pip-based environments.

`make test` runs non-e2e tests with a temp SQLite database and mocked system
calls. `make e2e` starts a real uvicorn server on `127.0.0.1:19090` and uses
Playwright with system calls mocked.

`make check-fast` runs lint plus non-e2e tests. `make check` also runs e2e.
CI calls the same Make targets for lint and non-e2e tests.

Optional local git hooks are available:

```bash
make install-hooks
```

The hooks block commits, pushes, and rebases on `main`. They run checks without
formatting or rewriting files. Use `SKIP_PRE_PUSH=1` only for a deliberate
manual bypass.

## Repository Notes

- Schema changes are Alembic migrations under `migrations/versions`.
- The tracked `sudoers.d/singbox-manager` and `singbox-manager.service` files
  are templates rendered by `scripts/install-systemd.sh`.
- The local database, virtualenv, caches, and `.env` files are ignored by git.
- Changelog entries live in [CHANGELOG.md](CHANGELOG.md).

## License

MIT. See [LICENSE](LICENSE).
