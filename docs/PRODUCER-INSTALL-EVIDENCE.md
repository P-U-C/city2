# M6 ai-infra disabled install evidence

Observed at `2026-08-03T05:16:54Z`. This records a persistent **disabled-only**
worker install. It is not a shadow observation or M6 acceptance.

## Approved scope

- merged source: `main` at `d52150f`;
- City2 version: `0.8.5`;
- installed bundle SHA-256:
  `948da705117d2f316f1f0d773803f1c97f79aba0c7fbf41beff02c09311641ad`;
- installed: root-owned runtime code, schemas, two disabled manifests, static
  unit, bundle manifest and removal plan;
- excluded: signing key, Buzz identity, environment file, producer content,
  database, schedule, service enable/start and Core routing.

## Transaction

The bundle was copied to a random worker `/tmp` directory, verified, extracted
and checked against `MANIFEST.sha256`. Target collisions were denied. Exact
files were installed under `/opt/city2/lib/city2`, `/etc/city2/producer` and
`/etc/systemd/system`; all are root-owned. `systemctl daemon-reload` registered
the unit without enabling or starting it. The temporary directory was removed.
The transaction included automatic rollback of those exact targets on failure.

## Post-install proof

```text
installed_files_verified=43
manifests=disabled
credential=absent
unit=static,inactive
source_sha256_before=1df93c43ab1223489b8cbf1a7e70949913f02ca988dd3f9725b91ed724c70a7d
source_sha256_after=1df93c43ab1223489b8cbf1a7e70949913f02ca988dd3f9725b91ed724c70a7d
staging=removed
```

Every installed payload file was re-hashed against the bundle manifest. The
producer source remained unchanged. No model or producer content was invoked.

## Remaining gates

- explicit approval for one-time signing-key creation and public-key capture;
- enable reviewed worker manifest copies for one manual run only;
- create the distinct narrow Buzz identity/channel path;
- run and independently verify one signed shadow observation;
- disable/remove the observer and prove producer/downstream invariance.

The signing-key and shadow-run transaction is not authorized by this evidence.
