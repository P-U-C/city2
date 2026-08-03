# CredentialBroker contract v1

`CredentialBroker` is deterministic infrastructure between policy evaluation
and an approved operation. It is never exposed as a general model tool.

```text
resolve(handle, operation, approval) -> ephemeral_reference | broker_error
rotate(handle, approval) -> rotation_receipt | broker_error
revoke(handle, approval) -> revocation_receipt | broker_error
export_recovery_metadata(approval) -> encrypted_artifact_ref | broker_error
```

`resolve` receives a credential handle, canonical operation parameters and the
exact immutable approval. It MUST:

1. recompute and compare operation hashes;
2. verify target, capability, task revision, policy version, expiry,
   revocation and remaining executions;
3. materialize only the minimum credential through a reviewed ephemeral path;
4. bind the reference to one operation and a short expiry;
5. emit only content-free audit data; and
6. revoke/remove material after use or expiry.

The reference is an opaque broker locator, not the secret. Core, events,
telemetry, logs, model input and result envelopes never receive credential
values. Backend-native names may appear only in backend configuration, not
agent manifests.

Stable errors are `handle_unknown`, `operation_mismatch`, `approval_denied`,
`approval_expired`, `approval_exhausted`, `backend_unavailable`,
`materialization_failed` and `revocation_failed`. Errors fail closed and contain
no value, path containing a value, or backend diagnostic payload.

Conformance proves least-privilege resolution, expiry cleanup, revocation,
rotation, content-free audit and backend replacement from independently
encrypted recovery metadata.
