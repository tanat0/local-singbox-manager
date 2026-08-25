# Agent Notes

This repository is the admin/operator side of the personal sing-box setup.
Treat it as a local-first management utility, not as the Windows/Android client
application and not as a hosted VPN panel.

## Repository Role

- Store nodes, profiles, config groups, managed users, delivery logs, and local
  operator state.
- Generate and deploy the sing-box config for the managed Linux host.
- Deliver user-facing artifacts through Telegram:
  - raw proxy URL fallback links;
  - generic sing-box JSON configs;
  - `.sbclient` bundles for the companion `singbox-client` project.
- Operators can also download the same generated JSON and `.sbclient` files
  from the Users page.
- Keep local observability, diagnostics, deploy history, rollback, and helper
  checks in this repo.

## Boundaries

- Do not implement Windows or Android UI/runtime behavior here. That belongs in
  `/home/nikita/Documents/projects/own/singbox-client/`.
- Do not make this app depend on a client-side library unless duplication has
  become a demonstrated maintenance problem.
- Do not add a hosted sync API, public control plane, device binding, or remote
  kill switch without an explicit design change.
- Do not store 3x-ui panel credentials or call the 3x-ui API in the first relay
  topology pass. Treat exported 3x-ui links as imported nodes until a concrete
  operator workflow requires more.

## Shared Contract

- `.sbclient` schema v1 is an offline import contract owned jointly by this repo
  and `singbox-client`; see `docs/client-contract.md`.
- Raw proxy URLs remain the credential source of truth for user delivery.
- Route preset IDs must stay aligned with the client project:
  `full_tunnel`, `bypass_lan`, and `bypass_ru`.
- Unsupported transports should fail fast with safe user-facing errors and raw
  fallback links where possible. Do not generate invalid sing-box JSON.

## Change Rules

- Keep `README.md`, `docs/ecosystem.md`, `docs/client-contract.md`, and
  `docs/roadmap.md` aligned when changing user delivery or topology behavior.
- Add focused tests for routing, Telegram delivery, config generation, deploy,
  auth, and migration changes.
- Do not log raw URLs, generated configs, `.sbclient` payloads, Telegram tokens,
  or proxy credentials.
- Do not restart `singbox-manager.service` or `sing-box.service` unless the user
  explicitly asks for it.
