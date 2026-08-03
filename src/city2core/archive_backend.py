"""M5 encrypted archive backends; all Walrus writes are disabled by default."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from typing import Any, Callable

from .archive import _file_sha, _sign, _verify, restore_backup, verify_backup
from .model import canonical_json, sha256_bytes, utc_now
from .schema import validate_named
from .store import IntegrityError, StoreError


def _age_binary(name: str) -> str:
    root = os.environ.get("CITY2_AGE_BIN")
    path = str(Path(root) / name) if root else shutil.which(name)
    if not path or not Path(path).is_file():
        raise StoreError(f"{name} is required; install pinned age tooling")
    return path


def generate_age_identity(identity: str | Path) -> str:
    path = Path(identity)
    if path.exists():
        raise StoreError(f"refusing to overwrite age identity: {path}")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    result = subprocess.run(
        [_age_binary("age-keygen"), "-o", str(path)], capture_output=True, text=True
    )
    if result.returncode:
        raise StoreError("age-keygen failed")
    os.chmod(path, 0o600)
    public = subprocess.run(
        [_age_binary("age-keygen"), "-y", str(path)], capture_output=True, text=True
    )
    if public.returncode or not public.stdout.strip().startswith("age1"):
        raise StoreError("age public-key derivation failed")
    return public.stdout.strip()


def _deterministic_tar(source: Path, output: Path) -> None:
    with tarfile.open(output, "w") as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            info = archive.gettarinfo(str(path), arcname=str(relative))
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            with path.open("rb") as handle:
                archive.addfile(info, handle)


def seal_archive(
    archive_dir: str | Path,
    ciphertext: str | Path,
    *,
    recipient: str,
    key_version: str,
    checkpoint_signing_key: str | Path,
    checkpoint_public_key: str | Path,
) -> dict[str, Any]:
    source = Path(archive_dir)
    checkpoint, manifest = verify_backup(
        source, trusted_public_key=checkpoint_public_key
    )
    output = Path(ciphertext)
    if output.exists():
        raise StoreError(f"refusing to overwrite ciphertext: {output}")
    with tempfile.NamedTemporaryFile(prefix="city2-inner-", suffix=".tar") as inner:
        _deterministic_tar(source, Path(inner.name))
        result = subprocess.run(
            [_age_binary("age"), "-r", recipient, "-o", str(output), inner.name],
            capture_output=True,
        )
    if result.returncode:
        output.unlink(missing_ok=True)
        raise StoreError("age encryption failed")
    os.chmod(output, 0o600)
    manifest_sha = _file_sha(source / "manifest.json")
    envelope = {
        "schema_version": "city2.archive-envelope/v1",
        "archive_id": manifest["archive_id"],
        "snapshot_sequence": max(1, int(checkpoint["event_high_water"])),
        "cipher_profile": "age-v1-x25519",
        "recipient_fingerprints": ["sha256:" + sha256_bytes(recipient.encode())],
        "key_versions": [key_version],
        "inner_manifest_sha256": manifest_sha,
        "checkpoint_sha256": _file_sha(source / "checkpoint.json"),
        "ciphertext_sha256": _file_sha(output),
        "created_at": utc_now(),
    }
    validate_named(envelope, "archive-envelope.schema.json")
    signature = base64.urlsafe_b64encode(
        _sign(Path(checkpoint_signing_key), canonical_json(envelope).encode())
    ).rstrip(b"=")
    encoded_signature = signature.decode()
    verify_archive_envelope(
        envelope,
        encoded_signature,
        trusted_public_key=checkpoint_public_key,
    )
    return {"envelope": envelope, "signature": encoded_signature}


def _signed_receipt(
    envelope: dict[str, Any],
    *,
    backend: str,
    backend_object_id: str,
    signing_key: str | Path,
    key_version: str,
    storage_end_epoch: int | None = None,
) -> dict[str, Any]:
    now = utc_now()
    receipt = {
        "schema_version": "city2.archive-receipt/v1",
        "archive_id": envelope["archive_id"],
        "backend": backend,
        "backend_object_id": backend_object_id,
        "ciphertext_sha256": envelope["ciphertext_sha256"],
        "snapshot_sequence": envelope["snapshot_sequence"],
        "stored_at": now,
        "verified_at": now,
        "checkpoint_key_version": key_version,
        "signature_algorithm": "ed25519",
    }
    if storage_end_epoch is not None:
        receipt["storage_end_epoch"] = storage_end_epoch
    signature = _sign(Path(signing_key), canonical_json(receipt).encode())
    receipt["signature"] = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    validate_named(receipt, "archive-receipt.schema.json")
    return receipt


def verify_archive_receipt(
    receipt: dict[str, Any],
    envelope: dict[str, Any],
    *,
    trusted_public_key: str | Path,
) -> None:
    validate_named(receipt, "archive-receipt.schema.json")
    if any(
        receipt[field] != envelope[field]
        for field in ("archive_id", "ciphertext_sha256", "snapshot_sequence")
    ):
        raise IntegrityError("archive receipt does not match envelope")
    unsigned = {key: value for key, value in receipt.items() if key != "signature"}
    encoded = receipt["signature"]
    try:
        signature = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        _verify(Path(trusted_public_key), canonical_json(unsigned).encode(), signature)
    except (ValueError, StoreError) as error:
        raise IntegrityError("archive receipt signature verification failed") from error


def verify_archive_envelope(
    envelope: dict[str, Any],
    signature: str,
    *,
    trusted_public_key: str | Path,
) -> None:
    validate_named(envelope, "archive-envelope.schema.json")
    try:
        raw_signature = base64.urlsafe_b64decode(
            signature + "=" * (-len(signature) % 4)
        )
        _verify(
            Path(trusted_public_key),
            canonical_json(envelope).encode(),
            raw_signature,
        )
    except (ValueError, StoreError) as error:
        raise IntegrityError(
            "archive envelope signature verification failed"
        ) from error


def restore_encrypted_archive(
    ciphertext: str | Path,
    envelope: dict[str, Any],
    signature: str,
    *,
    identity: str | Path,
    checkpoint_public_key: str | Path,
    destination: str | Path,
) -> dict[str, Any]:
    cipher = Path(ciphertext)
    verify_archive_envelope(
        envelope, signature, trusted_public_key=checkpoint_public_key
    )
    if _file_sha(cipher) != envelope["ciphertext_sha256"]:
        raise IntegrityError("ciphertext hash mismatch")
    destination_path = Path(destination)
    if destination_path.exists() and any(destination_path.iterdir()):
        raise StoreError("encrypted restore destination is not empty")
    destination_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="city2-decrypted-", suffix=".tar") as inner:
        result = subprocess.run(
            [
                _age_binary("age"),
                "-d",
                "-i",
                str(identity),
                "-o",
                inner.name,
                str(cipher),
            ],
            capture_output=True,
        )
        if result.returncode:
            raise IntegrityError("age decryption failed")
        with tarfile.open(inner.name) as archive:
            for member in archive.getmembers():
                target = (destination_path / member.name).resolve()
                if (
                    destination_path.resolve() not in target.parents
                    or not member.isfile()
                ):
                    raise IntegrityError("unsafe archive member")
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise IntegrityError("unreadable archive member")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    if (
        _file_sha(destination_path / "manifest.json")
        != envelope["inner_manifest_sha256"]
    ):
        raise IntegrityError("inner manifest substitution")
    if _file_sha(destination_path / "checkpoint.json") != envelope["checkpoint_sha256"]:
        raise IntegrityError("inner checkpoint substitution")
    restored = destination_path / "restored"
    return restore_backup(
        destination_path, restored, trusted_public_key=checkpoint_public_key
    )


class LocalArchiveBackend:
    def __init__(
        self,
        root: str | Path,
        *,
        signing_key: str | Path,
        key_version: str,
    ) -> None:
        self.root = Path(root)
        self.signing_key = Path(signing_key)
        self.key_version = key_version
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def put(self, ciphertext: Path, envelope: dict[str, Any]) -> dict[str, Any]:
        validate_named(envelope, "archive-envelope.schema.json")
        if _file_sha(ciphertext) != envelope["ciphertext_sha256"]:
            raise IntegrityError("local archive input hash mismatch")
        target = self.root / f"{envelope['archive_id']}.age"
        if not target.exists():
            shutil.copyfile(ciphertext, target)
            os.chmod(target, 0o600)
        if _file_sha(target) != envelope["ciphertext_sha256"]:
            raise IntegrityError("local archive post-write hash mismatch")
        return _signed_receipt(
            envelope,
            backend="local-filesystem",
            backend_object_id=target.name,
            signing_key=self.signing_key,
            key_version=self.key_version,
        )

    def get(self, receipt: dict[str, Any]) -> bytes:
        value = (self.root / Path(receipt["backend_object_id"]).name).read_bytes()
        if sha256_bytes(value) != receipt["ciphertext_sha256"]:
            raise IntegrityError("local archive retrieval hash mismatch")
        return value


class WalrusTestnetBackend:
    """Injected-transport adapter; network writes require explicit enablement."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        put: Callable[[bytes, int], dict[str, Any]] | None = None,
        get: Callable[[str], bytes] | None = None,
        status: Callable[[str], dict[str, Any]] | None = None,
        signing_key: str | Path | None = None,
        key_version: str | None = None,
    ) -> None:
        self.enabled, self._put, self._get, self._status = enabled, put, get, status
        self.signing_key = Path(signing_key) if signing_key else None
        self.key_version = key_version

    def store(
        self,
        ciphertext: bytes,
        envelope: dict[str, Any],
        *,
        epochs: int,
        current_epoch: int,
        operation_approved: bool = False,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise StoreError("Walrus Testnet writes are disabled")
        if not operation_approved:
            raise StoreError("Walrus Testnet operation approval is required")
        if not self._put or not self._get or epochs < 1:
            raise StoreError("Walrus Testnet transport/retention unavailable")
        if not self.signing_key or not self.key_version:
            raise StoreError("archive receipt signing is unavailable")
        validate_named(envelope, "archive-envelope.schema.json")
        if sha256_bytes(ciphertext) != envelope["ciphertext_sha256"]:
            raise IntegrityError("Walrus archive input hash mismatch")
        result = self._put(ciphertext, epochs)
        blob_id = result["blob_id"]
        status = self.status(blob_id)
        end_epoch = int(status["end_epoch"])
        if (
            not status.get("certified")
            or status.get("deletable")
            or end_epoch <= current_epoch
        ):
            raise IntegrityError("Walrus blob is not certified permanent storage")
        if self.retrieve(blob_id, envelope["ciphertext_sha256"]) != ciphertext:
            raise IntegrityError("Walrus retrieval content mismatch")
        return _signed_receipt(
            envelope,
            backend="walrus-testnet",
            backend_object_id=blob_id,
            signing_key=self.signing_key,
            key_version=self.key_version,
            storage_end_epoch=end_epoch,
        )

    def retrieve(self, blob_id: str, expected_sha256: str) -> bytes:
        if not self._get:
            raise StoreError("independent Walrus aggregator unavailable")
        value = self._get(blob_id)
        if sha256_bytes(value) != expected_sha256:
            raise IntegrityError("Walrus retrieval hash mismatch")
        return value

    def status(self, blob_id: str) -> dict[str, Any]:
        if not self._status:
            raise StoreError("Walrus status proof unavailable")
        return self._status(blob_id)

    @staticmethod
    def renewal_required(current_epoch: int, end_epoch: int) -> bool:
        return end_epoch - current_epoch <= 2


def enforce_retention_fallback(
    walrus: WalrusTestnetBackend,
    receipt: dict[str, Any],
    *,
    current_epoch: int,
    ciphertext: Path,
    envelope: dict[str, Any],
    fallback: LocalArchiveBackend,
) -> dict[str, Any]:
    """Guarantee a second verified copy before the Walrus renewal deadline."""
    try:
        status = walrus.status(receipt["backend_object_id"])
        end_epoch = int(status["end_epoch"])
    except (KeyError, TypeError, ValueError, StoreError):
        local = fallback.put(ciphertext, envelope)
        return {
            "state": "fallback_written",
            "reason": "availability_unverified",
            "local": local,
        }
    if not status.get("certified") or current_epoch >= end_epoch:
        local = fallback.put(ciphertext, envelope)
        return {
            "state": "fallback_written",
            "reason": "walrus_unavailable",
            "local": local,
        }
    if walrus.renewal_required(current_epoch, end_epoch):
        local = fallback.put(ciphertext, envelope)
        return {
            "state": "fallback_written",
            "reason": "renewal_required",
            "local": local,
        }
    return {"state": "available", "end_epoch": end_epoch}
