# Archive backend contract v1

Archive backends store already-encrypted bytes. They never receive plaintext,
recipient private keys or authority to create a wallet transaction.

```text
put(envelope, ciphertext, operation_approval) -> city2.archive-receipt/v1
get(receipt) -> ciphertext
verify(receipt) -> verification_receipt
extend(receipt, retention, operation_approval) -> city2.archive-receipt/v1
delete(receipt, deletion_order) -> deletion_receipt | unsupported
```

The backend MUST verify the ciphertext hash before and after storage. `get`
returns exact bytes; Core independently checks the receipt signature,
ciphertext hash, archive ID and checkpoint continuity before decrypting.
`extend` is a new exact operation and cannot reuse an approval whose backend,
blob set, epoch window, spend or execution count changed.

Receipts are minimal, signed, backend-neutral availability records. Backend
attributes are confined to `backend` and `backend_object_id`; a missing storage
end epoch means the backend does not expose epoch retention. An inability to
prove availability returns `verification_failed`, never success based only on a
provider response.

Stable errors are `hash_mismatch`, `object_missing`, `verification_failed`,
`retention_unsupported`, `approval_denied`, `budget_exceeded`,
`backend_unavailable` and `delete_unsupported`. Unknown post-dispatch outcomes
are reconciled before retry.

The local encrypted backend is the recovery baseline. Walrus is one optional
implementation and cannot change these contracts or become the only usable
off-host copy while renewal is pending.
