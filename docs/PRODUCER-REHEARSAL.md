# M6 ai-infra bundle rehearsal evidence

Observed at `2026-08-03T05:12:22Z`. This is a content-free, disposable staging
proof—not a producer observer deployment.

## Inputs

- merged source: `main` at `de5522c`;
- City2 version: `0.8.4`;
- bundle:
  `build/producer-observer/city2-producer-observer-ai-infra.tar.gz`;
- bundle SHA-256:
  `7d8e8494a7c1ee529deb0252156a052c7221e6c94828e3db7e555b951a47d117`;
- worker path: serial fleet fallback `city-worker-lan`;
- producer source: the exact aggregate declared in the disabled contract.

## Procedure and results

1. Created a random `/tmp/city2-observer-rehearsal.*` directory on worker-1.
2. Hashed the producer aggregate as `ai-infra`.
3. Copied only the credential-free bundle into the temporary directory.
4. Verified the archive SHA-256 and every `MANIFEST.sha256` entry.
5. Verified both packaged manifests remained disabled.
6. Verified the unit with an isolated `SYSTEMD_UNIT_PATH`.
7. Proved no key, environment or SQLite file existed in the bundle.
8. Re-hashed the producer aggregate as `ai-infra`.
9. Removed the complete temporary directory and verified it no longer existed.

Results:

```text
manifests=disabled
inventory=verified
credentials=absent
source_sha256_before=1df93c43ab1223489b8cbf1a7e70949913f02ca988dd3f9725b91ed724c70a7d
source_sha256_after=1df93c43ab1223489b8cbf1a7e70949913f02ca988dd3f9725b91ed724c70a7d
cleanup=verified
```

No producer content was printed or copied into City2/model context. No system
path, service, schedule, database, identity, credential or downstream output
was created or changed.

## Remaining live gates

- explicit approval for a persistent disabled bundle install;
- independent review of the exact install/removal transaction;
- separate signing-key creation and recovery handling;
- distinct narrow Buzz identity/channel membership;
- manually started signed shadow observation;
- independent evidence verification and complete removal proof.

M6 and M7 remain unaccepted until those gates pass.
