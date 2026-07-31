# 0001 — Start City2 in a clean repository

- **Status:** accepted
- **Date:** 2026-07-31

## Context

Legacy City control state is spread across OpenClaw-era workspaces, historical
harness repositories and live producer systems. The OpenClaw workspace has
large amounts of generated and mutable state and is no longer a trustworthy
foundation for an overhaul.

## Decision

Create a new private `P-U-C/city2` repository. Preserve live producer/data
contracts, treat legacy workspaces as read-only evidence and use PfTerminal as
the new operating harness. Add Buzz as a private coordination layer.

## Consequences

- Clean reviewable history and explicit ownership.
- No hidden dependency on OpenClaw prompts, gateway or heartbeat.
- Existing producers continue while migration is measured.
- Useful legacy behavior must be intentionally documented or ported.
- Runtime retirement remains a separate approved operation.
