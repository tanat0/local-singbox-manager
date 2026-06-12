# Design Decisions

This document records the current project constraints and trade-offs. It is not
a promise that these choices fit every deployment.

## Localhost-Only Web UI

The app binds to `127.0.0.1` by default and the systemd template also allows
only loopback IP traffic.

Reason:

- the panel controls sing-box and can replace configs/restart the service
- reverse-proxy exposure changes the threat model
- local-only deployment keeps auth and session handling simple

If the panel is exposed through a reverse proxy, set `SINGLE_ADMIN_PASSWORD`,
use TLS, and treat the proxy as part of the security boundary.

## Sudo Helper Instead Of Root Web App

The FastAPI process should not run as root. Root work is limited to
`scripts/singbox-manager-helper`, installed under a fixed path and allowed by a
narrow sudoers rule.

Reason:

- config replacement and `systemctl` operations need privileges
- the web app does not need general root access
- the helper can validate a small command surface

The helper is not a sandbox. It is a small privileged boundary for this local
tool.

## SQLite

SQLite is the expected database for this project.

Reason:

- single-host local tool
- no multi-user web deployment requirement
- easy backup and inspection
- Alembic still gives explicit schema history

The app does not currently target PostgreSQL/MySQL deployment.

## Parsed Node Storage

Nodes store the raw URL and parsed source fields. Generated sing-box outbound
JSON is not treated as durable data.

Reason:

- sing-box schema evolves
- generator logic can be fixed centrally
- re-activation should use the current generator and settings

This means an old node may produce different generated JSON after an upgrade.
Use the dashboard diff before re-activating if that matters.

## Restart Instead Of Reload For Deploys

Deploy activation restarts `sing-box.service` instead of relying on reload.

Reason:

- TUN configs can fail to reload while the previous interface is still open
- restart behavior is more predictable for this local client use case

Manual service actions still expose reload/restart/start/stop where useful.

## Optional Telegram

Telegram is optional infrastructure, not the core control plane.

Reason:

- the manager must work without any external service
- Telegram delivery can fail when users have not started the bot
- bot polling is disabled in tests and can be disabled in tooling

Telegram errors are logged and should not roll back local state changes unless
the requested command itself failed.

## User Config Distribution

Managed users receive raw proxy URLs through Telegram commands. Groups select
existing nodes and carry a config version plus deterministic fingerprint.

Reason:

- raw URLs are the format already stored by the app
- different clients have different import mechanisms
- server-side enforcement is not available in the local client manager

Limits are refresh/delivery limits, not traffic controls. They reduce spam and
accidental repeated delivery; they do not prevent actual network usage.

## Routing Presets And Client Enforcement

Route presets are generated into the sing-box config deployed on the managed
host. They can send selected destinations direct or through the active outbound
for that host.

They do not control clients that imported a raw VLESS/Hysteria2 URL. Once a raw
URL is delivered, routing behavior belongs to the user's client application.
Changing this requires distributing full client configs with route presets,
not only proxy URLs.

## Always-On Route Guards

Generated TUN configs include a small hardcoded routing policy for this local
host: selected reporting and IP-checker domains go to the `block` outbound, and
basic RU destinations go to the `direct` outbound.

Reason:

- the policy is part of the local operator's expected baseline, not a per-user
  feature
- a hardcoded list is easier to review than an early rule editor
- putting the rules before presets keeps them consistent across route modes

This can break applications that rely on the blocked IP-checker endpoints. It
is not server-side enforcement and it is not a guarantee that other software
cannot infer routing state by other means.

## Current Trust Boundaries

Trusted:

- the local OS user running the app
- the installed helper binary
- the local SQLite database contents
- configured environment variables

Untrusted:

- web form input
- Telegram messages and user IDs
- proxy URLs pasted into the UI
- subprocess output from sing-box/systemd/network tools

The app validates inputs at the transport/service boundary and keeps privileged
operations behind the helper.

## Audit Follow-Ups

These are intentionally not fixed by broad rewrites:

- split `app/services/users.py` further only when new user-distribution behavior
  makes the current module harder to reason about
- consider a separate requirements file for dev/test tooling if dependency
  installation time or production packaging becomes a problem
- keep checking docs after feature work so README does not become the full
  operations manual again
