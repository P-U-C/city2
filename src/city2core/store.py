"""Hardened single-writer SQLite event store for City2 Core."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Callable
import uuid

from .model import (
    ZERO_SHA256,
    canonical_json,
    digest_profile,
    new_id,
    normalize_text,
    sha256_bytes,
    sha256_json,
    utc_now,
)
from .schema import SchemaStore, ValidationError, validate_named


SCHEMA_VERSION = 2
WRITER_ID = "city2-core-v1"
FaultHook = Callable[[str], None]


class StoreError(RuntimeError):
    """Base class for durable-store failures."""


class ConflictError(StoreError):
    """An optimistic-concurrency check failed."""


class IdempotencyCollision(StoreError):
    """An idempotency key was reused for a different command."""


class IntegrityError(StoreError):
    """The event log, projection or store configuration is unsafe."""


@dataclass(frozen=True)
class EventMarker:
    event_id: str
    event_sha256: str
    database_sequence: int
    aggregate_version: int


class WriteTransaction:
    def __init__(self, store: "Store", idempotency_key: str) -> None:
        self.store = store
        self.conn = store.conn
        self.idempotency_key = idempotency_key

    def current_version(self, table: str, id_column: str, aggregate_id: str) -> int:
        if table not in {"objectives", "tasks", "actions", "memory_records"}:
            raise ValueError(f"unsupported projection table: {table}")
        row = self.conn.execute(
            f"SELECT aggregate_version FROM {table} WHERE {id_column} = ?",
            (aggregate_id,),
        ).fetchone()
        return int(row[0]) if row else 0

    def expect_version(
        self, table: str, id_column: str, aggregate_id: str, expected_version: int
    ) -> int:
        actual = self.current_version(table, id_column, aggregate_id)
        if actual != expected_version:
            raise ConflictError(
                f"{aggregate_id}: expected aggregate version {expected_version}, found {actual}"
            )
        return actual

    def append_event(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        aggregate_version: int,
        actor: str,
        payload: Any,
        sensitivity: str = "internal",
        occurred_at: str | None = None,
    ) -> EventMarker:
        previous = self.conn.execute(
            """SELECT aggregate_version, aggregate_sequence, event_sha256
               FROM events WHERE aggregate_id = ? ORDER BY aggregate_sequence DESC LIMIT 1""",
            (aggregate_id,),
        ).fetchone()
        prior_version = int(previous[0]) if previous else 0
        if aggregate_version != prior_version + 1:
            raise ConflictError(
                f"{aggregate_id}: event version {aggregate_version} does not follow {prior_version}"
            )

        aggregate_sequence = (int(previous[1]) + 1) if previous else 1
        prior_hash = str(previous[2]) if previous else ZERO_SHA256
        writer_sequence = (
            int(
                self.conn.execute(
                    "SELECT writer_sequence FROM writer_state WHERE writer_id = ?",
                    (self.store.writer_id,),
                ).fetchone()[0]
            )
            + 1
        )
        database_sequence = int(self.store.meta("global_sequence")) + 1
        recorded_at = utc_now()
        event = {
            "schema_version": "city2.event/v1",
            "event_id": new_id("event"),
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "event_type": event_type,
            "aggregate_version": aggregate_version,
            "aggregate_sequence": aggregate_sequence,
            "writer_id": self.store.writer_id,
            "writer_sequence": writer_sequence,
            "database_sequence": database_sequence,
            "actor": actor,
            "occurred_at": occurred_at or recorded_at,
            "recorded_at": recorded_at,
            "idempotency_key": self.idempotency_key,
            "prior_event_sha256": prior_hash,
            "payload_sha256": sha256_json(payload),
            "payload": payload,
            "sensitivity": sensitivity,
        }
        try:
            validate_named(event, "event.schema.json", self.store.schemas)
        except ValidationError as error:
            raise StoreError(f"invalid event envelope: {error}") from error
        event_sha256 = sha256_json(event)
        self.conn.execute(
            """INSERT INTO events (
                 database_sequence, event_id, aggregate_type, aggregate_id, event_type,
                 aggregate_version, aggregate_sequence, writer_id, writer_sequence, actor,
                 occurred_at, recorded_at, idempotency_key, prior_event_sha256,
                 payload_sha256, payload_json, event_sha256, sensitivity
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                database_sequence,
                event["event_id"],
                aggregate_type,
                aggregate_id,
                event_type,
                aggregate_version,
                aggregate_sequence,
                self.store.writer_id,
                writer_sequence,
                actor,
                event["occurred_at"],
                recorded_at,
                self.idempotency_key,
                prior_hash,
                event["payload_sha256"],
                canonical_json(payload),
                event_sha256,
                sensitivity,
            ),
        )
        self.conn.execute(
            "UPDATE writer_state SET writer_sequence = ? WHERE writer_id = ?",
            (writer_sequence, self.store.writer_id),
        )
        self.conn.execute(
            "UPDATE core_meta SET value = ? WHERE key = 'global_sequence'",
            (str(database_sequence),),
        )
        self.store.fault("after_event_append")
        return EventMarker(
            event_id=event["event_id"],
            event_sha256=event_sha256,
            database_sequence=database_sequence,
            aggregate_version=aggregate_version,
        )

    def projection_updated(self) -> None:
        self.store.fault("after_projection_update")


