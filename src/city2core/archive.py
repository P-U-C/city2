"""Barrier-consistent local M1 backups with trusted Ed25519 checkpoints."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from typing import Any
import uuid

from .model import canonical_json, sha256_bytes, sha256_json, utc_now
from .store import IntegrityError, Store, StoreError


ARCHIVE_FILES = {
    "core-snapshot.sqlite",
    "events.jsonl",
    "git-refs.json",
    "manifest.json",
}


def _run_openssl(args: list[str], *, data: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(
            ["openssl", *args], input=data, capture_output=True, check=False
        )
    except FileNotFoundError as error:
        raise StoreError("OpenSSL is required for signed checkpoints") from error
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise StoreError(f"OpenSSL checkpoint operation failed: {message}")
    return result.stdout


def generate_checkpoint_key(private_key: str | Path, public_key: str | Path) -> None:
    private_path = Path(private_key)
    public_path = Path(public_key)
    for path in (private_path, public_path):
        if path.exists():
            raise StoreError(f"refusing to overwrite key: {path}")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _run_openssl(["genpkey", "-algorithm", "ED25519", "-out", str(private_path)])
    os.chmod(private_path, 0o600)
    try:
        _run_openssl(
            ["pkey", "-in", str(private_path), "-pubout", "-out", str(public_path)]
        )
        os.chmod(public_path, 0o644)
    except BaseException:
        private_path.unlink(missing_ok=True)
        public_path.unlink(missing_ok=True)
        raise


def _public_key_der(public_key: Path) -> bytes:
    return _run_openssl(["pkey", "-pubin", "-in", str(public_key), "-outform", "DER"])


def _public_from_private(private_key: Path) -> bytes:
    return _run_openssl(["pkey", "-in", str(private_key), "-pubout", "-outform", "DER"])


def _sign(private_key: Path, payload: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(prefix="city2-checkpoint-", mode="wb") as handle:
        handle.write(payload)
        handle.flush()
        return _run_openssl(
            [
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private_key),
                "-rawin",
                "-in",
                handle.name,
            ]
        )


def _verify(public_key: Path, payload: bytes, signature: bytes) -> None:
    with tempfile.NamedTemporaryFile(
        prefix="city2-signature-", mode="wb"
    ) as signature_file:
        signature_file.write(signature)
        signature_file.flush()
        with tempfile.NamedTemporaryFile(
            prefix="city2-checkpoint-", mode="wb"
        ) as payload_file:
            payload_file.write(payload)
            payload_file.flush()
            _run_openssl(
                [
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(public_key),
                    "-sigfile",
                    signature_file.name,
                    "-rawin",
                    "-in",
                    payload_file.name,
                ]
            )


def _file_sha(path: Path) -> str:
    digest = __import__("hashlib").sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def _write_sums(root: Path, names: set[str]) -> str:
    lines = [f"{_file_sha(root / name)}  {name}" for name in sorted(names)]
    content = "\n".join(lines) + "\n"
    (root / "SHA256SUMS").write_text(content, encoding="utf-8")
    return sha256_bytes(content.encode("utf-8"))


def create_backup(
    store: Store,
    output: str | Path,
    *,
    signing_key: str | Path,
    key_version: str,
    git_refs: dict[str, str] | None = None,
) -> dict[str, Any]:
    destination = Path(output)
    if destination.exists():
        raise StoreError(f"backup destination already exists: {destination}")
    private_key = Path(signing_key)
    if not private_key.is_file():
        raise StoreError(f"checkpoint signing key does not exist: {private_key}")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        store.fault("before_backup")
        store.verify_integrity()
        snapshot_path = stage / "core-snapshot.sqlite"
        snapshot_conn = sqlite3.connect(snapshot_path)
        try:
            store.conn.backup(snapshot_conn)
        finally:
            snapshot_conn.close()
        os.chmod(snapshot_path, 0o600)
        store.fault("after_sqlite_backup")

        with Store.open(snapshot_path) as snapshot:
            integrity = snapshot.verify_integrity()
            events = snapshot.events()
            event_text = "".join(canonical_json(event) + "\n" for event in events)
            (stage / "events.jsonl").write_text(event_text, encoding="utf-8")
            _write_json(stage / "git-refs.json", git_refs or {})
            store.fault("after_event_export")

            created_at = utc_now()
            barrier_id = str(uuid.uuid4())
            manifest = {
                "schema_version": "city2.local-backup-manifest/v1",
                "archive_id": "local-" + barrier_id,
                "backup_barrier_id": barrier_id,
                "created_at": created_at,
                "database_id": integrity["database_id"],
                "snapshot_method": "sqlite-online-backup-api",
                "schema_version_number": int(snapshot.meta("schema_version")),
                "application_version": snapshot.meta("application_version"),
                "event_high_water": integrity["event_high_water"],
                "terminal_hashes": integrity["terminal_hashes"],
                "integrity_check": integrity["integrity_check"],
                "git_refs": git_refs or {},
                "artifact_inventory": [],
                "artifact_root_sha256": sha256_json([]),
                "encryption_profile": "local-plaintext-m1-test-only",
                "creation_software": {"city2": snapshot.meta("application_version")},
            }
            _write_json(stage / "manifest.json", manifest)

        sums_sha = _write_sums(stage, ARCHIVE_FILES)
        public_der = _public_from_private(private_key)
        checkpoint = {
            "schema_version": "city2.checkpoint/v1",
            "backup_barrier_id": manifest["backup_barrier_id"],
            "database_id": manifest["database_id"],
            "event_high_water": manifest["event_high_water"],
            "terminal_hashes": manifest["terminal_hashes"],
            "manifest_sha256": _file_sha(stage / "manifest.json"),
            "sha256sums_sha256": sums_sha,
            "checkpoint_key_version": key_version,
            "checkpoint_public_key_sha256": sha256_bytes(public_der),
            "signature_algorithm": "ed25519",
            "created_at": manifest["created_at"],
        }
        checkpoint_bytes = canonical_json(checkpoint).encode("utf-8")
        store.fault("before_checkpoint_sign")
        _write_json(stage / "checkpoint.json", checkpoint)
        signature = base64.urlsafe_b64encode(
            _sign(private_key, checkpoint_bytes)
        ).rstrip(b"=")
        (stage / "checkpoint.sig").write_bytes(signature + b"\n")
        os.chmod(stage / "checkpoint.sig", 0o600)
        store.fault("before_backup_commit")
        stage.rename(destination)
        store.fault("after_backup_commit")
        return checkpoint
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def verify_backup(
    archive: str | Path, *, trusted_public_key: str | Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(archive)
    public_key = Path(trusted_public_key)
    required = ARCHIVE_FILES | {"SHA256SUMS", "checkpoint.json", "checkpoint.sig"}
    if not root.is_dir() or any(not (root / name).is_file() for name in required):
        raise IntegrityError("archive is incomplete")

    expected_lines = (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    parsed: dict[str, str] = {}
    for line in expected_lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or parts[1] not in ARCHIVE_FILES or parts[1] in parsed:
            raise IntegrityError("invalid SHA256SUMS inventory")
        parsed[parts[1]] = parts[0]
    if set(parsed) != ARCHIVE_FILES:
        raise IntegrityError("SHA256SUMS inventory mismatch")
    for name, expected in parsed.items():
        if _file_sha(root / name) != expected:
            raise IntegrityError(f"archive checksum mismatch: {name}")

    checkpoint = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if canonical_json(checkpoint) + "\n" != (root / "checkpoint.json").read_text(
        encoding="utf-8"
    ):
        raise IntegrityError("checkpoint is not canonical JSON")
    if canonical_json(manifest) + "\n" != (root / "manifest.json").read_text(
        encoding="utf-8"
    ):
        raise IntegrityError("manifest is not canonical JSON")
    if checkpoint.get("signature_algorithm") != "ed25519":
        raise IntegrityError("unsupported checkpoint signature algorithm")
    if checkpoint.get("manifest_sha256") != _file_sha(root / "manifest.json"):
        raise IntegrityError("checkpoint does not bind manifest")
    if checkpoint.get("sha256sums_sha256") != _file_sha(root / "SHA256SUMS"):
        raise IntegrityError("checkpoint does not bind SHA256SUMS")
    if checkpoint.get("checkpoint_public_key_sha256") != sha256_bytes(
        _public_key_der(public_key)
    ):
        raise IntegrityError("checkpoint was not signed by the trusted key")
    if any(
        checkpoint.get(key) != manifest.get(key)
        for key in (
            "backup_barrier_id",
            "database_id",
            "event_high_water",
            "terminal_hashes",
        )
    ):
        raise IntegrityError("checkpoint and manifest barrier disagree")
    encoded = (root / "checkpoint.sig").read_bytes().strip()
    try:
        signature = base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4))
    except ValueError as error:
        raise IntegrityError("invalid checkpoint signature encoding") from error
    try:
        _verify(public_key, canonical_json(checkpoint).encode("utf-8"), signature)
    except StoreError as error:
        raise IntegrityError("checkpoint signature verification failed") from error

    with Store.open(root / "core-snapshot.sqlite") as snapshot:
        report = snapshot.verify_integrity()
        if report["database_id"] != checkpoint["database_id"]:
            raise IntegrityError("snapshot database identity mismatch")
        if report["event_high_water"] != checkpoint["event_high_water"]:
            raise IntegrityError("snapshot event barrier mismatch")
        if report["terminal_hashes"] != checkpoint["terminal_hashes"]:
            raise IntegrityError("snapshot terminal hashes mismatch")
        expected_events = "".join(
            canonical_json(event) + "\n" for event in snapshot.events()
        )
        if (root / "events.jsonl").read_text(encoding="utf-8") != expected_events:
            raise IntegrityError("event export disagrees with snapshot")
    return checkpoint, manifest


def restore_backup(
    archive: str | Path,
    destination_dir: str | Path,
    *,
    trusted_public_key: str | Path,
) -> dict[str, Any]:
    checkpoint, _ = verify_backup(archive, trusted_public_key=trusted_public_key)
    destination = Path(destination_dir)
    if destination.exists() and any(destination.iterdir()):
        raise StoreError(f"restore destination is not empty: {destination}")
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    output = destination / "core.sqlite"
    source = sqlite3.connect(Path(archive) / "core-snapshot.sqlite")
    target = sqlite3.connect(output)
    try:
        source.backup(target)
        target.execute("PRAGMA journal_mode=WAL")
        target.execute("PRAGMA synchronous=FULL")
    finally:
        target.close()
        source.close()
    os.chmod(output, 0o600)
    try:
        with Store.open(output) as restored:
            report = restored.verify_integrity()
            if report["database_id"] != checkpoint["database_id"]:
                raise IntegrityError("restored database identity mismatch")
            if report["event_high_water"] != checkpoint["event_high_water"]:
                raise IntegrityError("restored event barrier mismatch")
            if report["terminal_hashes"] != checkpoint["terminal_hashes"]:
                raise IntegrityError("restored terminal hashes mismatch")
    except BaseException:
        output.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(output) + suffix).unlink(missing_ok=True)
        raise
    return {"database": str(output), "checkpoint": checkpoint, "verified": True}
