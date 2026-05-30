# Engineering Backlog

This file tracks practical work for the local sing-box manager. It separates
implemented behavior from backlog ideas so documentation does not imply support
for features that are not built.

## Current State

- Local FastAPI web UI for a personal sing-box client.
- Node parsing for VLESS and Hysteria2/Hy2 URLs.
- Config generation from stored node data plus DNS/route settings.
- Deploy pipeline with validation, helper-based config replacement, restart,
  lightweight service health check, backup, rollback, and deploy logs.
- Profiles for node plus DNS/route preset combinations.
- Optional password auth, signed cookies, CSRF checks, and login rate limiting.
- Local diagnostics for logs, health checks, latency history, service status,
  external IP, and config diff.
- Optional notifications through `notify-send`, Telegram, and ntfy.
- Optional Telegram admin bot for local management commands.
- Managed-user Telegram config delivery with config groups, selected nodes,
  config versions, fingerprints, refresh limits, and delivery logs.
- Unit/page tests and Playwright e2e smoke tests with system calls mocked.

## Near-Term Hardening

- Keep README short and move operational detail into focused docs.
- Keep `make lint`, `make test`, and CI green after feature work.
- Keep local quality gates reproducible through `make check-fast` and `make
  check`; avoid duplicating command logic in CI.
- Continue reducing route/service coupling where it gets in the way of tests.
- Keep test DB isolation strict so local `singbox_manager.db` is not mutated.
- Add regression tests when changing deploy, auth, Telegram, or user
  distribution behavior.
- Review docs after every feature pass for stale claims and unsupported
  promises.

## User Distribution Follow-Ups

- Separate personal/admin nodes from user-visible nodes if shared use grows.
- Add clearer UI filters for delivery log review.
- Add export of config delivery logs for manual audit.
- Add per-group/user expiry fields only if there is a concrete use case.
- Support QR or file exports only for specific client formats that can be
  tested.

## Operations Follow-Ups

- Add a small disaster-recovery export containing DB dump instructions,
  `.env.example`, rendered service/sudoers examples, and current generated
  config metadata.
- Improve backup restore documentation for manual recovery after rollback
  failure.
- Add a simple smoke command that validates helper install, sudoers, sing-box
  binary path, and systemd service state without modifying config.

## Non-Goals For Now

- Hosted multi-tenant control plane.
- General server fleet management.
- Server-side bandwidth accounting or traffic enforcement.
- Device binding.
- Reliable remote kill-switch for distributed client configs.
- MTProto server inventory or rotation.
- Claims that Telegram config delivery controls actual VPN usage.

## Audit Follow-Ups

- Revisit `app/services/users.py` if user distribution gains more behavior.
- Split broad tests into focused modules when they next need substantial edits.
- Replace import-time global test patches with fixture-scoped patches where it
  improves readability without weakening DB/system-call isolation.
- Consider moving dev/test tools into separate requirements if production
  packaging becomes a concern.
- Keep comments focused on constraints and edge cases; avoid comments that
  restate simple code.
