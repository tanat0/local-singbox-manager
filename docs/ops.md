# Operations

This document covers day-to-day use and troubleshooting. All commands assume a
local checkout of the repository.

## Node Activation

Add nodes from the Nodes page by pasting a supported URL:

```text
vless://UUID@HOST:PORT?security=reality&sni=SNI&pbk=PUBKEY&sid=SHORTID&fp=chrome&type=tcp#tag
hysteria2://PASSWORD@HOST:PORT?sni=SNI#tag
```

Activation runs:

1. generate config from the selected node and current presets
2. validate with `sing-box check` on a temporary file
3. call the privileged helper to back up and replace the config
4. restart `sing-box.service`
5. verify `systemctl is-active sing-box.service`
6. mark the node active and write `deploy_log`

If restart or service health fails after deploy, the helper restores the
previous config and restarts the service. Rollback failure requires manual
recovery from `/etc/sing-box/backups`.

`reload` is not used for deploys because TUN configs can fail on reload while
the old interface is still open.

## Profiles

A profile stores a node plus DNS and route presets. Activating a profile runs
the same deploy path as activating a node. Direct node activation or manual
settings changes clear the active profile marker so the UI reflects the current
state.

Profiles use a soft node reference and can outlive deleted nodes. Activating a
profile with a missing node fails safely.

## Settings

DNS presets:

| Preset | Resolver |
| --- | --- |
| `quad9_tls` | 9.9.9.9 over DoT |
| `cloudflare_tls` | 1.1.1.1 over DoT |
| `google_tls` | 8.8.8.8 over DoT |

Route presets:

| Preset | Behavior |
| --- | --- |
| `full_tunnel` | all traffic through sing-box |
| `bypass_lan` | private IP ranges go direct |
| `bypass_ru` | RU IP/domain rule sets go direct, rest through sing-box |

The `bypass_ru` preset references remote SagerNet `.srs` rule sets. sing-box
downloads and refreshes them; the app does not keep a local geo database.

These presets apply to the generated config deployed on the managed host. They
do not affect managed users who currently receive raw proxy URLs through
Telegram.

Generated configs default to `log.level: warn`. Use `info` or `debug` only for
diagnostics and re-activate a node after changing the setting.

## Logs And Diagnostics

- Dashboard shows service state, active node/profile, external IP, observed
  tunnel health, recent problem digest, node metadata, and config diff.
- Logs page can show all logs, warnings/errors, fatal/error, and text grep.
- Diagnostics page runs live checks and shows recent latency history from the
  SQLite health log.

Health checks:

- `systemctl is-active sing-box.service`
- `ip link show singtun0`
- DNS resolve for `google.com`
- TCP connect to `1.1.1.1:80`
- HTTPS request to `https://www.google.com`
- external IP through ipify, ifconfig.me, then ipinfo.io

Background health checks keep 7 days of data. New samples include the active
node tag at the time of the check. This is observed tunnel health while a node
was active, not a remote server uptime guarantee.

Inspect recent checks:

```bash
sqlite3 singbox_manager.db \
  "SELECT checked_at, node_tag, check_name, ok, latency_ms FROM health_check_log ORDER BY id DESC LIMIT 20;"
```

## Backups

Each deploy creates a helper backup before replacing
`/etc/sing-box/config.json`. Backups are listed on the Backups page.

Restoring a backup copies the selected file back to the sing-box config path,
restarts the service, and clears the active node flag because the deployed file
may no longer match the database.

Recent deploys:

```bash
sqlite3 singbox_manager.db \
  "SELECT started_at, node_tag, stage_reached, success, rolled_back FROM deploy_log ORDER BY id DESC LIMIT 10;"
```

## Notifications

Notification channels are best effort. Failure to notify does not block deploy,
rollback, health, settings, or user-management paths.

| Channel | Configuration |
| --- | --- |
| `notify-send` | no config, requires a desktop session and DBUS |
| Telegram notifications | `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` |
| ntfy | `NTFY_TOPIC`, optional `NTFY_SERVER` |

Notification events include deploy success/failure, rollback triggered/failure,
and health state transitions. Health notifications fire only when the state
changes.

Use Settings -> Notifications -> Send Test Notification to verify configured
channels.

## Telegram Admin Bot

The admin bot is optional. It uses long polling in the same app process when
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_IDS`, and `TELEGRAM_ADMIN_BOT_ENABLED=1`
are set.

Validate bot settings:

```bash
make telegram-check
```

Useful diagnostics:

```bash
.venv/bin/python scripts/check-telegram.py --list-updates
.venv/bin/python scripts/check-telegram.py --send-test
```

Admin commands:

```text
/status
/nodes
/activate <node-id-or-tag>
/logs
/health
/notify_test
```

Only numeric IDs listed in `TELEGRAM_ADMIN_IDS` are accepted. Admin actions are
written to `admin_action_log`.

## Managed Users

Managed non-admin Telegram users can call:

```text
/status
/config
/refresh
```

The Users page controls:

- config groups
- selected nodes per group
- group config version and refresh limit
- managed user Telegram IDs
- optional per-user refresh limit override
- delivery log visibility

`/config` and `/refresh` return raw proxy URLs for the assigned group with a
version and fingerprint. The fingerprint is a sha256 hash over sorted
`tag`, `protocol`, and `raw_url` values for the assigned nodes.

Refresh limits use a rolling one-hour window. User override wins over group
limit; otherwise the default is 10 deliveries per hour. Blocked attempts are
also logged.

When an enabled group's node assignment changes, enabled users in that group
receive a best-effort Telegram notification if a bot token is configured.
Failures are written to `config_delivery_log`.

## Troubleshooting

### Helper not found

Install it or run the systemd installer:

```bash
sudo cp scripts/singbox-manager-helper /usr/local/bin/singbox-manager-helper
sudo chmod 755 /usr/local/bin/singbox-manager-helper
sudo chown root:root /usr/local/bin/singbox-manager-helper
```

### sing-box binary not found

Set `SINGBOX_BIN` if sing-box is not at `/usr/bin/sing-box`:

```bash
SINGBOX_BIN=/usr/local/bin/sing-box make run
```

### sudo asks for a password

Check `/etc/sudoers.d/singbox-manager`, file mode `440`, and the rendered
username/helper path. Validate sudoers:

```bash
sudo visudo -c
```

### Sessions reset after restart

Set a persistent `SESSION_SECRET`.

### Telegram messages do not arrive

Check token/chat ID/admin IDs with `make telegram-check`. For notification
delivery, use the Settings test button and inspect app logs for HTTP errors.

### Deploy fails at validation

The page shows the output from `sing-box check`. If the binary path is wrong,
set `SINGBOX_BIN`.

### Deploy fails at health

Check sing-box logs:

```bash
journalctl -u sing-box.service -n 50
```

The previous config should have been restored automatically unless rollback
also failed.

### Config diff shows unexpected changes

The diff compares the deployed config to what would be generated now from the
active node/profile and current settings. If settings changed without
re-activation, the diff will show that pending change.

### External IP is not the VPN IP

Check sing-box and routing:

```bash
systemctl status sing-box.service
ip route show table main | grep singtun0
```

### Port 9090 is busy

Use `scripts/install-systemd.sh --port <port>` or run uvicorn with a different
local port.

### Database schema errors after an old upgrade

If upgrading from a pre-Alembic schema, export nodes if possible, delete the
old `singbox_manager.db`, restart, and import the node JSON again.
