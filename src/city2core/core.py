"""Deterministic objective, task, lease and action lifecycle for City2 M1."""

from __future__ import annotations

import json
import re
import secrets
from typing import Any

from .model import (
    canonical_json,
    digest_profile,
    new_id,
    parse_time,
    sha256_json,
    utc_now,
)
from .schema import ValidationError, validate_named
from .store import ConflictError, Store, WriteTransaction


class CoreError(RuntimeError):
    """A command violates a deterministic Core lifecycle rule."""


TASK_TERMINAL = {"accepted", "rejected", "cancelled", "failed_terminal"}
UNCERTAIN_ACTION_STATES = {"dispatched", "unknown"}
SECRET_KEY_PATTERN = re.compile(
    r"(^|[._-])(api[_-]?key|credential|mnemonic|password|private[_-]?key|recovery[_-]?phrase|secret|seed|token)([._-]|$)",
    re.IGNORECASE,
)


def _required(record: dict[str, Any], *names: str) -> None:
    missing = [name for name in names if name not in record]
    if missing:
        raise CoreError("missing required fields: " + ", ".join(missing))


def _reject_secret_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY_PATTERN.search(key):
                raise CoreError(f"secret-shaped parameter key denied at {path}.{key}")
            _reject_secret_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_keys(item, f"{path}[{index}]")


