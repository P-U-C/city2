"""M6 read-only producer observation and scoped memory candidate output."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from .archive import _public_from_private, _public_key_der, _sign, _verify
from .model import canonical_json, digest_profile, parse_time, sha256_bytes
from .schema import validate_named
from .store import IntegrityError, StoreError


class ProducerError(StoreError):
    pass


def _uri_path(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc or parsed.query or parsed.fragment:
        raise ProducerError("producer source must be a local file URI")
    return Path(unquote(parsed.path))


def _timestamp(value: float) -> str:
    return (
        datetime.fromtimestamp(value, timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _candidate_scope(scope: str) -> str:
    return f"candidate:{scope}"


def _runtime_uri(contract: dict[str, Any]) -> str:
    return str(contract["source"].get("runtime_uri", contract["source"]["uri"]))


def _hash_fd(fd: int, maximum: int) -> tuple[str, int]:
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    total = 0
    while chunk := os.read(fd, 1024 * 1024):
        total += len(chunk)
        if total > maximum:
            raise ProducerError("producer output exceeds the contract limit")
        digest.update(chunk)
    return digest.hexdigest(), total


class ProducerObserver:
    def __init__(
        self,
        contract: dict[str, Any],
        agent: dict[str, Any],
        *,
        after_read: Callable[[], None] | None = None,
    ) -> None:
        validate_named(contract, "producer-contract.schema.json")
        validate_named(agent, "agent.schema.json")
        self.contract = contract
        self.agent = agent
        self.after_read = after_read
        self._validate_boundary()

    def _validate_boundary(self) -> None:
        contract, agent = self.contract, self.agent
        if agent["manifest_sha256"] != digest_profile(
            agent, {"manifest_sha256", "aggregate_version"}
        ):
            raise ProducerError("producer observer manifest digest mismatch")
        expected = {
            "agent_id": contract["agent_id"],
            "role": "producer-observer",
            "authority_class": "A0",
            "network_policy": "deny",
            "credential_handles": [],
            "memory_write_scopes": [_candidate_scope(contract["memory_scope"])],
            "filesystem_scopes": ["read:" + _runtime_uri(contract)],
            "allowed_task_types": ["observe-producer-output"],
            "review_policy": "deterministic",
            "concurrency": 1,
        }
        for field, value in expected.items():
            if agent[field] != value:
                raise ProducerError(f"producer observer boundary mismatch: {field}")
        if set(agent["tools"]) != {"read-output", "hash-output"}:
            raise ProducerError(
                "producer observer tools are not the exact read-only set"
            )
        if set(agent["required_capabilities"]) != {
            "filesystem_read",
            "artifact_hashing",
        }:
            raise ProducerError("producer observer capabilities are not read-only")
        if agent["model_policy"] != "none" or agent["cost_budget"] != {
            "max_billable_usd": "0",
            "max_input_tokens": 0,
            "max_output_tokens": 0,
        }:
            raise ProducerError("producer observer must be deterministic and zero-cost")

    def observe(
        self,
        source: str | Path,
        *,
        observed_at: str,
        signing_key: str | Path,
        signer_key_version: str,
    ) -> dict[str, Any]:
        if not self.contract["enabled"] or not self.agent["enabled"]:
            raise ProducerError("producer observer is disabled")
        signer = self.contract.get("signer")
        if signer:
            if signer_key_version != signer["key_version"]:
                raise ProducerError("producer signer key version mismatch")
            try:
                fingerprint = sha256_bytes(_public_from_private(Path(signing_key)))
            except StoreError as error:
                raise ProducerError("producer signer key is unavailable") from error
            if fingerprint != signer["public_key_sha256"]:
                raise ProducerError("producer signer public key mismatch")
        observed_time = parse_time(observed_at)
        path = Path(source)
        expected = _uri_path(_runtime_uri(self.contract))
        if path.is_symlink() or path.resolve() != expected.resolve():
            raise ProducerError("producer source does not match the contract")
        lowered = path.name.casefold()
        if lowered.endswith((".sqlite", ".sqlite3", ".db", "-wal", "-shm")):
            raise ProducerError("producer databases and journals are not observable")

        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except OSError as error:
            raise ProducerError("producer output is unavailable") from error
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ProducerError("producer source must be a regular file")
            digest, total = _hash_fd(fd, self.contract["source"]["max_bytes"])
            if self.after_read:
                self.after_read()
            second_digest, second_total = _hash_fd(
                fd, self.contract["source"]["max_bytes"]
            )
            after = os.fstat(fd)
        finally:
            os.close(fd)

        def identity(stat):
            return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)

        if (
            identity(before) != identity(after)
            or digest != second_digest
            or total != second_total
        ):
            raise IntegrityError("producer output changed during observation")

        source_modified = datetime.fromtimestamp(before.st_mtime, timezone.utc)
        if source_modified > observed_time:
            raise IntegrityError("producer source modification time is in the future")
        freshness_seconds = int((observed_time - source_modified).total_seconds())
        unsigned = {
            "schema_version": "city2.producer-observation/v1",
            "contract_id": self.contract["contract_id"],
            "contract_version": self.contract["contract_version"],
            "producer_id": self.contract["producer_id"],
            "agent_id": self.agent["agent_id"],
            "source_uri": self.contract["source"]["uri"],
            "source_sha256": digest,
            "byte_length": total,
            "source_modified_at": _timestamp(before.st_mtime),
            "observed_at": observed_at,
            "freshness_seconds": freshness_seconds,
            "freshness_state": (
                "current"
                if freshness_seconds <= self.contract["freshness_slo_seconds"]
                else "stale"
            ),
            "authority_touch": {
                "schedule": False,
                "database": False,
                "source_write": False,
            },
            "value": {
                "provenance_checks": 4,
                "freshness_detected": True,
                "source_content_copied": False,
            },
            "signer_key_version": signer_key_version,
            "signature_algorithm": "ed25519",
        }
        signature = _sign(Path(signing_key), canonical_json(unsigned).encode())
        observation = dict(unsigned)
        observation["signature"] = (
            base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
        )
        validate_named(observation, "producer-observation.schema.json")
        return observation

    def memory_candidate(
        self,
        observation: dict[str, Any],
        *,
        trusted_public_key: str | Path,
    ) -> dict[str, Any]:
        verify_producer_observation(
            observation,
            self.contract,
            trusted_public_key=trusted_public_key,
        )
        revalidate_at = parse_time(observation["observed_at"]) + timedelta(
            seconds=self.contract["freshness_slo_seconds"]
        )
        actor = "agent:" + self.agent["name"]
        return {
            "scope": self.contract["memory_scope"],
            "type": "fact",
            "statement": (
                f"Producer {observation['producer_id']} output was "
                f"{observation['freshness_state']} at {observation['observed_at']}."
            ),
            "evidence_refs": [
                {
                    "relationship": "observed_from",
                    "source_type": "producer_output",
                    "authoritative_owner": self.contract["unix_user"],
                    "uri": observation["source_uri"],
                    "retrieval_method": "read_only_hash",
                    "content_sha256": observation["source_sha256"],
                    "observed_at": observation["observed_at"],
                    "validity_status": observation["freshness_state"],
                    "revocation_checked_at": observation["observed_at"],
                }
            ],
            "asserted_by": actor,
            "owner": "human:chad",
            "valid_from": observation["observed_at"],
            "fact_class": "producer_output_health",
            "revalidation_policy": "producer_freshness_slo",
            "revalidate_at": revalidate_at.isoformat().replace("+00:00", "Z"),
            "confidence": 1.0,
            "sensitivity": self.contract["sensitivity"],
            "labels": ["producer", "read_only_observation"],
            "supersedes": [],
        }


def verify_producer_observation(
    observation: dict[str, Any],
    contract: dict[str, Any],
    *,
    trusted_public_key: str | Path,
) -> None:
    validate_named(observation, "producer-observation.schema.json")
    if (
        any(
            observation[field] != contract[field]
            for field in ("contract_id", "contract_version", "producer_id", "agent_id")
        )
        or observation["source_uri"] != contract["source"]["uri"]
    ):
        raise IntegrityError("producer observation does not match contract")
    signer = contract.get("signer")
    if signer:
        try:
            fingerprint = sha256_bytes(_public_key_der(Path(trusted_public_key)))
        except StoreError as error:
            raise IntegrityError(
                "producer observation signer is unavailable"
            ) from error
        if (
            observation["signer_key_version"] != signer["key_version"]
            or fingerprint != signer["public_key_sha256"]
        ):
            raise IntegrityError("producer observation signer does not match contract")
    unsigned = {key: value for key, value in observation.items() if key != "signature"}
    encoded = observation["signature"]
    try:
        signature = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        _verify(Path(trusted_public_key), canonical_json(unsigned).encode(), signature)
    except (ValueError, StoreError) as error:
        raise IntegrityError(
            "producer observation signature verification failed"
        ) from error


def write_observation(path: str | Path, observation: dict[str, Any]) -> None:
    validate_named(observation, "producer-observation.schema.json")
    destination = Path(path)
    if destination.resolve() == _uri_path(observation["source_uri"]).resolve():
        raise ProducerError("observation output cannot replace producer source")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if destination.exists():
        raise ProducerError("refusing to overwrite producer observation")
    payload = canonical_json(observation) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        temporary.rename(destination)
    except BaseException:
        if temporary:
            temporary.unlink(missing_ok=True)
        raise
