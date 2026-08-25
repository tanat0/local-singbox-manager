# Sing-Box Manager

[![Tests](https://github.com/tanat0/local-singbox-manager/actions/workflows/tests.yml/badge.svg)](https://github.com/tanat0/local-singbox-manager/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)

Local-first management utility for operating a small trusted
[sing-box](https://sing-box.sagernet.org/) setup on Linux. It is intended to run
on the same host as sing-box and bind to `127.0.0.1:9090`.

This is not a hosted VPN panel or public control plane. It stores local proxy
URLs, generates sing-box configs, deploys them through a small sudo helper, and
keeps local audit logs in SQLite.

Current released version: `1.3.0`. `main` also contains unreleased hardening
work listed in [CHANGELOG.md](CHANGELOG.md).

## Why This Exists

This project was built for a small trusted setup where one technical user
manages sing-box configuration for personal devices and a few family or friend
devices.

The goal is to avoid manual config sharing, repeated explanations, and fragile
copy-paste updates when nodes, profiles, or generated links change.

It is intentionally local-first and small-scope: one trusted operator, one
managed host, a small number of known users and devices, no public multi-tenant
control plane, and no remote exposure by default.

## Scope

### Core Scope

- Parse and store `vless://`, `hysteria2://`, and `hy2://` node URLs.
- Generate sing-box client configs from validated inputs with DNS and route
  presets.
- Activate a node or profile through validate, deploy, restart, health check,
  and rollback steps.
- Keep deploy, health, and admin action logs in SQLite.

### Small Trusted-User Workflow

- Store managed Telegram users and groups.
- Generate user-specific sing-box config files, `.sbclient` bundles, and raw-link
  fallbacks from selected nodes.
- Send config updates through Telegram, or download the same artifacts from the
  Users page.
- Track group versions, deterministic config fingerprints, delivery attempts,
  and refresh limits.
- Reduce manual support for family or friend devices.

### Operational Helpers

- Local diagnostics pages for logs, service state, health checks, and latency
  history.
- Optional single-admin web auth with signed cookies and basic CSRF checks.
- Optional notifications through `notify-send`, Telegram, and ntfy.sh.
- Optional Telegram admin bot for status, logs, node listing, and activation.

## Non-Goals

This project is not:

- a hosted VPN panel
- a public multi-tenant control plane
- a commercial proxy management platform
- a replacement for enterprise device management
- intended to be exposed directly to the Internet

## Known Limitations

- Proxy credentials are stored in plaintext in `singbox_manager.db`.
- User distribution sends client-side config material. It does not enforce
  actual VPN usage server-side.
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

Install the helper, sudoers rule, service file, and initial `.env` after
reviewing the dry run:

```bash
bash scripts/install-systemd.sh --dry-run
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

Open **Nodes**, paste a supported proxy URL, save it, then activate a node or
create a **Profile** that combines a node with DNS and route presets. Check
**Dashboard**, **Logs**, and **Diagnostics** if activation fails.

Deploys are serialized with an in-process lock. Each deploy writes a backup
before replacing `/etc/sing-box/config.json`. If restart or the lightweight
service health check fails after deploy, the previous config is restored.

Operational details are in [docs/ops.md](docs/ops.md).

## Configuration

The app reads `.env` when started by `make run` or the installed systemd unit.
Common settings include `DATABASE_URL`, `SINGLE_ADMIN_PASSWORD`,
`SESSION_SECRET`, sing-box/helper paths, background task flags, Telegram
settings, and ntfy settings. See `.env.example` and
[docs/install.md](docs/install.md) for the full list.

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
- [docs/ecosystem.md](docs/ecosystem.md)
- [docs/client-contract.md](docs/client-contract.md)
- [docs/design-decisions.md](docs/design-decisions.md)
- [docs/recovery.md](docs/recovery.md)
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

Run `make lint`, `make test`, `make e2e`, `make check-fast`, or `make check`.
Dependencies are defined in `pyproject.toml`, locked in `uv.lock`, and exported
to `requirements.txt` / `requirements-dev.txt` for pip-based environments.

`make test` uses a temp SQLite database and mocked system calls. `make e2e`
starts uvicorn on `127.0.0.1:19090` and uses Playwright with system calls
mocked. CI calls the same Make targets for lint and non-e2e tests.

Optional local git hooks are available:

```bash
make install-hooks
```

The hooks block commits, pushes, and rebases on `main`. They run checks without
formatting or rewriting files. Use `SKIP_PRE_PUSH=1` only for a deliberate
manual bypass.

## Repository Notes

Schema changes live under `migrations/versions`. The tracked sudoers and
systemd files are templates rendered by `scripts/install-systemd.sh`. Local
database files, virtualenvs, caches, and `.env` files are ignored by git.
Changelog entries live in [CHANGELOG.md](CHANGELOG.md).

For focused contribution notes, see [CONTRIBUTING.md](CONTRIBUTING.md). For the
local security boundary and reporting notes, see [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
