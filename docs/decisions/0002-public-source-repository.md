# 0002 — Publish the City2 source repository

- **Status:** accepted
- **Date:** 2026-08-01
- **Supersedes:** the repository-visibility portion of 0001

## Context

City2 began in a private repository while the clean control plane, Buzz relay
packaging and first coordinator boundary were established. The repository now
contains reusable public architecture, validation and deployment tooling.

Before changing visibility, every reachable branch and historical blob was
scanned for private keys, credential tokens and private host addresses. No such
material was found. Runtime `.env` files, identities, state databases, backups
and generated credentials are ignored and remain outside Git.

## Decision

Make `P-U-C/city2` publicly readable. Keep the production Buzz relay, private
channels, identities, runtime configuration and backup material private.

Repository visibility does not change any agent authority, relay exposure,
producer contract or deployment gate.

## Consequences

- Source, branches, pull requests and history are publicly readable.
- Public changes can be reviewed across model and harness providers.
- The repository's credential and private-address scan remains a required
  validation gate.
- Operational evidence must use sanitized facts and pointers rather than copied
  runtime configuration.
- Any future discovery of sensitive committed data requires immediate access
  review, credential rotation where applicable and history remediation.
