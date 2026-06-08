# Contributing

This is a small local utility. Keep changes focused and proportional to the
problem being solved.

## Setup

```bash
make dev-install
```

## Checks

Run the smallest useful set before opening a PR:

```bash
make lint
make test
```

Run e2e tests when changing templates, browser flows, deploy behavior, routing,
or diagnostics:

```bash
make e2e
```

## Change Guidelines

- Keep feature changes separate from broad refactors.
- Add tests for deploy, auth, Telegram, routing, distribution, and migration
  changes.
- Update docs when behavior, commands, settings, or limitations change.
- Do not add speculative abstractions or placeholder extension points.
- Do not include proxy URLs, tokens, `.env`, local databases, or generated
  caches in commits.
