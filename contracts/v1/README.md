# City2 v1 contract set

This directory defines behavior at replaceable boundaries. The canonical data
shapes are the JSON Schemas in [`../../schemas/v1`](../../schemas/v1); interface
documents here define semantics that JSON Schema cannot express.

## Encoding and hashing

- Exchange objects are UTF-8 JSON and MUST round-trip without information loss.
- Canonical JSON uses RFC 8785 JSON Canonicalization Scheme (JCS).
- A top-level immutable-object digest is SHA-256 over its canonical JSON with
  the exclusions in the profile table below.
- `payload_sha256` hashes only canonical `payload`; `parameters_sha256` hashes
  only canonical `canonical_parameters`; artifact hashes cover exact bytes.
- Hashes are lowercase hexadecimal. Implementations MUST reject a supplied
  digest that does not match the recomputed value.
- Optional fields are omitted. `null` is not a substitute unless a schema
  explicitly permits it.

### Digest profiles

| Digest | Canonical input exclusions |
|---|---|
| `manifest_sha256` (`city2.agent/v1`) | `manifest_sha256`, `aggregate_version` |
| `objective_sha256` | `objective_sha256`, `aggregate_version`, `status` |
| `task_envelope_sha256` | `task_envelope_sha256` |
| `approval_sha256` | `approval_sha256`, `aggregate_version`, `executions_consumed`, `revocation_state`, `revoked_at`, `revoked_by` |
| `order_sha256` (`city2.deletion-order/v1`) | `order_sha256`, `aggregate_version`, `state`, `targets`, `proof_sha256`, `completed_at` |
| `manifest_sha256` (`city2.runner-capability/v1`) | `manifest_sha256` |
| `pack_sha256` (`city2.context-pack/v1`) | `pack_sha256` |

Excluded mutable fields remain protected by optimistic concurrency and the
event payload/hash chain. Every other top-level field is included, whether
required or optional. `payload_sha256`, `parameters_sha256`, artifact hashes,
source hashes and ciphertext hashes retain the narrower byte/object definitions
above.

## Compatibility

`schema_version` is the dispatch key. A consumer MUST reject unknown major
versions and MUST NOT silently discard unknown properties. A producer changing
meaning or removing a field creates a new major version. Additive changes use a
new explicitly supported schema version; they are not smuggled into `v1`.

Canonical IDs are allocated only by Core. Adapters may provide namespaced
idempotency keys, never canonical IDs. Schema validation is necessary but does
not grant authority or prove semantic validity.

## Security boundary

Canonical objects may contain credential **handles**, public fingerprints and
content hashes. They MUST NOT contain secret values, provider session state,
hidden model state or an interface-specific conversation as authority.

Interfaces:

- [Runner](RUNNER.md)
- [CredentialBroker](CREDENTIAL-BROKER.md)
- [Archive backend](ARCHIVE-BACKEND.md)
- [Authority evaluator](AUTHORITY.md)
