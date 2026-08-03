import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from city2core import Core, Store  # noqa: E402
from city2core.archive import create_backup, generate_checkpoint_key  # noqa: E402
from city2core.archive_backend import (  # noqa: E402
    LocalArchiveBackend,
    WalrusTestnetBackend,
    enforce_retention_fallback,
    generate_age_identity,
    restore_encrypted_archive,
    seal_archive,
    verify_archive_envelope,
    verify_archive_receipt,
)
from city2core.store import IntegrityError, StoreError  # noqa: E402


class ArchiveBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="city2-archive-test-"))

    def tearDown(self):
        shutil.rmtree(self.temp)

    def test_real_age_encrypted_local_restore(self):
        tools = ROOT / "build" / "archive-tools"
        if not (tools / "age").is_file():
            self.skipTest("run scripts/build-archive-tools.sh for real age proof")
        old = os.environ.get("CITY2_AGE_BIN")
        os.environ["CITY2_AGE_BIN"] = str(tools)
        try:
            db = self.temp / "core.sqlite"
            with Store.initialize(db) as store:
                Core(store).create_objective(
                    {
                        "title": "Archive proof",
                        "intent": "Prove encrypted recovery.",
                        "accountable_owner": "human:chad",
                        "review_at": "2027-08-03T00:00:00Z",
                        "measurable_outcomes": [
                            {
                                "outcome_id": "oc_restore",
                                "measure": "restore",
                                "target": "verified",
                            }
                        ],
                        "stop_conditions": ["Integrity fails."],
                        "authority_ceiling": "A0",
                        "budget": {
                            "max_billable_usd": "0",
                            "max_input_tokens": 0,
                            "max_output_tokens": 0,
                        },
                    },
                    actor="human:chad",
                    idempotency_key="archive:objective:create",
                )
                checkpoint_key = self.temp / "checkpoint.key"
                checkpoint_public = self.temp / "checkpoint.pub"
                generate_checkpoint_key(checkpoint_key, checkpoint_public)
                archive = self.temp / "archive"
                create_backup(
                    store,
                    archive,
                    signing_key=checkpoint_key,
                    key_version="synthetic-v1",
                )
            identity = self.temp / "age-identity.txt"
            recipient = generate_age_identity(identity)
            ciphertext = self.temp / "archive.age"
            sealed = seal_archive(
                archive,
                ciphertext,
                recipient=recipient,
                key_version="synthetic-v1",
                checkpoint_signing_key=checkpoint_key,
                checkpoint_public_key=checkpoint_public,
            )
            verify_archive_envelope(
                sealed["envelope"],
                sealed["signature"],
                trusted_public_key=checkpoint_public,
            )
            manifest = json.loads((archive / "manifest.json").read_text())
            self.assertEqual(sealed["envelope"]["archive_id"], manifest["archive_id"])
            local = LocalArchiveBackend(
                self.temp / "backend",
                signing_key=checkpoint_key,
                key_version="synthetic-v1",
            )
            receipt = local.put(ciphertext, sealed["envelope"])
            verify_archive_receipt(
                receipt,
                sealed["envelope"],
                trusted_public_key=checkpoint_public,
            )
            self.assertEqual(local.get(receipt), ciphertext.read_bytes())
            restored = restore_encrypted_archive(
                ciphertext,
                sealed["envelope"],
                sealed["signature"],
                identity=identity,
                checkpoint_public_key=checkpoint_public,
                destination=self.temp / "recovery",
            )
            with Store.open(restored["database"]) as store:
                self.assertEqual(store.verify_integrity()["event_high_water"], 1)
            tampered = self.temp / "tampered.age"
            tampered.write_bytes(ciphertext.read_bytes() + b"x")
            with self.assertRaises(IntegrityError):
                restore_encrypted_archive(
                    tampered,
                    sealed["envelope"],
                    sealed["signature"],
                    identity=identity,
                    checkpoint_public_key=checkpoint_public,
                    destination=self.temp / "bad-recovery",
                )
        finally:
            if old is None:
                os.environ.pop("CITY2_AGE_BIN", None)
            else:
                os.environ["CITY2_AGE_BIN"] = old

    def test_walrus_testnet_is_disabled_and_verifies_ciphertext_lifecycle(self):
        payload = b"age-encrypted-only"
        checkpoint_key = self.temp / "checkpoint.key"
        checkpoint_public = self.temp / "checkpoint.pub"
        generate_checkpoint_key(checkpoint_key, checkpoint_public)
        envelope = {
            "schema_version": "city2.archive-envelope/v1",
            "archive_id": "arc_01980000-0000-7000-8000-000000000001",
            "ciphertext_sha256": hashlib.sha256(payload).hexdigest(),
            "snapshot_sequence": 1,
            "cipher_profile": "age-v1-x25519",
            "recipient_fingerprints": ["sha256:" + "0" * 64],
            "key_versions": ["synthetic-v1"],
            "inner_manifest_sha256": "1" * 64,
            "checkpoint_sha256": "2" * 64,
            "created_at": "2026-08-03T00:00:00Z",
        }
        disabled = WalrusTestnetBackend()
        with self.assertRaises(StoreError):
            disabled.store(payload, envelope, epochs=2, current_epoch=7)
        calls = []
        backend = WalrusTestnetBackend(
            enabled=True,
            put=lambda value, epochs: (
                calls.append((value, epochs))
                or {"blob_id": "blob-fixture", "object_id": "object-fixture"}
            ),
            get=lambda blob_id: payload,
            status=lambda blob_id: {
                "certified": True,
                "deletable": False,
                "end_epoch": 10,
            },
            signing_key=checkpoint_key,
            key_version="synthetic-v1",
        )
        with self.assertRaises(StoreError):
            backend.store(payload, envelope, epochs=2, current_epoch=7)
        receipt = backend.store(
            payload,
            envelope,
            epochs=2,
            current_epoch=7,
            operation_approved=True,
        )
        self.assertEqual(calls, [(payload, 2)])
        verify_archive_receipt(receipt, envelope, trusted_public_key=checkpoint_public)
        changed = dict(receipt)
        changed["backend_object_id"] = "different-object"
        with self.assertRaises(IntegrityError):
            verify_archive_receipt(
                changed, envelope, trusted_public_key=checkpoint_public
            )
        self.assertEqual(
            backend.retrieve(
                receipt["backend_object_id"], receipt["ciphertext_sha256"]
            ),
            payload,
        )
        self.assertTrue(backend.renewal_required(8, 10))
        self.assertFalse(backend.renewal_required(7, 10))
        expired = WalrusTestnetBackend(
            enabled=True,
            put=lambda value, epochs: {"blob_id": "expired-fixture"},
            get=lambda blob_id: payload,
            status=lambda blob_id: {
                "certified": True,
                "deletable": False,
                "end_epoch": 7,
            },
            signing_key=checkpoint_key,
            key_version="synthetic-v1",
        )
        with self.assertRaises(IntegrityError):
            expired.store(
                payload,
                envelope,
                epochs=2,
                current_epoch=7,
                operation_approved=True,
            )
        poisoned = WalrusTestnetBackend(get=lambda blob_id: b"plaintext")
        with self.assertRaises(IntegrityError):
            poisoned.retrieve("blob-fixture", receipt["ciphertext_sha256"])
        cipher = self.temp / "fixture.age"
        cipher.write_bytes(payload)
        fallback = LocalArchiveBackend(
            self.temp / "fallback",
            signing_key=checkpoint_key,
            key_version="synthetic-v1",
        )
        state = enforce_retention_fallback(
            backend,
            receipt,
            current_epoch=8,
            ciphertext=cipher,
            envelope=envelope,
            fallback=fallback,
        )
        self.assertEqual(state["state"], "fallback_written")
        self.assertEqual(state["reason"], "renewal_required")

        def unavailable_status(blob_id):
            raise StoreError("status unavailable")

        unavailable = WalrusTestnetBackend(status=unavailable_status)
        state = enforce_retention_fallback(
            unavailable,
            receipt,
            current_epoch=7,
            ciphertext=cipher,
            envelope=envelope,
            fallback=fallback,
        )
        self.assertEqual(state["reason"], "availability_unverified")


if __name__ == "__main__":
    unittest.main()
