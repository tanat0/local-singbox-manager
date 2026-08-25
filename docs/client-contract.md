# Client Delivery Contract

This document describes the artifacts that `local-singbox-manager` can deliver
to managed users. It is intentionally smaller than a sync protocol.

## Delivered Artifacts

### Raw Proxy URLs

Raw VLESS/Hysteria2/Hy2 URLs remain the fallback format and the credential source
of truth. They are useful when a client cannot import generated JSON or a
`.sbclient` bundle.

### Generic sing-box JSON

`/config` and `/refresh` prepare a generic sing-box JSON document for clients
that can import a complete sing-box config.

The generated JSON includes:

- assigned group nodes;
- `direct` and `block` outbounds;
- selected group route preset;
- always-on route guards;
- a `selector` outbound named `proxy` when the group has multiple nodes.

This artifact is not a `.sbclient` bundle.

### `.sbclient` Bundle

`/sbclient` prepares an offline import bundle for the companion
`singbox-client` app. The detailed client-side contract lives in
`/home/nikita/Documents/projects/own/singbox-client/docs/client-bundle-v1.md`.

The manager currently builds schema version `1`:

```json
{
  "schema_version": 1,
  "default_profile": "node-tag",
  "profiles": [
    {
      "name": "node-tag",
      "raw_url": "vless://...",
      "dns_preset": "quad9_tls",
      "route_preset": "full_tunnel"
    }
  ]
}
```

Manager-side rules:

- one profile per assigned node;
- profile name comes from the node tag;
- duplicate or invalid profile names fail bundle generation;
- `raw_url` is copied from the stored node and remains the source of truth;
- group `route_preset` is copied to every profile;
- `dns_preset` defaults to `quad9_tls` until group-level DNS exists;
- `default_profile` is deterministic.

The operator can also download the same generic JSON and `.sbclient` files from
the Users page. That is a local authenticated export, not a public download API.

## Validation Behavior

Unsupported transports must fail before an artifact is attached. The Telegram
response should still include safe text and raw fallback links where possible.

Known unsupported generated-config transports:

- XHTTP/SplitHTTP;
- QUIC;
- VLESS `headerType=http`.

Do not silently drop unsupported nodes from a generated artifact. A partial
bundle or partial generated config is harder to reason about than a clear
fallback.

## Security Rules

All delivered artifacts contain proxy credentials.

- Do not log raw URLs, generated JSON, `.sbclient` payloads, or document bytes.
- Do not attach example artifacts to public issues unless credentials are
  synthetic.
- Use safe user-facing errors that do not include raw URLs or tokens.
- Treat Telegram delivery as best effort; a prepared artifact does not prove the
  user imported or used it.

## Non-Goals

- Background client sync.
- Device registration or binding.
- Remote revocation of already delivered credentials.
- Server-side traffic enforcement for client devices.
- 3x-ui panel automation.
- Node `topology_role` labels. Those are operator inventory in this repo, not
  part of the client import contract.