class Core:
    """Application service over the single-writer event store."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def _validate(self, value: Any, schema_name: str) -> None:
        try:
            validate_named(value, schema_name, self.store.schemas)
        except ValidationError as error:
            raise CoreError(f"{schema_name}: {error}") from error

    def create_objective(
        self, fields: dict[str, Any], *, actor: str, idempotency_key: str
    ) -> dict[str, Any]:
        _required(
            fields,
            "title",
            "intent",
            "accountable_owner",
            "review_at",
            "measurable_outcomes",
            "stop_conditions",
            "authority_ceiling",
            "budget",
        )
        command = {"command": "create_objective", "fields": fields, "actor": actor}

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            now = utc_now()
            objective_id = fields.get("objective_id") or new_id("objective")
            record = {
                "schema_version": "city2.objective/v1",
                "objective_id": objective_id,
                "aggregate_version": 1,
                "objective_revision": 1,
                "objective_sha256": "",
                "title": fields["title"],
                "intent": fields["intent"],
                "created_by": actor,
                "accountable_owner": fields["accountable_owner"],
                "created_at": fields.get("created_at", now),
                "review_at": fields["review_at"],
                "measurable_outcomes": fields["measurable_outcomes"],
                "stop_conditions": fields["stop_conditions"],
                "authority_ceiling": fields["authority_ceiling"],
                "budget": fields["budget"],
                "status": "proposed",
            }
            record["objective_sha256"] = digest_profile(
                record, {"aggregate_version", "objective_sha256", "status"}
            )
            self._validate(record, "objective.schema.json")
            tx.expect_version("objectives", "objective_id", objective_id, 0)
            marker = tx.append_event(
                aggregate_type="objective",
                aggregate_id=objective_id,
                event_type="objective.created",
                aggregate_version=1,
                actor=actor,
                payload={"objective": record},
            )
            record_json = canonical_json(record)
            self.store.conn.execute(
                """INSERT INTO objective_revisions
                   (objective_id, objective_revision, objective_sha256, record_json, created_at)
                   VALUES (?, 1, ?, ?, ?)""",
                (objective_id, record["objective_sha256"], record_json, now),
            )
            self.store.conn.execute(
                """INSERT INTO objectives
                   (objective_id, aggregate_version, objective_revision, objective_sha256,
                    status, record_json, last_event_id, last_event_sha256,
                    event_high_water, updated_at)
                   VALUES (?, 1, 1, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    objective_id,
                    record["objective_sha256"],
                    record["status"],
                    record_json,
                    marker.event_id,
                    marker.event_sha256,
                    marker.database_sequence,
                    now,
                ),
            )
            tx.projection_updated()
            return record

        return self.store.command(idempotency_key, command, operation)[0]

    def set_objective_status(
        self,
        objective_id: str,
        status: str,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        allowed = {
            "proposed": {"active", "cancelled"},
            "active": {"paused", "completed", "cancelled", "superseded"},
            "paused": {"active", "cancelled", "superseded"},
        }
        command = {
            "command": "set_objective_status",
            "objective_id": objective_id,
            "status": status,
            "expected_version": expected_version,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version(
                "objectives", "objective_id", objective_id, expected_version
            )
            row = self._objective_row(objective_id)
            current = str(row["status"])
            if status not in allowed.get(current, set()):
                raise CoreError(
                    f"objective transition {current} -> {status} is not allowed"
                )
            record = json.loads(row["record_json"])
            record.update(aggregate_version=expected_version + 1, status=status)
            self._validate(record, "objective.schema.json")
            marker = tx.append_event(
                aggregate_type="objective",
                aggregate_id=objective_id,
                event_type=f"objective.{status}",
                aggregate_version=expected_version + 1,
                actor=actor,
                payload={"from": current, "to": status},
            )
            self.store.conn.execute(
                """UPDATE objectives SET aggregate_version = ?, status = ?, record_json = ?,
                   last_event_id = ?, last_event_sha256 = ?, event_high_water = ?, updated_at = ?
                   WHERE objective_id = ?""",
                (
                    expected_version + 1,
                    status,
                    canonical_json(record),
                    marker.event_id,
                    marker.event_sha256,
                    marker.database_sequence,
                    utc_now(),
                    objective_id,
                ),
            )
            tx.projection_updated()
            return record

        return self.store.command(idempotency_key, command, operation)[0]

    def revise_objective(
        self,
        objective_id: str,
        updates: dict[str, Any],
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        permitted = {
            "title",
            "intent",
            "accountable_owner",
            "review_at",
            "measurable_outcomes",
            "stop_conditions",
            "authority_ceiling",
            "budget",
        }
        unknown = set(updates) - permitted
        if unknown:
            raise CoreError(
                f"objective revision contains immutable/unknown fields: {sorted(unknown)}"
            )
        if not updates:
            raise CoreError("objective revision requires at least one change")
        command = {
            "command": "revise_objective",
            "objective_id": objective_id,
            "updates": updates,
            "expected_version": expected_version,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version(
                "objectives", "objective_id", objective_id, expected_version
            )
            row = self._objective_row(objective_id)
            if row["status"] in {"completed", "cancelled", "superseded"}:
                raise CoreError("terminal objectives cannot be revised")
            prior = json.loads(row["record_json"])
            revision_number = int(row["objective_revision"]) + 1
            record = {
                **prior,
                **updates,
                "aggregate_version": expected_version + 1,
                "objective_revision": revision_number,
                "objective_sha256": "",
                "supersedes": {
                    "objective_id": objective_id,
                    "objective_revision": row["objective_revision"],
                    "objective_sha256": row["objective_sha256"],
                },
            }
            record["objective_sha256"] = digest_profile(
                record, {"aggregate_version", "objective_sha256", "status"}
            )
            self._validate(record, "objective.schema.json")
            if record["objective_sha256"] == row["objective_sha256"]:
                raise CoreError(
                    "objective revision does not change the immutable profile"
                )
            now = utc_now()
            marker = tx.append_event(
                aggregate_type="objective",
                aggregate_id=objective_id,
                event_type="objective.revised",
                aggregate_version=expected_version + 1,
                actor=actor,
                payload={
                    "objective_revision": revision_number,
                    "objective_sha256": record["objective_sha256"],
                    "supersedes_revision": row["objective_revision"],
                },
            )
            record_json = canonical_json(record)
            self.store.conn.execute(
                """INSERT INTO objective_revisions
                   (objective_id, objective_revision, objective_sha256, record_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    objective_id,
                    revision_number,
                    record["objective_sha256"],
                    record_json,
                    now,
                ),
            )
            self.store.conn.execute(
                """UPDATE objectives SET aggregate_version = ?, objective_revision = ?,
                   objective_sha256 = ?, record_json = ?, last_event_id = ?,
                   last_event_sha256 = ?, event_high_water = ?, updated_at = ?
                   WHERE objective_id = ?""",
                (
                    expected_version + 1,
                    revision_number,
                    record["objective_sha256"],
                    record_json,
                    marker.event_id,
                    marker.event_sha256,
                    marker.database_sequence,
                    now,
                    objective_id,
                ),
            )
            tx.projection_updated()
            return record

        return self.store.command(idempotency_key, command, operation)[0]

    def create_task(
        self, fields: dict[str, Any], *, actor: str, idempotency_key: str
    ) -> dict[str, Any]:
        _required(
            fields,
            "objective_id",
            "task_type",
            "title",
            "intent",
            "requested_role",
            "authority_class",
            "inputs",
            "constraints",
            "acceptance_criteria",
            "memory_scopes",
            "time_budget_seconds",
            "max_attempts",
            "task_dedupe_key",
        )
        command = {"command": "create_task", "fields": fields, "actor": actor}

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            objective = self._objective_row(fields["objective_id"])
            if objective["status"] not in {"active", "proposed"}:
                raise CoreError(
                    "tasks may only be created under a proposed or active objective"
                )
            now = utc_now()
            task_id = fields.get("task_id") or new_id("task")
            revision = {
                "task_id": task_id,
                "task_revision": 1,
                "objective_id": objective["objective_id"],
                "objective_revision": objective["objective_revision"],
                "objective_sha256": objective["objective_sha256"],
                "task_type": fields["task_type"],
                "title": fields["title"],
                "intent": fields["intent"],
                "created_by": actor,
                "requested_role": fields["requested_role"],
                "authority_class": fields["authority_class"],
                "inputs": fields["inputs"],
                "constraints": fields["constraints"],
                "acceptance_criteria": fields["acceptance_criteria"],
                "memory_scopes": fields["memory_scopes"],
                "time_budget_seconds": fields["time_budget_seconds"],
                "max_attempts": fields["max_attempts"],
                "task_dedupe_key": fields["task_dedupe_key"],
                "created_at": fields.get("created_at", now),
            }
            task_sha = sha256_json(revision)
            record = {
                "schema_version": "city2.task-record/v1",
                "task_id": task_id,
                "task_revision": 1,
                "task_envelope_sha256": task_sha,
                "objective_id": objective["objective_id"],
                "objective_revision": objective["objective_revision"],
                "objective_sha256": objective["objective_sha256"],
                "aggregate_version": 1,
                "state": "proposed",
                "attempt_count": 0,
                "max_attempts": fields["max_attempts"],
                "created_at": revision["created_at"],
                "updated_at": revision["created_at"],
            }
            self._validate(record, "task-record.schema.json")
            tx.expect_version("tasks", "task_id", task_id, 0)
            marker = tx.append_event(
                aggregate_type="task",
                aggregate_id=task_id,
                event_type="task.created",
                aggregate_version=1,
                actor=actor,
                payload={"task_revision": revision, "state": record["state"]},
            )
            self.store.conn.execute(
                """INSERT INTO task_revisions
                   (task_id, task_revision, task_sha256, record_json, created_at)
                   VALUES (?, 1, ?, ?, ?)""",
                (task_id, task_sha, canonical_json(revision), now),
            )
            self.store.conn.execute(
                """INSERT INTO tasks
                   (task_id, aggregate_version, task_revision, task_sha256,
                    objective_id, objective_revision, objective_sha256, state,
                    attempt_count, max_attempts, last_event_id, last_event_sha256,
                    event_high_water, created_at, updated_at)
                   VALUES (?, 1, 1, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    task_sha,
                    objective["objective_id"],
                    objective["objective_revision"],
                    objective["objective_sha256"],
                    record["state"],
                    fields["max_attempts"],
                    marker.event_id,
                    marker.event_sha256,
                    marker.database_sequence,
                    now,
                    now,
                ),
            )
            tx.projection_updated()
            return record

        return self.store.command(idempotency_key, command, operation)[0]

    def set_task_ready(
        self,
        task_id: str,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._simple_task_transition(
            task_id,
            to_state="ready",
            allowed_from={"proposed", "awaiting_approval", "expired"},
            expected_version=expected_version,
            actor=actor,
            idempotency_key=idempotency_key,
        )

    def request_task_approval(
        self,
        task_id: str,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._simple_task_transition(
            task_id,
            to_state="awaiting_approval",
            allowed_from={"proposed"},
            expected_version=expected_version,
            actor=actor,
            idempotency_key=idempotency_key,
        )

    def review_task(
        self,
        task_id: str,
        decision: str,
        *,
        expected_version: int,
        review_id: str,
        finding_ids: list[str],
        finding_dispositions: dict[str, str] | None,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if decision not in {"accepted", "rejected", "changes_requested"}:
            raise CoreError(f"invalid review decision: {decision}")
        if decision == "changes_requested" and not finding_ids:
            raise CoreError("changes_requested requires at least one finding")
        dispositions = finding_dispositions or {}
        command = {
            "command": "review_task",
            "task_id": task_id,
            "decision": decision,
            "expected_version": expected_version,
            "review_id": review_id,
            "finding_ids": finding_ids,
            "finding_dispositions": dispositions,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version("tasks", "task_id", task_id, expected_version)
            row = self._task_row(task_id)
            if row["state"] != "review":
                raise CoreError(
                    f"task in {row['state']} cannot receive a review decision"
                )
            revision = self._task_revision(task_id, int(row["task_revision"]))
            unresolved = set(revision.get("unresolved_finding_ids", []))
            if decision == "accepted" and unresolved - set(dispositions):
                missing = sorted(unresolved - set(dispositions))
                raise CoreError(f"acceptance lacks finding dispositions: {missing}")
            return self._transition_in_tx(
                tx,
                row,
                decision,
                expected_version,
                actor,
                {
                    "review_id": review_id,
                    "finding_ids": finding_ids,
                    "finding_dispositions": dispositions,
                },
            )

        return self.store.command(idempotency_key, command, operation)[0]

    def revise_task(
        self,
        task_id: str,
        updates: dict[str, Any],
        *,
        expected_version: int,
        review_id: str,
        unresolved_finding_ids: list[str],
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        permitted = {
            "task_type",
            "title",
            "intent",
            "requested_role",
            "authority_class",
            "inputs",
            "constraints",
            "acceptance_criteria",
            "memory_scopes",
            "time_budget_seconds",
            "max_attempts",
            "task_dedupe_key",
        }
        unknown = set(updates) - permitted
        if unknown:
            raise CoreError(
                f"task revision contains immutable/unknown fields: {sorted(unknown)}"
            )
        if not updates:
            raise CoreError("task revision requires at least one change")
        command = {
            "command": "revise_task",
            "task_id": task_id,
            "updates": updates,
            "expected_version": expected_version,
            "review_id": review_id,
            "unresolved_finding_ids": unresolved_finding_ids,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version("tasks", "task_id", task_id, expected_version)
            row = self._task_row(task_id)
            if row["state"] != "changes_requested":
                raise CoreError("only changes_requested tasks may be revised")
            previous = self._task_revision(task_id, int(row["task_revision"]))
            latest_run = self.store.conn.execute(
                "SELECT run_id FROM runs WHERE task_id = ? ORDER BY attempt_number DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if latest_run is None:
                raise CoreError("revised task has no prior run")
            now = utc_now()
            revision_number = int(row["task_revision"]) + 1
            revision = {
                **previous,
                **updates,
                "task_revision": revision_number,
                "created_at": now,
                "supersedes_run_id": latest_run["run_id"],
                "review_id": review_id,
                "unresolved_finding_ids": unresolved_finding_ids,
            }
            task_sha = sha256_json(revision)
            if task_sha == row["task_sha256"]:
                raise CoreError("task revision does not change the immutable profile")
            marker = tx.append_event(
                aggregate_type="task",
                aggregate_id=task_id,
                event_type="task.revised",
                aggregate_version=expected_version + 1,
                actor=actor,
                payload={
                    "task_revision": revision_number,
                    "task_sha256": task_sha,
                    "review_id": review_id,
                    "unresolved_finding_ids": unresolved_finding_ids,
                    "supersedes_run_id": latest_run["run_id"],
                },
            )
            self.store.conn.execute(
                """INSERT INTO task_revisions
                   (task_id, task_revision, task_sha256, record_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (task_id, revision_number, task_sha, canonical_json(revision), now),
            )
            self.store.conn.execute(
                """UPDATE tasks SET aggregate_version = ?, task_revision = ?, task_sha256 = ?,
                   state = 'ready', max_attempts = ?, last_event_id = ?, last_event_sha256 = ?,
                   event_high_water = ?, updated_at = ? WHERE task_id = ?""",
                (
                    expected_version + 1,
                    revision_number,
                    task_sha,
                    revision["max_attempts"],
                    marker.event_id,
                    marker.event_sha256,
                    marker.database_sequence,
                    now,
                    task_id,
                ),
            )
            tx.projection_updated()
            return self.task(task_id)

        return self.store.command(idempotency_key, command, operation)[0]

    def resume_after_reconciliation(
        self,
        task_id: str,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        command = {
            "command": "resume_after_reconciliation",
            "task_id": task_id,
            "expected_version": expected_version,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version("tasks", "task_id", task_id, expected_version)
            row = self._task_row(task_id)
            if row["state"] != "needs_reconciliation":
                raise CoreError("task does not require reconciliation")
            uncertain = self.store.conn.execute(
                "SELECT COUNT(*) FROM actions WHERE task_id = ? AND state IN ('prepared','dispatched','unknown')",
                (task_id,),
            ).fetchone()[0]
            if uncertain:
                raise CoreError("task still has unresolved actions")
            run = self.store.conn.execute(
                "SELECT status, result_json FROM runs WHERE task_id = ? ORDER BY attempt_number DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            next_state = "review" if run and run["status"] == "completed" else "ready"
            return self._transition_in_tx(
                tx,
                row,
                next_state,
                expected_version,
                actor,
                {"reconciliation_complete": True},
                clear_lease=next_state == "ready",
            )

        return self.store.command(idempotency_key, command, operation)[0]

    def lease_task(
        self,
        task_id: str,
        *,
        expected_version: int,
        owner: str,
        expires_at: str,
        resolved_agent_id: str,
        resolved_manifest_version: int,
        resolved_manifest_sha256: str,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if parse_time(expires_at) <= parse_time(utc_now()):
            raise CoreError("lease expiry must be in the future")
        command = {
            "command": "lease_task",
            "task_id": task_id,
            "expected_version": expected_version,
            "owner": owner,
            "expires_at": expires_at,
            "resolved_agent_id": resolved_agent_id,
            "resolved_manifest_version": resolved_manifest_version,
            "resolved_manifest_sha256": resolved_manifest_sha256,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version("tasks", "task_id", task_id, expected_version)
            row = self._task_row(task_id)
            if row["state"] not in {"ready", "expired"}:
                raise CoreError(f"task in {row['state']} cannot be leased")
            attempt = int(row["attempt_count"]) + 1
            if attempt > int(row["max_attempts"]):
                raise CoreError("task attempt ceiling reached")
            run_id = new_id("run")
            fence = secrets.token_urlsafe(24)
            revision = self._task_revision(task_id, int(row["task_revision"]))
            envelope = {
                "schema_version": "city2.task/v1",
                "task_id": task_id,
                "task_revision": row["task_revision"],
                "task_envelope_sha256": "",
                "objective_id": row["objective_id"],
                "objective_revision": row["objective_revision"],
                "objective_sha256": row["objective_sha256"],
                "task_type": revision["task_type"],
                "title": revision["title"],
                "intent": revision["intent"],
                "created_by": revision["created_by"],
                "requested_role": revision["requested_role"],
                "resolved_agent_id": resolved_agent_id,
                "resolved_manifest_version": resolved_manifest_version,
                "resolved_manifest_sha256": resolved_manifest_sha256,
                "attempt_number": attempt,
                "expected_task_version": expected_version + 1,
                "lease_fencing_token": fence,
                "authority_class": revision["authority_class"],
                "inputs": revision["inputs"],
                "constraints": revision["constraints"],
                "acceptance_criteria": revision["acceptance_criteria"],
                "memory_scopes": revision["memory_scopes"],
                "time_budget_seconds": revision["time_budget_seconds"],
                "max_attempts": revision["max_attempts"],
                "task_dedupe_key": revision["task_dedupe_key"],
            }
            for optional in (
                "supersedes_run_id",
                "review_id",
                "unresolved_finding_ids",
            ):
                if optional in revision:
                    envelope[optional] = revision[optional]
            envelope["task_envelope_sha256"] = digest_profile(
                envelope, {"task_envelope_sha256"}
            )
            self._validate(envelope, "task-envelope.schema.json")
            now = utc_now()
            marker = tx.append_event(
                aggregate_type="task",
                aggregate_id=task_id,
                event_type="task.leased",
                aggregate_version=expected_version + 1,
                actor=actor,
                payload={
                    "run_id": run_id,
                    "owner": owner,
                    "fencing_token_sha256": sha256_json(fence),
                    "expires_at": expires_at,
                    "attempt_number": attempt,
                    "task_envelope_sha256": envelope["task_envelope_sha256"],
                },
                sensitivity="confidential",
            )
            self.store.conn.execute(
                """INSERT INTO runs
                   (run_id, task_id, task_revision, attempt_number, status,
                    task_envelope_json, task_envelope_sha256, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'leased', ?, ?, ?, ?)""",
                (
                    run_id,
                    task_id,
                    row["task_revision"],
                    attempt,
                    canonical_json(envelope),
                    envelope["task_envelope_sha256"],
                    now,
                    now,
                ),
            )
            self.store.conn.execute(
                """UPDATE tasks SET aggregate_version = ?, state = 'leased', attempt_count = ?,
                   task_sha256 = ?,
                   current_run_id = ?, lease_owner = ?, lease_fencing_token = ?,
                   lease_expires_at = ?, last_event_id = ?, last_event_sha256 = ?,
                   event_high_water = ?, updated_at = ? WHERE task_id = ?""",
                (
                    expected_version + 1,
                    attempt,
                    envelope["task_envelope_sha256"],
                    run_id,
                    owner,
                    fence,
                    expires_at,
                    marker.event_id,
                    marker.event_sha256,
                    marker.database_sequence,
                    now,
                    task_id,
                ),
            )
            tx.projection_updated()
            self.store.fault("after_lease_acquisition")
            return {
                "run_id": run_id,
                "task": self.task(task_id),
                "task_envelope": envelope,
            }

        return self.store.command(idempotency_key, command, operation)[0]

    def start_run(
        self,
        task_id: str,
        run_id: str,
        fencing_token: str,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        command = {
            "command": "start_run",
            "task_id": task_id,
            "run_id": run_id,
            "fencing_token_sha256": sha256_json(fencing_token),
            "expected_version": expected_version,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version("tasks", "task_id", task_id, expected_version)
            row = self._task_row(task_id)
            self._require_current_lease(row, run_id, fencing_token)
            if row["state"] != "leased":
                raise CoreError(f"task in {row['state']} cannot start")
            return self._transition_in_tx(
                tx,
                row,
                "running",
                expected_version,
                actor,
                {"run_id": run_id},
                run_status="running",
            )

        return self.store.command(idempotency_key, command, operation)[0]

    def submit_result(
        self,
        result: dict[str, Any],
        *,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        _required(
            result,
            "task_id",
            "run_id",
            "expected_task_version",
            "lease_fencing_token",
            "run_status",
        )
        self._validate(result, "result.schema.json")
        task_id = result["task_id"]
        expected_version = int(result["expected_task_version"])
        command = {"command": "submit_result", "result": result, "actor": actor}

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            row = self._task_row(task_id)
            current_version = int(row["aggregate_version"])
            if row["state"] != "cancellation_requested":
                tx.expect_version("tasks", "task_id", task_id, expected_version)
            elif expected_version > current_version:
                raise ConflictError("result expects a future task version")
            run = self._run_row(result["run_id"])
            envelope = json.loads(run["task_envelope_json"])
            if (
                run["task_id"] != task_id
                or envelope["lease_fencing_token"] != result["lease_fencing_token"]
            ):
                raise ConflictError("stale or foreign lease fencing token")
            if row["current_run_id"] != result["run_id"]:
                raise ConflictError("run no longer owns the task")
            if row["state"] not in {"running", "cancellation_requested"}:
                raise CoreError(f"task in {row['state']} cannot accept a result")
            self.store.fault("before_result_persistence")
            now = utc_now()
            result_sha = sha256_json(result)
            if row["state"] == "cancellation_requested":
                self.store.conn.execute(
                    """UPDATE runs SET status = 'completed_after_cancel', result_json = ?,
                       result_sha256 = ?, updated_at = ? WHERE run_id = ?""",
                    (canonical_json(result), result_sha, now, result["run_id"]),
                )
                marker = tx.append_event(
                    aggregate_type="task",
                    aggregate_id=task_id,
                    event_type="task.result_quarantined_after_cancel",
                    aggregate_version=current_version + 1,
                    actor=actor,
                    payload={"run_id": result["run_id"], "result_sha256": result_sha},
                )
                self.store.conn.execute(
                    """UPDATE tasks SET aggregate_version = ?, last_event_id = ?,
                       last_event_sha256 = ?, event_high_water = ?, updated_at = ? WHERE task_id = ?""",
                    (
                        current_version + 1,
                        marker.event_id,
                        marker.event_sha256,
                        marker.database_sequence,
                        now,
                        task_id,
                    ),
                )
                tx.projection_updated()
                return {
                    "task": self.task(task_id),
                    "result_status": "completed_after_cancel",
                }

            uncertain = self.store.conn.execute(
                "SELECT COUNT(*) FROM actions WHERE run_id = ? AND state IN ('dispatched', 'unknown')",
                (result["run_id"],),
            ).fetchone()[0]
            if uncertain:
                next_state = "needs_reconciliation"
            elif result["run_status"] == "completed":
                next_state = "review"
            elif int(row["attempt_count"]) < int(row["max_attempts"]):
                next_state = "ready"
            else:
                next_state = "failed_terminal"
            run_status = (
                "completed" if result["run_status"] == "completed" else "failed"
            )
            self.store.conn.execute(
                """UPDATE runs SET status = ?, result_json = ?, result_sha256 = ?, updated_at = ?
                   WHERE run_id = ?""",
                (run_status, canonical_json(result), result_sha, now, result["run_id"]),
            )
            marker = tx.append_event(
                aggregate_type="task",
                aggregate_id=task_id,
                event_type="task.result_recorded",
                aggregate_version=expected_version + 1,
                actor=actor,
                payload={
                    "run_id": result["run_id"],
                    "result_sha256": result_sha,
                    "run_status": run_status,
                    "next_state": next_state,
                },
            )
            self.store.conn.execute(
                """UPDATE tasks SET aggregate_version = ?, state = ?, current_run_id = NULL,
                   lease_owner = NULL, lease_fencing_token = NULL, lease_expires_at = NULL,
                   last_event_id = ?, last_event_sha256 = ?, event_high_water = ?, updated_at = ?
                   WHERE task_id = ?""",
                (
                    expected_version + 1,
                    next_state,
                    marker.event_id,
                    marker.event_sha256,
                    marker.database_sequence,
                    now,
                    task_id,
                ),
            )
            tx.projection_updated()
            self.store.fault("after_result_persistence")
            return {"task": self.task(task_id), "result_sha256": result_sha}

        return self.store.command(idempotency_key, command, operation)[0]

    def request_cancellation(
        self,
        task_id: str,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        command = {
            "command": "request_cancellation",
            "task_id": task_id,
            "expected_version": expected_version,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version("tasks", "task_id", task_id, expected_version)
            row = self._task_row(task_id)
            if row["state"] in {"proposed", "awaiting_approval", "ready", "expired"}:
                return self._transition_in_tx(
                    tx, row, "cancelled", expected_version, actor, {}, clear_lease=True
                )
            if row["state"] not in {"leased", "running"}:
                raise CoreError(f"task in {row['state']} cannot be cancelled")
            return self._transition_in_tx(
                tx,
                row,
                "cancellation_requested",
                expected_version,
                actor,
                {"fenced_run_id": row["current_run_id"]},
                clear_fence=True,
            )

        return self.store.command(idempotency_key, command, operation)[0]

    def confirm_cancellation(
        self,
        task_id: str,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        command = {
            "command": "confirm_cancellation",
            "task_id": task_id,
            "expected_version": expected_version,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version("tasks", "task_id", task_id, expected_version)
            row = self._task_row(task_id)
            if row["state"] != "cancellation_requested":
                raise CoreError("cancellation was not requested")
            uncertain = self.store.conn.execute(
                "SELECT COUNT(*) FROM actions WHERE task_id = ? AND state IN ('prepared','dispatched','unknown')",
                (task_id,),
            ).fetchone()[0]
            if uncertain:
                raise CoreError("task has unresolved actions")
            return self._transition_in_tx(
                tx,
                row,
                "cancelled",
                expected_version,
                actor,
                {},
                run_status="cancelled",
                clear_lease=True,
            )

        return self.store.command(idempotency_key, command, operation)[0]

    def expire_lease(
        self,
        task_id: str,
        *,
        expected_version: int,
        replay_safe: bool,
        actor: str,
        idempotency_key: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        command = {
            "command": "expire_lease",
            "task_id": task_id,
            "expected_version": expected_version,
            "replay_safe": replay_safe,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version("tasks", "task_id", task_id, expected_version)
            row = self._task_row(task_id)
            if row["state"] not in {"leased", "running"}:
                raise CoreError("task has no expirable lease")
            if parse_time(str(row["lease_expires_at"])) > parse_time(now or utc_now()):
                raise CoreError("lease has not expired")
            uncertain = self.store.conn.execute(
                "SELECT COUNT(*) FROM actions WHERE task_id = ? AND state IN ('dispatched','unknown')",
                (task_id,),
            ).fetchone()[0]
            if uncertain or not replay_safe:
                next_state = "needs_reconciliation"
            elif int(row["attempt_count"]) >= int(row["max_attempts"]):
                next_state = "failed_terminal"
            else:
                next_state = "ready"
            return self._transition_in_tx(
                tx,
                row,
                next_state,
                expected_version,
                actor,
                {"replay_safe": replay_safe, "unresolved_actions": int(uncertain)},
                run_status="expired",
                clear_lease=True,
            )

        return self.store.command(idempotency_key, command, operation)[0]

    def prepare_action(
        self,
        fields: dict[str, Any],
        *,
        fencing_token: str,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        _required(
            fields,
            "task_id",
            "run_id",
            "capability",
            "target",
            "provider",
            "canonical_parameters",
            "approval_id",
            "approval_sha256",
            "operation_idempotency_key",
        )
        _reject_secret_keys(fields)
        command = {"command": "prepare_action", "fields": fields, "actor": actor}

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            task = self._task_row(fields["task_id"])
            self._require_current_lease(task, fields["run_id"], fencing_token)
            if task["state"] != "running":
                raise CoreError("actions require a running task")
            existing = self.store.conn.execute(
                "SELECT action_id FROM actions WHERE operation_idempotency_key = ?",
                (fields["operation_idempotency_key"],),
            ).fetchone()
            if existing is not None:
                raise CoreError(
                    "operation idempotency key already belongs to "
                    + str(existing["action_id"])
                )
            action_id = fields.get("action_id") or new_id("action")
            now = utc_now()
            record = {
                "schema_version": "city2.action/v1",
                "action_id": action_id,
                "aggregate_version": 1,
                "task_id": fields["task_id"],
                "task_revision": task["task_revision"],
                "run_id": fields["run_id"],
                "capability": fields["capability"],
                "target": fields["target"],
                "provider": fields["provider"],
                "canonical_parameters": fields["canonical_parameters"],
                "parameters_sha256": sha256_json(fields["canonical_parameters"]),
                "approval_id": fields["approval_id"],
                "approval_sha256": fields["approval_sha256"],
                "operation_idempotency_key": fields["operation_idempotency_key"],
                "state": "prepared",
                "prepared_at": now,
                "updated_at": now,
            }
            if "compensation" in fields:
                compensation = fields["compensation"]
                expected_compensation_sha = sha256_json(
                    compensation["canonical_parameters"]
                )
                if compensation.get("parameters_sha256") != expected_compensation_sha:
                    raise CoreError("compensation parameters_sha256 mismatch")
                record["compensation"] = compensation
            self._validate(record, "action.schema.json")
            marker = tx.append_event(
                aggregate_type="action",
                aggregate_id=action_id,
                event_type="action.prepared",
                aggregate_version=1,
                actor=actor,
                payload={"action": record},
                sensitivity="confidential",
            )
            self.store.conn.execute(
                """INSERT INTO actions
                   (action_id, aggregate_version, task_id, task_revision, run_id,
                    operation_idempotency_key, state, record_json, last_event_id,
                    last_event_sha256, event_high_water, created_at, updated_at)
                   VALUES (?, 1, ?, ?, ?, ?, 'prepared', ?, ?, ?, ?, ?, ?)""",
                (
                    action_id,
                    fields["task_id"],
                    task["task_revision"],
                    fields["run_id"],
                    fields["operation_idempotency_key"],
                    canonical_json(record),
                    marker.event_id,
                    marker.event_sha256,
                    marker.database_sequence,
                    now,
                    now,
                ),
            )
            tx.projection_updated()
            return record

        return self.store.command(idempotency_key, command, operation)[0]

    def begin_action_dispatch(
        self,
        action_id: str,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._action_transition(
            action_id,
            expected_version=expected_version,
            from_states={"prepared"},
            to_state="dispatched",
            actor=actor,
            idempotency_key=idempotency_key,
            details={},
            fault_boundary="after_dispatch_recorded",
        )

    def reconcile_action(
        self,
        action_id: str,
        outcome: str,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
        provider_operation_id: str | None = None,
        provider_evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if outcome not in {"confirmed", "failed", "unknown", "compensated"}:
            raise CoreError(f"invalid reconciliation outcome: {outcome}")
        if outcome == "confirmed" and (
            not provider_operation_id or not provider_evidence
        ):
            raise CoreError(
                "confirmation requires durable provider operation ID and evidence"
            )
        details: dict[str, Any] = {}
        if provider_operation_id:
            details["provider_operation_id"] = provider_operation_id
        if provider_evidence:
            details["provider_evidence"] = provider_evidence
        allowed = {
            "confirmed": {"dispatched", "unknown"},
            "failed": {"prepared", "dispatched", "unknown"},
            "unknown": {"dispatched"},
            "compensated": {"confirmed"},
        }
        return self._action_transition(
            action_id,
            expected_version=expected_version,
            from_states=allowed[outcome],
            to_state=outcome,
            actor=actor,
            idempotency_key=idempotency_key,
            details=details,
            fault_boundary="after_action_acknowledgement",
            escalate=outcome == "unknown",
        )

    def task(self, task_id: str) -> dict[str, Any]:
        row = self._task_row(task_id)
        revision = self._task_revision(task_id, int(row["task_revision"]))
        record = {
            "schema_version": "city2.task-record/v1",
            "task_id": row["task_id"],
            "task_revision": row["task_revision"],
            "task_envelope_sha256": row["task_sha256"],
            "objective_id": row["objective_id"],
            "objective_revision": row["objective_revision"],
            "objective_sha256": row["objective_sha256"],
            "aggregate_version": row["aggregate_version"],
            "state": row["state"],
            "attempt_count": row["attempt_count"],
            "max_attempts": row["max_attempts"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if row["current_run_id"]:
            record["current_run_id"] = row["current_run_id"]
        if "review_id" in revision:
            record["review_id"] = revision["review_id"]
        if (
            row["lease_owner"]
            and row["lease_fencing_token"]
            and row["lease_expires_at"]
        ):
            record["lease"] = {
                "owner": row["lease_owner"],
                "fencing_token": row["lease_fencing_token"],
                "expires_at": row["lease_expires_at"],
                "attempt_number": row["attempt_count"],
                "expected_task_version": row["aggregate_version"],
            }
        return record

    def objective(self, objective_id: str) -> dict[str, Any]:
        return json.loads(self._objective_row(objective_id)["record_json"])

    def action(self, action_id: str) -> dict[str, Any]:
        row = self._action_row(action_id)
        return json.loads(row["record_json"])

    def status(self) -> dict[str, Any]:
        report = self.store.verify_integrity()
        task_counts = {
            str(row["state"]): int(row["count"])
            for row in self.store.conn.execute(
                "SELECT state, COUNT(*) AS count FROM tasks GROUP BY state ORDER BY state"
            )
        }
        action_counts = {
            str(row["state"]): int(row["count"])
            for row in self.store.conn.execute(
                "SELECT state, COUNT(*) AS count FROM actions GROUP BY state ORDER BY state"
            )
        }
        return {
            "ok": True,
            "database_id": report["database_id"],
            "schema_version": int(self.store.meta("schema_version")),
            "application_version": self.store.meta("application_version"),
            "event_high_water": report["event_high_water"],
            "journal_mode": "wal",
            "synchronous": "full",
            "objectives": int(
                self.store.conn.execute("SELECT COUNT(*) FROM objectives").fetchone()[0]
            ),
            "tasks": task_counts,
            "actions": action_counts,
        }

    def _simple_task_transition(
        self,
        task_id: str,
        *,
        to_state: str,
        allowed_from: set[str],
        expected_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        command = {
            "command": "task_transition",
            "task_id": task_id,
            "to_state": to_state,
            "expected_version": expected_version,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version("tasks", "task_id", task_id, expected_version)
            row = self._task_row(task_id)
            if row["state"] not in allowed_from:
                raise CoreError(
                    f"task transition {row['state']} -> {to_state} is not allowed"
                )
            return self._transition_in_tx(
                tx, row, to_state, expected_version, actor, {}
            )

        return self.store.command(idempotency_key, command, operation)[0]

    def _transition_in_tx(
        self,
        tx: WriteTransaction,
        row: Any,
        to_state: str,
        expected_version: int,
        actor: str,
        details: dict[str, Any],
        *,
        run_status: str | None = None,
        clear_lease: bool = False,
        clear_fence: bool = False,
    ) -> dict[str, Any]:
        task_id = str(row["task_id"])
        marker = tx.append_event(
            aggregate_type="task",
            aggregate_id=task_id,
            event_type=f"task.{to_state}",
            aggregate_version=expected_version + 1,
            actor=actor,
            payload={"from": row["state"], "to": to_state, **details},
        )
        now = utc_now()
        assignments = [
            "aggregate_version = ?",
            "state = ?",
            "last_event_id = ?",
            "last_event_sha256 = ?",
            "event_high_water = ?",
            "updated_at = ?",
        ]
        values: list[Any] = [
            expected_version + 1,
            to_state,
            marker.event_id,
            marker.event_sha256,
            marker.database_sequence,
            now,
        ]
        if clear_lease:
            assignments.extend(
                [
                    "current_run_id = NULL",
                    "lease_owner = NULL",
                    "lease_fencing_token = NULL",
                    "lease_expires_at = NULL",
                ]
            )
        elif clear_fence:
            assignments.extend(
                [
                    "lease_owner = NULL",
                    "lease_fencing_token = NULL",
                    "lease_expires_at = NULL",
                ]
            )
        values.append(task_id)
        self.store.conn.execute(
            f"UPDATE tasks SET {', '.join(assignments)} WHERE task_id = ?", values
        )
        if run_status and row["current_run_id"]:
            self.store.conn.execute(
                """UPDATE runs SET status = ?, updated_at = ?
                   WHERE run_id = ? AND status != 'completed_after_cancel'""",
                (run_status, now, row["current_run_id"]),
            )
        tx.projection_updated()
        return self.task(task_id)

    def _action_transition(
        self,
        action_id: str,
        *,
        expected_version: int,
        from_states: set[str],
        to_state: str,
        actor: str,
        idempotency_key: str,
        details: dict[str, Any],
        fault_boundary: str,
        escalate: bool = False,
    ) -> dict[str, Any]:
        command = {
            "command": "action_transition",
            "action_id": action_id,
            "expected_version": expected_version,
            "to_state": to_state,
            "details": details,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version("actions", "action_id", action_id, expected_version)
            row = self._action_row(action_id)
            if row["state"] not in from_states:
                raise CoreError(
                    f"action transition {row['state']} -> {to_state} is not allowed"
                )
            record = json.loads(row["record_json"])
            now = utc_now()
            record.update(
                aggregate_version=expected_version + 1, state=to_state, updated_at=now
            )
            if to_state == "dispatched":
                record["dispatched_at"] = now
            if to_state == "confirmed":
                record["confirmed_at"] = now
            record.update(details)
            self._validate(record, "action.schema.json")
            marker = tx.append_event(
                aggregate_type="action",
                aggregate_id=action_id,
                event_type=f"action.{to_state}",
                aggregate_version=expected_version + 1,
                actor=actor,
                payload={"from": row["state"], "to": to_state, **details},
                sensitivity="confidential",
            )
            evidence_sha = (
                sha256_json(details["provider_evidence"])
                if details.get("provider_evidence")
                else None
            )
            self.store.conn.execute(
                """UPDATE actions SET aggregate_version = ?, state = ?, record_json = ?,
                   provider_operation_id = ?, provider_evidence_sha256 = ?, last_event_id = ?,
                   last_event_sha256 = ?, event_high_water = ?, updated_at = ? WHERE action_id = ?""",
                (
                    expected_version + 1,
                    to_state,
                    canonical_json(record),
                    details.get("provider_operation_id"),
                    evidence_sha,
                    marker.event_id,
                    marker.event_sha256,
                    marker.database_sequence,
                    now,
                    action_id,
                ),
            )
            if escalate:
                task = self._task_row(row["task_id"])
                if (
                    task["state"] not in TASK_TERMINAL
                    and task["state"] != "needs_reconciliation"
                ):
                    task_marker = tx.append_event(
                        aggregate_type="task",
                        aggregate_id=task["task_id"],
                        event_type="task.needs_reconciliation",
                        aggregate_version=int(task["aggregate_version"]) + 1,
                        actor=actor,
                        payload={
                            "action_id": action_id,
                            "reason": "unknown_external_outcome",
                        },
                    )
                    self.store.conn.execute(
                        """UPDATE tasks SET aggregate_version = aggregate_version + 1,
                           state = 'needs_reconciliation', last_event_id = ?, last_event_sha256 = ?,
                           event_high_water = ?, lease_owner = NULL,
                           lease_fencing_token = NULL, lease_expires_at = NULL,
                           updated_at = ? WHERE task_id = ?""",
                        (
                            task_marker.event_id,
                            task_marker.event_sha256,
                            task_marker.database_sequence,
                            now,
                            task["task_id"],
                        ),
                    )
            tx.projection_updated()
            self.store.fault(fault_boundary)
            return self.action(action_id)

        return self.store.command(idempotency_key, command, operation)[0]

    def _require_current_lease(self, row: Any, run_id: str, fencing_token: str) -> None:
        if (
            row["current_run_id"] != run_id
            or row["lease_fencing_token"] != fencing_token
        ):
            raise ConflictError("stale or foreign lease fencing token")
        if parse_time(str(row["lease_expires_at"])) <= parse_time(utc_now()):
            raise ConflictError("lease has expired")

    def _objective_row(self, objective_id: str) -> Any:
        row = self.store.conn.execute(
            "SELECT * FROM objectives WHERE objective_id = ?", (objective_id,)
        ).fetchone()
        if row is None:
            raise CoreError(f"unknown objective: {objective_id}")
        return row

    def _task_row(self, task_id: str) -> Any:
        row = self.store.conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise CoreError(f"unknown task: {task_id}")
        return row

    def _run_row(self, run_id: str) -> Any:
        row = self.store.conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise CoreError(f"unknown run: {run_id}")
        return row

    def _action_row(self, action_id: str) -> Any:
        row = self.store.conn.execute(
            "SELECT * FROM actions WHERE action_id = ?", (action_id,)
        ).fetchone()
        if row is None:
            raise CoreError(f"unknown action: {action_id}")
        return row

    def _task_revision(self, task_id: str, revision: int) -> dict[str, Any]:
        row = self.store.conn.execute(
            "SELECT record_json FROM task_revisions WHERE task_id = ? AND task_revision = ?",
            (task_id, revision),
        ).fetchone()
        if row is None:
            raise CoreError(f"missing task revision: {task_id}@{revision}")
        return json.loads(row[0])
