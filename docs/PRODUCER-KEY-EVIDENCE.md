# M6 ai-infra shadow signing-key evidence

Observed on `2026-08-03`. This records one-time shadow signer provisioning, not
a producer observation or M6 acceptance.

## Key contract

- key version: `ai-infra-shadow-1`;
- algorithm: Ed25519;
- public-key DER SHA-256:
  `2858eb9727bf82f98d7b2d18352df21a7aff9b51c7a758104d2620cc1a9b0da5`;
- private path: systemd credential source under `/etc/city2/producer`;
- private mode/owner: `0600`, root-only;
- public mode: `0644`;
- private key copied off worker: **no**;
- public key captured in source: `config/producer-observer.ai-infra.pub`.

The public key derived independently from the private key matched the captured
public fingerprint. The private key is intentionally one-time: after the shadow
evidence/removal proof, destroy it and retain the public key for verification.

## Closed gates during provisioning

```text
manifests=disabled
unit=static,inactive
source_sha256_before=1df93c43ab1223489b8cbf1a7e70949913f02ca988dd3f9725b91ed724c70a7d
source_sha256_after=1df93c43ab1223489b8cbf1a7e70949913f02ca988dd3f9725b91ed724c70a7d
private_key_copied=no
```

No service, identity, schedule, database or producer output changed. Source now
binds the trusted key version/fingerprint and rejects key substitution before
any manual shadow run.
