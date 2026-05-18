# Local Sing-Box Manager Roadmap

## Summary

The project stays local-client focused first: stable deploys, clear logs, maintainable code, and reliable node switching. Telegram, user config distribution, server-side management, limits, and MTProto are planned as separate phases so each area can be tested without breaking the current manager.

## Phase 0: Stabilize Local Manager

- Keep the local service flow stable: install, restart, update repo, restart service.
- Finish the logical commit split.
- Keep `app/main.py` as app bootstrap only.
- Keep routes in `app/routes/` and reusable logic in `app/services/`.
- Add route/page smoke tests for major pages.
- Keep this phase focused on personal/local sing-box client management.

## Phase 1: Telegram Admin Bot MVP

- Access is admin-only through explicit Telegram IDs from `.env` or DB.
- Commands:
  - `/status`: sing-box service state, active node, external IP.
  - `/nodes`: list nodes with an active marker.
  - `/activate <node>`: activate a node through the existing deploy pipeline.
  - `/logs`: recent filtered problems.
  - `/health`: run current health checks.
  - `/notify_test`: verify bot delivery.
- The bot must reuse existing deploy/service APIs instead of duplicating sing-box logic.
- All admin actions are written to an audit log.

## Phase 2: User Config Distribution

- Add base web management for config groups and managed Telegram user IDs.
- Add a users table: Telegram ID, display name, enabled flag, allowed config groups.
- User commands:
  - `/config`: get assigned config or proxy.
  - `/status`: basic availability check.
  - `/refresh`: request the latest assigned config.
- Notify users when their assigned configuration changes.
- Separate personal/admin nodes from user-visible nodes.
- For Telegram proxy, provide clickable `tg://proxy` links where applicable.
- For VPN clients, there is no universal one-click add flow; support import links, files, or QR codes where client formats allow it.

## Phase 3: Abuse Control And Limits

- Add optional policy fields per user or group:
  - allowed servers/configs
  - max config refreshes per time window
  - expiration date
  - notes/manual risk flag
- Track data that is realistically observable:
  - issued configs
  - refresh/download history
  - server-side connection telemetry only where the server stack supports it.
- Treat device binding and IP checks as best-effort controls, not hard security.
- Do not pretend client-side VPN usage can always be killed cleanly. Reliable enforcement needs server-side firewall/session controls and may only force reconnects.

## Phase 4: Server-Side Management

- Add a separate “Servers” section.
- Model owned servers, their visibility, installed protocols, health, and user availability.
- Support server-side config generation/deploy for selected protocols.
- Keep personal-only servers separate from user-available servers.
- Add an audit log for server changes.

## Phase 5: MTProto

- Keep MTProto separate from the VPN/proxy node model unless the schema naturally converges.
- Support MTProto server inventory.
- Generate Telegram proxy links.
- Add availability checks and rotation workflow.

## Later Ideas

- Per-node/user cost notes for tracking who uses which paid server.
- Config group versioning so users can be notified only when their assigned config changes.
- Safer “dry run” deploy preview for server-side config changes.
- Minimal export bundle for disaster recovery: DB dump, `.env.example`, service file, and current generated config.
