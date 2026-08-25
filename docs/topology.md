# Relay Topology

This is a manual inventory model for a small trusted setup. It is not a 3x-ui
control plane and it does not change generated configs or user delivery.

## First Supported Shape

```text
client or managed user config -> RU 3x-ui inbound -> upstream exit nodes
```

The managed Linux host can also use an upstream exit node directly. That is a
local deploy choice and does not change what managed users receive.

## Node Roles

Stored nodes can carry an optional `topology_role`:

| Role | Meaning |
| --- | --- |
| unset | ordinary imported node, no topology claim |
| `entry_relay` | exported 3x-ui inbound used as the client entry |
| `upstream_exit` | node behind the relay, used as an exit |

The role is an operator label. It does not:

- change sing-box JSON generation;
- change Telegram or web artifact delivery;
- filter config-group membership;
- contact 3x-ui or store panel credentials.

Config groups are still chosen by hand. Managed users usually receive the
`entry_relay` link, not the upstream exits.

## Operator Workflow

1. Export the 3x-ui inbound as a normal `vless://` or `hysteria2://` URL.
2. Import it on the Nodes page and mark it `entry_relay`.
3. Import upstream exits the same way and mark them `upstream_exit` if that
   helps you tell them apart.
4. Put the entry relay in the managed group that users should receive.
5. Activate an upstream exit on the Linux host only if that host should bypass
   the relay.

Keep notes and country/provider fields for anything the role does not capture.

## Out Of Scope

- storing 3x-ui panel credentials
- calling the 3x-ui API
- provisioning or rotating inbounds from this app
- server-side enforcement of already distributed client credentials
