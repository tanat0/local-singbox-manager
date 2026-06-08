# Security

This project is a local-first manager for a small trusted sing-box setup. It is
not designed to be exposed directly to the Internet.

## Supported Scope

Security reports should focus on the current local manager:

- web UI auth, sessions, and CSRF behavior
- unsafe handling of proxy URLs, tokens, or environment values
- privileged helper and sudoers behavior
- generated sing-box config safety
- local database or log exposure

## Sensitive Data

Proxy URLs, Telegram tokens, ntfy topics, session secrets, raw logs, and
`singbox_manager.db` contents may contain sensitive data. Do not post them in
public issues.

## Reporting

Open a minimal GitHub issue asking for a private contact path. Do not include
secrets, credentials, full proxy URLs, private logs, or exploit details in the
public issue.

## Deployment Boundary

The default deployment binds to `127.0.0.1` and the systemd template adds a
loopback-only network guard. If you expose the panel through a reverse proxy,
that proxy becomes part of your security boundary. Use TLS, enable
`SINGLE_ADMIN_PASSWORD`, keep `SESSION_SECRET` stable and private, and do not
publish the panel without understanding that changed threat model.
