# Architecture

This project is a local FastAPI app around sing-box client configuration. The
important boundary is between unprivileged web code and a small privileged
helper.

## Runtime Shape

```text
browser on localhost
  -> FastAPI app on 127.0.0.1:9090
     -> SQLite database
     -> sing-box binary for validation/version checks
     -> sudo helper for config deploy/restore/service control
     -> optional notification clients
     -> optional Telegram long-polling bot
```

The app process should run as a normal user. It does not need root access
except through the helper path allowed by sudoers.

## Module Boundaries

| Area | Responsibility |
| --- | --- |
| `app/main.py` | app bootstrap, migrations, background task startup |
| `app/routes/` | HTTP request parsing and response rendering |
| `app/services/` | business logic for deploys, nodes, profiles, users, metrics |
| `app/repositories.py` | shared database query boundaries |
| `app/models.py` | SQLAlchemy models |
| `app/parsers/` | proxy URL parsing into typed node models |
| `app/singbox/` | config generation, validation, service control, deploy pipeline |
| `app/telegram/` | Telegram client, dispatcher, handlers, presenters |
| `app/system_clients.py` | subprocess/systemd command wrappers |
| `scripts/singbox-manager-helper` | privileged file/service operations |

Routes should orchestrate. They should not contain sing-box generation logic,
privileged operations, Telegram transport details, or complex database rules.

## Database

SQLite is the default and expected storage backend. Schema is managed by
Alembic migrations under `migrations/versions`.

Core tables:

- `nodes`: parsed proxy node source data and metadata
- `settings`: simple key/value settings
- `profiles`: named node plus DNS/route preset combinations
- `deploy_log`: deploy attempt audit trail
- `health_check_log`: background health samples
- `admin_action_log`: accepted/denied Telegram admin actions
- `config_groups`: managed-user distribution groups
- `managed_users`: Telegram user IDs assigned to config groups
- `config_delivery_log`: config delivery and notification attempts

The app stores parsed source fields, not generated sing-box outbound JSON, so
configs can be regenerated when generator logic changes.

## Deploy Flow

Node/profile activation runs through `app.services.deploy` and
`app.singbox.deployer`:

```text
deserialize node
  -> generate config with current presets
  -> validate with sing-box check on a temp file
  -> helper deploy creates backup and replaces config
  -> restart sing-box.service
  -> lightweight service health check
  -> mark active and write deploy_log
```

If the flow fails after helper deploy, rollback restores the backup and
restarts the service. Rollback failure is reported and requires manual recovery.

An `asyncio.Lock` serializes deploys inside one app process.

## Privileged Helper Boundary

The helper is installed as root and called through sudo. It handles only these
operations:

- deploy a temp config into `/etc/sing-box/config.json`
- restore a named backup
- restart/start/stop/reload `sing-box.service`
- list backup filenames

The helper validates filenames and paths and does not provide an arbitrary
shell escape. The sudoers template grants passwordless access only to the
helper binary for the configured app user.

## Background Tasks

Startup can run:

- Alembic migrations
- health check loop
- Telegram long polling

Tests and tooling can disable startup side effects with:

```bash
MIGRATIONS_ENABLED=0
BACKGROUND_TASKS_ENABLED=0
```

The test suite uses an isolated temp SQLite database and mocks system/helper
calls.

## Telegram

Telegram support has two independent uses:

- notifications to a configured chat ID
- long-polling bot for admins and managed users

The bot routes admin and user commands through the same service/deploy/user
distribution logic used by the web UI. Handlers format Telegram responses but
do not duplicate sing-box config generation. Operator downloads of generated
JSON and `.sbclient` files use the same assignment and document builders.