class Store:
    """One SQLite connection owned by the singular City2 v1 writer."""

    def __init__(
        self,
        path: Path,
        conn: sqlite3.Connection,
        *,
        writer_id: str = WRITER_ID,
        fault_hook: FaultHook | None = None,
    ) -> None:
        self.path = path
        self.conn = conn
        self.writer_id = writer_id
        self._fault_hook = fault_hook
        self.schemas = SchemaStore()

    @classmethod
    def initialize(
        cls,
        path: str | Path,
        *,
        writer_id: str = WRITER_ID,
        fault_hook: FaultHook | None = None,
    ) -> "Store":
        db_path = Path(path)
        db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if db_path.exists():
            raise StoreError(f"database already exists: {db_path}")
        conn = cls._connect(db_path)
        try:
            mode = str(conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
            if mode != "wal":
                raise IntegrityError(f"SQLite refused WAL mode: {mode}")
            cls._configure_connection(conn)
            now = utc_now()
            metadata = {
                "application_version": cls.application_version(),
                "database_id": str(uuid.uuid4()),
                "global_sequence": "0",
                "schema_version": str(SCHEMA_VERSION),
                "writer_id": writer_id,
            }
            for version, migration_path in enumerate(cls.migration_paths(), 1):
                migration = migration_path.read_text(encoding="utf-8")
                conn.executescript("BEGIN IMMEDIATE;\n" + migration)
                conn.execute(
                    """INSERT INTO schema_migrations(version, sha256, applied_at)
                       VALUES (?, ?, ?)""",
                    (version, sha256_bytes(migration.encode("utf-8")), now),
                )
                if version == 1:
                    conn.executemany(
                        "INSERT INTO core_meta(key, value) VALUES (?, ?)",
                        sorted(metadata.items()),
                    )
                    conn.execute(
                        "INSERT INTO writer_state(writer_id, writer_sequence) VALUES (?, 0)",
                        (writer_id,),
                    )
                else:
                    conn.execute(
                        "UPDATE core_meta SET value = ? WHERE key = 'schema_version'",
                        (str(version),),
                    )
                conn.commit()
            os.chmod(db_path, 0o600)
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            conn.close()
            if db_path.exists():
                db_path.unlink()
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(db_path) + suffix)
                if sidecar.exists():
                    sidecar.unlink()
            raise
        store = cls(db_path, conn, writer_id=writer_id, fault_hook=fault_hook)
        store.verify_integrity()
        return store

    @classmethod
    def migrate(
        cls,
        path: str | Path,
        *,
        writer_id: str = WRITER_ID,
        fault_hook: FaultHook | None = None,
    ) -> "Store":
        """Apply reviewed forward-only migrations, then return a verified store."""
        db_path = Path(path)
        if not db_path.is_file():
            raise StoreError(f"database does not exist: {db_path}")
        conn = cls._connect(db_path)
        try:
            mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            if mode != "wal":
                raise IntegrityError(f"unsafe SQLite journal_mode={mode}; expected wal")
            cls._configure_connection(conn)
            current = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if current < 1 or current > SCHEMA_VERSION:
                raise IntegrityError(f"unsupported schema version: {current}")
            for version, migration_path in enumerate(cls.migration_paths(), 1):
                if version > current:
                    break
                row = conn.execute(
                    "SELECT sha256 FROM schema_migrations WHERE version = ?", (version,)
                ).fetchone()
                if row is None or row[0] != sha256_bytes(migration_path.read_bytes()):
                    raise IntegrityError(f"migration checksum mismatch: v{version}")
            for version in range(current + 1, SCHEMA_VERSION + 1):
                migration_path = cls.migration_paths()[version - 1]
                migration = migration_path.read_text(encoding="utf-8")
                conn.executescript("BEGIN IMMEDIATE;\n" + migration)
                conn.execute(
                    """INSERT INTO schema_migrations(version, sha256, applied_at)
                       VALUES (?, ?, ?)""",
                    (version, sha256_bytes(migration.encode("utf-8")), utc_now()),
                )
                conn.execute(
                    "UPDATE core_meta SET value = ? WHERE key = 'schema_version'",
                    (str(version),),
                )
                conn.execute(
                    "UPDATE core_meta SET value = ? WHERE key = 'application_version'",
                    (cls.application_version(),),
                )
                if fault_hook is not None:
                    fault_hook(f"before_migration_{version}_commit")
                conn.commit()
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            conn.close()
            raise
        conn.close()
        return cls.open(db_path, writer_id=writer_id, fault_hook=fault_hook)

    @classmethod
    def open(
        cls,
        path: str | Path,
        *,
        writer_id: str = WRITER_ID,
        fault_hook: FaultHook | None = None,
        verify: bool = True,
    ) -> "Store":
        db_path = Path(path)
        if not db_path.is_file():
            raise StoreError(f"database does not exist: {db_path}")
        conn = cls._connect(db_path)
        try:
            mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            if mode != "wal":
                raise IntegrityError(f"unsafe SQLite journal_mode={mode}; expected wal")
            cls._configure_connection(conn)
            store = cls(db_path, conn, writer_id=writer_id, fault_hook=fault_hook)
            if store.meta("writer_id") != writer_id:
                raise IntegrityError("configured writer does not own this database")
            store._verify_pragmas()
            if verify:
                store.verify_integrity()
            return store
        except BaseException:
            conn.close()
            raise

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(path, isolation_level=None, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _configure_connection(conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=5000")

    def _verify_pragmas(self) -> None:
        actual = {
            "foreign_keys": int(self.conn.execute("PRAGMA foreign_keys").fetchone()[0]),
            "journal_mode": str(
                self.conn.execute("PRAGMA journal_mode").fetchone()[0]
            ).lower(),
            "synchronous": int(self.conn.execute("PRAGMA synchronous").fetchone()[0]),
            "user_version": int(self.conn.execute("PRAGMA user_version").fetchone()[0]),
        }
        expected = {
            "foreign_keys": 1,
            "journal_mode": "wal",
            "synchronous": 2,
            "user_version": SCHEMA_VERSION,
        }
        if actual != expected:
            raise IntegrityError(
                f"unsafe SQLite configuration: {actual}; expected {expected}"
            )

    @staticmethod
    def migration_paths() -> tuple[Path, ...]:
        root = Path(__file__).with_name("migrations")
        return tuple(sorted(root.glob("[0-9][0-9][0-9][0-9]_*.sql")))

    @staticmethod
    def application_version() -> str:
        return (
            (Path(__file__).parents[2] / "VERSION").read_text(encoding="utf-8").strip()
        )

    def meta(self, key: str) -> str:
        row = self.conn.execute(
            "SELECT value FROM core_meta WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            raise IntegrityError(f"missing Core metadata: {key}")
        return str(row[0])

    def fault(self, boundary: str) -> None:
        if self._fault_hook is not None:
            self._fault_hook(boundary)

    def command(
        self,
        idempotency_key: str,
        command: dict[str, Any],
        operation: Callable[[WriteTransaction], dict[str, Any]],
    ) -> tuple[dict[str, Any], bool]:
        self._verify_pragmas()
        command_sha = sha256_json(command)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.fault("after_begin")
            prior = self.conn.execute(
                "SELECT command_sha256, result_json FROM command_dedup WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if prior is not None:
                if str(prior[0]) != command_sha:
                    raise IdempotencyCollision(
                        f"idempotency key {idempotency_key!r} was reused for a different command"
                    )
                result = json.loads(str(prior[1]))
                self.conn.commit()
                return result, True

            tx = WriteTransaction(self, idempotency_key)
            result = operation(tx)
            result_json = canonical_json(result)
            self.fault("before_dedup_record")
            self.conn.execute(
                """INSERT INTO command_dedup
                   (idempotency_key, command_sha256, result_json, committed_at)
                   VALUES (?, ?, ?, ?)""",
                (idempotency_key, command_sha, result_json, utc_now()),
            )
            self.fault("before_commit")
            self.conn.commit()
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        self.fault("after_commit")
        return result, False

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "schema_version": "city2.event/v1",
            "event_id": row["event_id"],
            "aggregate_type": row["aggregate_type"],
            "aggregate_id": row["aggregate_id"],
            "event_type": row["event_type"],
            "aggregate_version": row["aggregate_version"],
            "aggregate_sequence": row["aggregate_sequence"],
            "writer_id": row["writer_id"],
            "writer_sequence": row["writer_sequence"],
            "database_sequence": row["database_sequence"],
            "actor": row["actor"],
            "occurred_at": row["occurred_at"],
            "recorded_at": row["recorded_at"],
            "idempotency_key": row["idempotency_key"],
            "prior_event_sha256": row["prior_event_sha256"],
            "payload_sha256": row["payload_sha256"],
            "payload": json.loads(row["payload_json"]),
            "sensitivity": row["sensitivity"],
        }

    def events(self, through_sequence: int | None = None) -> list[dict[str, Any]]:
        if through_sequence is None:
            rows = self.conn.execute(
                "SELECT * FROM events ORDER BY database_sequence"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE database_sequence <= ? ORDER BY database_sequence",
                (through_sequence,),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def verify_integrity(self) -> dict[str, Any]:
        self._verify_pragmas()
        check = str(self.conn.execute("PRAGMA integrity_check").fetchone()[0])
        if check != "ok":
            raise IntegrityError(f"SQLite integrity_check failed: {check}")

        if len(self.migration_paths()) != SCHEMA_VERSION:
            raise IntegrityError("migration inventory does not match schema version")
        for version, migration_path in enumerate(self.migration_paths(), 1):
            migration = self.conn.execute(
                "SELECT sha256 FROM schema_migrations WHERE version = ?", (version,)
            ).fetchone()
            expected_migration = sha256_bytes(migration_path.read_bytes())
            if migration is None or str(migration[0]) != expected_migration:
                raise IntegrityError(f"migration checksum mismatch: v{version}")

        terminal: dict[str, tuple[int, str, int, int, str, str]] = {}
        writer_sequences: dict[str, int] = {}
        rows = self.conn.execute(
            "SELECT * FROM events ORDER BY database_sequence"
        ).fetchall()
        for expected_database_sequence, row in enumerate(rows, 1):
            if int(row["database_sequence"]) != expected_database_sequence:
                raise IntegrityError("event database sequence gap")
            event = self._event_from_row(row)
            payload_json = canonical_json(event["payload"])
            if payload_json != str(row["payload_json"]):
                raise IntegrityError(f"noncanonical payload at event {row['event_id']}")
            if sha256_json(event["payload"]) != row["payload_sha256"]:
                raise IntegrityError(
                    f"payload hash mismatch at event {row['event_id']}"
                )
            if sha256_json(event) != row["event_sha256"]:
                raise IntegrityError(f"event hash mismatch at event {row['event_id']}")

            prior = terminal.get(str(row["aggregate_id"]))
            prior_version, prior_hash, prior_sequence = (
                prior[:3] if prior else (0, ZERO_SHA256, 0)
            )
            if int(row["aggregate_version"]) != prior_version + 1:
                raise IntegrityError(f"aggregate version gap for {row['aggregate_id']}")
            if int(row["aggregate_sequence"]) != prior_sequence + 1:
                raise IntegrityError(
                    f"aggregate sequence gap for {row['aggregate_id']}"
                )
            if str(row["prior_event_sha256"]) != prior_hash:
                raise IntegrityError(
                    f"aggregate chain mismatch for {row['aggregate_id']}"
                )
            terminal[str(row["aggregate_id"])] = (
                int(row["aggregate_version"]),
                str(row["event_sha256"]),
                int(row["aggregate_sequence"]),
                int(row["database_sequence"]),
                str(row["event_id"]),
                str(row["aggregate_type"]),
            )

            writer = str(row["writer_id"])
            expected_writer_sequence = writer_sequences.get(writer, 0) + 1
            if int(row["writer_sequence"]) != expected_writer_sequence:
                raise IntegrityError(f"writer sequence gap for {writer}")
            writer_sequences[writer] = expected_writer_sequence

        high_water = len(rows)
        if int(self.meta("global_sequence")) != high_water:
            raise IntegrityError("Core metadata high-water does not match event log")
        for row in self.conn.execute(
            "SELECT writer_id, writer_sequence FROM writer_state"
        ):
            if int(row["writer_sequence"]) != writer_sequences.get(
                str(row["writer_id"]), 0
            ):
                raise IntegrityError(f"writer state mismatch for {row['writer_id']}")

        projected: set[str] = set()
        for table, id_column in (
            ("objectives", "objective_id"),
            ("tasks", "task_id"),
            ("actions", "action_id"),
            ("memory_records", "memory_id"),
        ):
            for row in self.conn.execute(
                f"""SELECT {id_column}, aggregate_version, last_event_id,
                    last_event_sha256, event_high_water, quarantined FROM {table}"""
            ):
                aggregate_id = str(row[id_column])
                projected.add(aggregate_id)
                marker = terminal.get(aggregate_id)
                if marker is None:
                    raise IntegrityError(f"projection without event: {aggregate_id}")
                if (
                    int(row["aggregate_version"]) != marker[0]
                    or str(row["last_event_sha256"]) != marker[1]
                    or int(row["event_high_water"]) != marker[3]
                    or str(row["last_event_id"]) != marker[4]
                    or int(row["quarantined"]) != 0
                ):
                    raise IntegrityError(f"projection/event mismatch: {aggregate_id}")

        expected_projected = {
            aggregate_id
            for aggregate_id, marker in terminal.items()
            if marker[5] in {"objective", "task", "action", "memory"}
        }
        if projected != expected_projected:
            raise IntegrityError("event/projection aggregate inventory mismatch")

        for row in self.conn.execute("SELECT * FROM objective_revisions"):
            record = json.loads(row["record_json"])
            if canonical_json(record) != row["record_json"]:
                raise IntegrityError(
                    f"noncanonical objective revision: {row['objective_id']}"
                )
            digest = digest_profile(
                record, {"aggregate_version", "objective_sha256", "status"}
            )
            if digest != row["objective_sha256"] or digest != record.get(
                "objective_sha256"
            ):
                raise IntegrityError(
                    f"objective revision hash mismatch: {row['objective_id']}"
                )

        for row in self.conn.execute("SELECT * FROM task_revisions"):
            record = json.loads(row["record_json"])
            if (
                canonical_json(record) != row["record_json"]
                or sha256_json(record) != row["task_sha256"]
            ):
                raise IntegrityError(f"task revision hash mismatch: {row['task_id']}")

        for row in self.conn.execute("SELECT * FROM runs"):
            envelope = json.loads(row["task_envelope_json"])
            envelope_sha = digest_profile(envelope, {"task_envelope_sha256"})
            if (
                canonical_json(envelope) != row["task_envelope_json"]
                or envelope_sha != row["task_envelope_sha256"]
                or envelope_sha != envelope.get("task_envelope_sha256")
            ):
                raise IntegrityError(f"run envelope hash mismatch: {row['run_id']}")
            if row["result_json"] is not None:
                result = json.loads(row["result_json"])
                if (
                    canonical_json(result) != row["result_json"]
                    or sha256_json(result) != row["result_sha256"]
                ):
                    raise IntegrityError(f"run result hash mismatch: {row['run_id']}")

        for row in self.conn.execute("SELECT * FROM objectives"):
            record = json.loads(row["record_json"])
            if (
                canonical_json(record) != row["record_json"]
                or record.get("objective_id") != row["objective_id"]
                or record.get("aggregate_version") != row["aggregate_version"]
                or record.get("status") != row["status"]
                or record.get("objective_sha256") != row["objective_sha256"]
            ):
                raise IntegrityError(
                    f"objective projection record mismatch: {row['objective_id']}"
                )

        for row in self.conn.execute("SELECT * FROM actions"):
            record = json.loads(row["record_json"])
            evidence_sha = (
                sha256_json(record["provider_evidence"])
                if record.get("provider_evidence")
                else None
            )
            if (
                canonical_json(record) != row["record_json"]
                or record.get("action_id") != row["action_id"]
                or record.get("aggregate_version") != row["aggregate_version"]
                or record.get("state") != row["state"]
                or record.get("task_id") != row["task_id"]
                or record.get("task_revision") != row["task_revision"]
                or record.get("run_id") != row["run_id"]
                or record.get("operation_idempotency_key")
                != row["operation_idempotency_key"]
                or record.get("provider_operation_id") != row["provider_operation_id"]
                or evidence_sha != row["provider_evidence_sha256"]
            ):
                raise IntegrityError(
                    f"action projection record mismatch: {row['action_id']}"
                )

        for row in self.conn.execute("SELECT * FROM tasks"):
            revision_row = self.conn.execute(
                """SELECT task_sha256, record_json FROM task_revisions
                   WHERE task_id = ? AND task_revision = ?""",
                (row["task_id"], row["task_revision"]),
            ).fetchone()
            if revision_row is None:
                raise IntegrityError(
                    f"task projection revision missing: {row['task_id']}"
                )
            revision = json.loads(revision_row["record_json"])
            latest_event = self.conn.execute(
                """SELECT event_type, payload_json FROM events
                   WHERE aggregate_id = ? ORDER BY aggregate_sequence DESC LIMIT 1""",
                (row["task_id"],),
            ).fetchone()
            if latest_event is None:
                raise IntegrityError(f"task projection event missing: {row['task_id']}")
            event_type = str(latest_event["event_type"])
            payload = json.loads(latest_event["payload_json"])
            if event_type == "task.created":
                expected_state = payload["state"]
            elif event_type == "task.result_recorded":
                expected_state = payload["next_state"]
            elif event_type == "task.result_quarantined_after_cancel":
                expected_state = "cancellation_requested"
            elif event_type == "task.revised":
                expected_state = "ready"
            elif event_type.startswith("task."):
                expected_state = event_type.removeprefix("task.")
            else:
                raise IntegrityError(f"unknown terminal task event: {event_type}")
            lease_count = int(
                self.conn.execute(
                    """SELECT COUNT(*) FROM events
                       WHERE aggregate_id = ? AND event_type = 'task.leased'""",
                    (row["task_id"],),
                ).fetchone()[0]
            )
            latest_run = self.conn.execute(
                """SELECT * FROM runs WHERE task_id = ? AND task_revision = ?
                   ORDER BY attempt_number DESC LIMIT 1""",
                (row["task_id"], row["task_revision"]),
            ).fetchone()
            expected_task_sha = (
                latest_run["task_envelope_sha256"]
                if latest_run is not None
                else revision_row["task_sha256"]
            )
            if (
                row["state"] != expected_state
                or int(row["attempt_count"]) != lease_count
                or row["task_sha256"] != expected_task_sha
                or row["objective_id"] != revision["objective_id"]
                or row["objective_revision"] != revision["objective_revision"]
                or row["objective_sha256"] != revision["objective_sha256"]
                or int(row["max_attempts"]) != int(revision["max_attempts"])
            ):
                raise IntegrityError(
                    f"task projection record mismatch: {row['task_id']}"
                )

            lease_values = (
                row["lease_owner"],
                row["lease_fencing_token"],
                row["lease_expires_at"],
            )
            if row["state"] in {"leased", "running"}:
                if latest_run is None or row["current_run_id"] != latest_run["run_id"]:
                    raise IntegrityError(f"task current run mismatch: {row['task_id']}")
                envelope = json.loads(latest_run["task_envelope_json"])
                if any(value is None for value in lease_values) or (
                    row["lease_fencing_token"] != envelope["lease_fencing_token"]
                ):
                    raise IntegrityError(
                        f"task lease projection mismatch: {row['task_id']}"
                    )
            elif any(value is not None for value in lease_values):
                raise IntegrityError(
                    f"inactive task retains lease authority: {row['task_id']}"
                )

        expected_fts: dict[str, tuple[str, str, str]] = {}
        for row in self.conn.execute("SELECT * FROM memory_records"):
            record = json.loads(row["record_json"])
            latest = self.conn.execute(
                """SELECT event_type FROM events WHERE aggregate_id = ?
                   ORDER BY aggregate_sequence DESC LIMIT 1""",
                (row["memory_id"],),
            ).fetchone()
            expected_state = str(latest["event_type"]).removeprefix("memory.")
            if expected_state == "created":
                expected_state = "candidate"
            if (
                canonical_json(record) != row["record_json"]
                or sha256_json(record) != row["record_sha256"]
                or record.get("memory_id") != row["memory_id"]
                or record.get("aggregate_version") != row["aggregate_version"]
                or record.get("scope") != row["scope"]
                or record.get("type") != row["memory_type"]
                or record.get("review_state") != row["review_state"]
                or row["review_state"] != expected_state
                or record.get("statement") != row["statement"]
                or record.get("sensitivity") != row["sensitivity"]
            ):
                raise IntegrityError(f"memory projection mismatch: {row['memory_id']}")
            if row["review_state"] == "accepted":
                expected_fts[str(row["memory_id"])] = (
                    normalize_text(str(row["statement"])),
                    str(row["labels_text"]),
                    str(row["source_text"]),
                )

        actual_fts = {
            str(row["memory_id"]): (
                str(row["statement"]),
                str(row["labels"]),
                str(row["source_metadata"]),
            )
            for row in self.conn.execute(
                "SELECT memory_id, statement, labels, source_metadata FROM memory_fts"
            )
        }
        if actual_fts != expected_fts:
            raise IntegrityError("memory FTS projection mismatch")

        for row in self.conn.execute("SELECT * FROM context_packs"):
            manifest = json.loads(row["manifest_json"])
            content = json.loads(row["content_json"])
            if (
                canonical_json(manifest) != row["manifest_json"]
                or sha256_json(manifest) != row["manifest_sha256"]
                or canonical_json(content) != row["content_json"]
                or sha256_json(content) != row["content_sha256"]
                or manifest.get("context_id") != row["context_id"]
                or manifest.get("task_id") != row["task_id"]
            ):
                raise IntegrityError(f"context pack mismatch: {row['context_id']}")

        return {
            "database_id": self.meta("database_id"),
            "event_high_water": high_water,
            "integrity_check": check,
            "terminal_hashes": {
                key: value[1] for key, value in sorted(terminal.items())
            },
        }

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
