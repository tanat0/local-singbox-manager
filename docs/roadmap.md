# Engineering Roadmap

This file tracks practical engineering work. It separates shipped behavior,
near-term milestones, and non-goals so the repo does not imply unsupported
features.

## Shipped State

- Local FastAPI web UI for a single Linux host running sing-box.
- Node parsing for VLESS and Hysteria2/Hy2 URLs.
- Config generation from stored node data plus DNS and route presets.
- Always-on route guards for generated TUN configs: selected domains are
  blocked and basic RU destinations go direct.
- Deploy pipeline with validation, helper-based config replacement, restart,
  lightweight health check, backup, rollback, and deploy logs.
- Profiles for node plus DNS/route preset combinations.
- Optional password auth, signed cookies, CSRF checks, and login rate limiting.
- Local diagnostics for logs, health checks, latency history, service status,
  external IP, and config diff.
- Optional notifications through `notify-send`, Telegram, and ntfy.
- Optional Telegram admin bot for local management commands.
- Managed-user Telegram delivery of generated sing-box JSON configs plus raw
  proxy URL fallbacks with groups, selected nodes, route presets, config
  versions, fingerprints, refresh limits, and delivery logs.
- Separate managed-user Telegram delivery of `.sbclient` bundles for the local
  `singbox-client` app through `/sbclient`.
- VLESS transport compatibility for generated configs: HTTP/H2, gRPC,
  WebSocket, and HTTPUpgrade are mapped to sing-box `transport` objects; known
  unsupported modes fail explicitly instead of producing invalid JSON.
- Unit/page tests and Playwright e2e smoke tests with system calls mocked.

## 1.3.2 Observability

- Attach the active node tag to new background health samples.
- Show dashboard-level tunnel health for 24h and 7d.
- Show per-node observed health only for periods when that node was active.
- Add a dashboard problem digest that groups recent sing-box connection and DNS
  errors by outbound, target, and reason.
- Keep raw logs and detailed latency charts on Logs/Diagnostics pages.
- Document that observed tunnel health is not remote server uptime.

## 1.4 Client Config Delivery Validation

- Manually test generated sing-box JSON import on the target client devices.
- Manually test `.sbclient` import on target Windows and Android devices.
- Keep raw URL fallback visible when generated JSON or `.sbclient` attachments
  cannot be prepared for an unsupported transport.
- Add a web admin download action for `.sbclient` bundles if operators need a
  non-Telegram export path.
- Decide whether route guards should become configurable only after generated
  client configs have a clear UX and import path.
- Keep raw URL delivery available until generated config delivery is proven
  usable for the target devices.

## 1.5 Operations Hardening

- Add a smoke command for helper install, sudoers, sing-box binary, and systemd
  service state without modifying deployed config.
- Add disaster-recovery export notes for DB dump, `.env.example`, rendered
  service/sudoers examples, and current generated config metadata.
- Improve manual restore documentation for rollback failure cases.
- Continue splitting broad tests or service modules only when feature work makes
  the current shape harder to maintain.

## 1.6 3x-ui Relay Topology

- Document the first supported relay topology as manual inventory:
  client or managed user config -> RU 3x-ui inbound -> upstream nodes.
- Add node/topology metadata only if it helps the operator understand which
  stored links are entry relays and which are upstream exits.
- Treat exported 3x-ui links as ordinary imported nodes in the first pass.
- Do not store 3x-ui panel credentials or call the 3x-ui API until there is a
  concrete operation that cannot be handled by manual import/export.

## Non-Goals

- Hosted multi-tenant control plane.
- General remote server fleet management.
- Server-side bandwidth accounting or traffic enforcement.
- Device binding.
- Reliable remote kill-switch for distributed client configs.
- MTProto server inventory or rotation.
- Claims that Telegram raw URL delivery controls actual VPN usage.

## Maintenance Rules

- Keep `make lint`, `make test`, and CI green after feature work.
- Add regression tests when changing deploy, auth, Telegram, routing, or user
  distribution behavior.
- Keep test DB isolation strict so local `singbox_manager.db` is not mutated.
- Review docs after feature work for stale claims and unsupported promises.
