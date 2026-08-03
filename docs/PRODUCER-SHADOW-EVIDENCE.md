# M6 ai-infra signed shadow and removal evidence

Accepted on `2026-08-03`. This records the single live M6 shadow transaction,
its independent Buzz attestation and complete rollback. It does not authorize a
persistent observer or another producer.

## Bound inputs

- merged source before the transaction: `main` at `78f6c1a`;
- City2 version: `0.8.7`;
- observer bundle SHA-256:
  `7906c5cf960de104f676d77d828964eb9c7fea28b78dc69e1b78f474df8d8044`;
- producer: `ai-infra`;
- exact source SHA-256:
  `1df93c43ab1223489b8cbf1a7e70949913f02ca988dd3f9725b91ed724c70a7d`;
- signer key version: `ai-infra-shadow-1`;
- signer public-key DER SHA-256:
  `2858eb9727bf82f98d7b2d18352df21a7aff9b51c7a758104d2620cc1a9b0da5`.

## Signed observation

The reviewed disabled manifest copies were enabled atomically for one manual
start of the static oneshot unit. The unit observed only the read-only bound
aggregate and emitted `city2.producer-observation/v1` at
`2026-08-03T05:27:58.408530Z`.

```text
observation_sha256=f166e829f48c76210530a45f227d0fed7ad78d00eaf5cde2ada8f0de3c51f33b
source_sha256=1df93c43ab1223489b8cbf1a7e70949913f02ca988dd3f9725b91ed724c70a7d
byte_length=6960
freshness_seconds=57477
freshness_state=current
signature_algorithm=ed25519
signer_key_version=ai-infra-shadow-1
authority_touch.source_write=false
authority_touch.database=false
authority_touch.schedule=false
```

The signature was verified independently against the captured public key. No
source content was copied into City2 or model context. The installed manifest
copies were disabled immediately after the run.

## Narrow Buzz attestation

A fresh evidence-publisher identity was admitted to the closed relay as a
member, added only to a new private M6 evidence channel and used to post the
observation, signer and unchanged-source hashes. The existing coordinator read
back the exact signed event independently.

```text
attested_at=2026-08-03T05:36:08Z
publisher_pubkey_sha256=adf9b83f6a5a2b92a95a79b6740bd087be2ba89f609a9901b15c3de73cbf8e23
channel_id_sha256=d77dd80a03c18cd96919b72c32b4ea189ff9600835ef31b04e76b303cedb5743
summary_sha256=ecb3f83b01cea60f4c8d953dc9afaf16d22472e375c4401f3879af9154b31a88
operator_proof_sha256=e8be1fa2095fdbf9c7e0db256d40e5612f028ef4c45f6626567b9e3a57ed7055
```

The publisher was then removed from the channel and closed relay, its private
identity files were destroyed, and the private channel was archived. The
coordinator recovered the same event after those steps. Because local Tailscale
was logged out, a turn-scoped local route to the already-bound private relay was
used and removed by the transaction; relay exposure did not change. Exact
private channel state and the operator receipt remain off-repository.

## Removal and invariance

The observer unit, `/opt/city2` observer runtime, installed manifests, public
and private signer files, evidence state and staging files were removed. A
daemon reload confirmed the unit `not-found`; the one-time private signer no
longer exists.

The producer aggregate hash matched before and after. The producer schedule
hash and database size/mtime comparisons were unchanged. A fresh fleet probe
then reported all 15 active producer contracts healthy through the existing LAN
fallback. The only host warning remained the pre-existing disk-headroom floor.
No downstream system consumed or depended on observer evidence.

## Exit decision

M6 exit criteria pass:

- existing output remained unchanged;
- signed provenance, freshness and independently retained attestation added
  measurable evidence; and
- failure/removal did not interrupt the producer or downstream systems.

M7 may now be evaluated one unit at a time. No M7 role, authority or deployment
is authorized by this acceptance record.
