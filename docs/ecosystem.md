# Ecosystem Boundaries

This project is one part of a small personal sing-box setup. The goal is to keep
each repository focused while still making the handoff between them explicit.

## Repositories

### local-singbox-manager

This repository is the admin/operator tool.

It owns:

- local node, profile, group, user, and delivery-log state;
- generated sing-box config for the managed Linux host;
- deploy, rollback, diagnostics, and helper checks;
- Telegram delivery of raw links, generic sing-box JSON, and `.sbclient`
  bundles.

It should not own Windows or Android UI/runtime behavior.

### singbox-client

`/home/nikita/Documents/projects/own/singbox-client/` is the end-user client
project.

It owns:

- importing `.sbclient` bundles and raw proxy URLs;
- platform-specific profile storage;
- platform-specific sing-box config generation;
- Windows connection lifecycle and Android VPN lifecycle when implemented;
- user-facing error messages for non-technical users.

It should not know about the manager database, deploy pipeline, Telegram admin
commands, or operator-only diagnostics.

### 3x-ui Relay Host

A RU 3x-ui host can be part of the topology as a relay entry. Exported 3x-ui
links are ordinary imported nodes. Optional `topology_role` labels mark which
stored links are entry relays and which are upstream exits. See
[topology.md](topology.md).

Initial model:

```text
client or managed user config -> RU 3x-ui inbound -> upstream exit nodes
```

Out of scope for now:

- storing 3x-ui panel credentials;
- calling the 3x-ui API;
- managing upstream server inventory through the panel;
- claiming server-side enforcement for already distributed client credentials.

## Shared Surface

Only a small surface should cross repository boundaries:

- raw VLESS/Hysteria2/Hy2 URLs;
- generic sing-box JSON for clients that can import it directly;
- `.sbclient` schema v1 for the companion client app;
- route preset IDs: `full_tunnel`, `bypass_lan`, `bypass_ru`;
- current transport compatibility expectations.

Do not introduce a shared package until duplicated parser or generator behavior
creates real maintenance cost. For now, shared fixtures and contract docs are a
better fit than a premature library.

## Practical Workflow

1. The operator imports or stores nodes in `local-singbox-manager`.
2. The operator assigns selected nodes and a route preset to a managed group.
3. Managed users receive raw links, generic sing-box JSON, or a `.sbclient`
   bundle through Telegram. The operator can also download the same artifacts
   from the Users page.
4. `singbox-client` imports the `.sbclient` bundle and generates platform-local
   sing-box config from the raw URLs.
5. 3x-ui relay links are imported as normal nodes. Mark them `entry_relay` or
   `upstream_exit` when that helps you keep the inventory straight. Put the
   entry relay in the managed group that users should receive.

## Coordination Rules

- When `.sbclient` changes, update this repo's `docs/client-contract.md` and the
  client repo's `docs/client-bundle-v1.md`.
- When transport support changes, update both config generators or explicitly
  document the gap.
- Keep raw URL fallback available until real Windows and Android import testing
  proves the generated artifacts are usable.
- Keep topology metadata descriptive. `topology_role` does not drive generation
  or delivery. Add 3x-ui automation only after the manual workflow is clear.
