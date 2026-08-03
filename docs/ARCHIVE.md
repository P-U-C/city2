# Encrypted archive pilot — M5

M5 adds a generic encrypted archive boundary and local recovery baseline. It
does not install Walrus, create a wallet, upload a blob, spend Testnet tokens or
perform any Mainnet action.

## Encryption and local recovery

`archive_backend.py` creates a deterministic inner tar from the barrier-
consistent M1 backup, encrypts it with the unmodified age v1 X25519 format and
signs the outer envelope with the independent Ed25519 checkpoint key. Restore
verifies the signature, ciphertext hash, safe archive paths, inner manifest,
checkpoint, event range and SQLite integrity before returning a database.

The real local proof uses pinned age v1.3.1. `scripts/build-archive-tools.sh`
downloads the official Linux release and verifies its published SHA-256 before
placing binaries in ignored `build/archive-tools/`. Identities and ciphertext
remain outside Git and are deleted with the synthetic test directory.

## Walrus Testnet adapter

`WalrusTestnetBackend` accepts injected transports and is disabled by default.
Enabling it still requires an operator-controlled Testnet publisher/wallet. It
also requires an exact operation approval, accepts only already-encrypted bytes,
requires a certified, unexpired, non-deletable status proof, retrieves through
an independent aggregator and checks the exact ciphertext hash. Backend-neutral
availability receipts are signed by the checkpoint key. Unknown or unverified
outcomes fail closed.

The adapter follows the current official stable paths: publisher
`PUT /v1/blobs`, aggregator `GET /v1/blobs/<BLOB_ID>`, mandatory epoch retention
and independent `blob-status`/onchain certification checks. See the
[Walrus network reference](https://docs.wal.app/docs/network-reference),
[storage API](https://docs.wal.app/docs/http-api/storing-blobs) and
[availability verification](https://docs.wal.app/docs/walrus-client/verifying-availability).

At two epochs from expiry, or immediately on failed certification/expiry,
`enforce_retention_fallback` writes a verified second copy to the local backend.
No workflow may treat a pending renewal as the only usable copy.

## Evidence and remaining gate

`tests/test_archive_backend.py` proves real age encryption/decryption, signed
checkpoint continuity, empty-directory SQLite restore, ciphertext tamper
rejection, disabled Testnet writes, ciphertext-only transport, independent
retrieval hash checks, certified permanence and expiry fallback.

The live Walrus Testnet upload/retrieval criterion remains open because this
host has no approved synthetic wallet/tooling. Mainnet remains prohibited until
Chad explicitly reviews Testnet evidence, cost and recovery.
