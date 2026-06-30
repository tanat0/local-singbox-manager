# Disaster Recovery

This document covers manual recovery for a single trusted host. It is not a
backup subsystem; keep copies of the files below with the same care as secrets.

## What To Preserve

Before reinstalling, moving hosts, or debugging a failed rollback, preserve:

| Item | Default path | Why it matters |
| --- | --- | --- |
| SQLite database | `./singbox_manager.db` | Nodes, profiles, settings, deploy logs, managed users, delivery logs |
| Environment file | `.env` | Auth secret, path overrides, Telegram and ntfy settings |
| Deployed sing-box config | `/etc/sing-box/config.json` | Last config actually used by `sing-box.service` |
| Helper backups | `/etc/sing-box/backups` | Rollback source files created before deploys |
| Rendered systemd unit | `/etc/systemd/system/singbox-manager.service` | Installed user, port, working directory, environment path |
| Rendered sudoers rule | `/etc/sudoers.d/singbox-manager` | Helper path and least-privilege sudo access |
| Git revision | `git rev-parse HEAD` | Code version that produced the database and generated configs |

The database, `.env`, raw proxy URLs, generated client configs, Telegram tokens,
and notification settings are sensitive. Do not paste them into issue reports or
chat logs.

## Database Backup

Use SQLite's online backup command when the app may be running:

```bash
sqlite3 singbox_manager.db ".backup 'singbox_manager.backup.db'"
```

For a stopped app, a plain file copy is also acceptable:

```bash
sudo systemctl stop singbox-manager.service
cp singbox_manager.db singbox_manager.backup.db
sudo systemctl start singbox-manager.service
```

Restore only after stopping the app:

```bash
sudo systemctl stop singbox-manager.service
cp singbox_manager.backup.db singbox_manager.db
sudo systemctl start singbox-manager.service
```

After restore, open the dashboard and check the active node/profile, Settings,
and Config Diff. Re-activate the intended node or profile if the database state
does not match `/etc/sing-box/config.json`.

## Host Migration Checklist

1. Install the same code revision or a newer compatible release.
2. Restore `.env` with mode `600`.
3. Restore `singbox_manager.db` into the project root.
4. Run `bash scripts/install-systemd.sh --dry-run` and review rendered paths.
5. Install or refresh the helper and unit with `bash scripts/install-systemd.sh`.
6. Copy `/etc/sing-box/config.json` and `/etc/sing-box/backups` if preserving the
   live deployed config and rollback history.
7. Run `make ops-check`.
8. Start or restart `singbox-manager.service`, then check Dashboard,
   Diagnostics, Logs, and Config Diff.

If `SESSION_SECRET` changes, existing browser sessions are invalidated. If
`SINGLE_ADMIN_PASSWORD` changes, use the new password after restart.

## Rollback Failure Runbook

If deploy says rollback failed or `sing-box.service` is unhealthy after a
restore attempt:

1. Stop making repeated deploy attempts until the current config is known.
2. Inspect the service state and recent logs:

   ```bash
   systemctl status sing-box.service
   journalctl -u sing-box.service -n 80 --no-pager
   ```

3. List helper backups:

   ```bash
   sudo /usr/local/bin/singbox-manager-helper list-backups
   ```

4. Restore a known-good backup through the helper:

   ```bash
   sudo /usr/local/bin/singbox-manager-helper restore /etc/sing-box/backups/config_YYYYMMDD_HHMMSS.json
   ```

5. Validate service state:

   ```bash
   systemctl is-active sing-box.service
   journalctl -u sing-box.service -n 50 --no-pager
   ```

6. In the panel, check Config Diff. If the restored file no longer matches the
   active node/profile and current settings, re-activate the intended profile
   only after the service is stable.

Use the actual helper path from `HELPER_BIN` if it differs from the default.

## Reconstructing State

The deployed config is the file currently used by sing-box. The database records
the manager's intended state: active node/profile, DNS preset, route preset,
groups, managed users, versions, fingerprints, and delivery attempts.

When these disagree, prefer the stable running service first, then use Config
Diff to decide whether to re-activate a node/profile or keep the restored file.
