"""Offline M3 interface and runner adapters; no live routing or deployment."""

from __future__ import annotations

import re
from typing import Any, Protocol

from .core import Core, CoreError
from .model import digest_profile, sha256_json, utc_now, uuid7
from .schema import ValidationError, validate_named
from .store import IntegrityError, Store


PUBLIC_KEY = re.compile(r"^[0-9a-f]{64}$")


class BuzzAdapter:
    """Owner-only, A0 ingress whose durable authority is Core rather than Buzz."""

    def __init__(
        self, store: Store, *, owner_public_key: str, allowed_channels: set[str]
    ) -> None:
        if not PUBLIC_KEY.fullmatch(owner_public_key):
            raise CoreError("Buzz owner key must be public hex")
        if not allowed_channels:
            raise CoreError("Buzz adapter requires an explicit channel allowlist")
        self.store = store
        self.core = Core(store)
        self.owner_public_key = owner_public_key
        self.allowed_channels = allowed_channels

    def ingest_task(
        self, message: dict[str, Any], task_fields: dict[str, Any]
    ) -> dict[str, Any]:
        required = {"message_id", "author_public_key", "channel_id", "created_at"}
        if required - set(message):
            raise CoreError("Buzz message envelope is incomplete")
        if message["author_public_key"] != self.owner_public_key:
            raise CoreError("Buzz task ingress is owner-only")
        if message["channel_id"] not in self.allowed_channels:
            raise CoreError("Buzz channel is not authorized for task ingress")
        if task_fields.get("authority_class") != "A0":
            raise CoreError("initial Buzz coordinator is restricted to A0")
        message_profile = {
            "message_id": message["message_id"],
            "author_public_key": message["author_public_key"],
            "channel_id": message["channel_id"],
            "thread_id": message.get("thread_id"),
            "created_at": message["created_at"],
            "task_fields_sha256": sha256_json(task_fields),
        }
        message_sha = sha256_json(message_profile)
        prior = self.store.conn.execute(
            """SELECT message_sha256, task_id FROM interface_messages
               WHERE interface = 'buzz' AND message_id = ?""",
            (message["message_id"],),
        ).fetchone()
        if prior is not None:
            if prior["message_sha256"] != message_sha:
                raise IntegrityError("Buzz message identity collision")
            return {"task": self.core.task(prior["task_id"]), "deduplicated": True}

        task = self.core.create_task(
            task_fields,
            actor="human:chad",
            idempotency_key=f"buzz:message:{message['message_id']}",
        )
        command = {
            "command": "record_buzz_ingress",
            "message": message_profile,
            "task_id": task["task_id"],
        }

        def record_mapping(_tx: Any) -> dict[str, Any]:
            self.store.conn.execute(
                """INSERT INTO interface_messages
                   (interface, message_id, author_id, channel_id, thread_id,
                    message_sha256, task_id, ingested_at)
                   VALUES ('buzz', ?, ?, ?, ?, ?, ?, ?)""",
                (
                    message["message_id"],
                    message["author_public_key"],
                    message["channel_id"],
                    message.get("thread_id"),
                    message_sha,
                    task["task_id"],
                    utc_now(),
                ),
            )
            return {"task_id": task["task_id"]}

        self.store.command(
            f"buzz:mapping:{message['message_id']}", command, record_mapping
        )
        return {"task": task, "deduplicated": False}

    def render_task(self, task_id: str) -> dict[str, Any]:
        task = self.core.task(task_id)
        return {
            "schema_version": "city2.buzz-task-view/v1",
            "task_id": task_id,
            "state": task["state"],
            "task_revision": task["task_revision"],
            "attempt_count": task["attempt_count"],
            "updated_at": task["updated_at"],
        }

    def ceo_projection(self) -> dict[str, Any]:
        objectives = [
            {"objective_id": row["objective_id"], "status": row["status"]}
            for row in self.store.conn.execute(
                "SELECT objective_id, status FROM objectives ORDER BY objective_id"
            )
        ]
        approvals = [
            row["task_id"]
            for row in self.store.conn.execute(
                "SELECT task_id FROM tasks WHERE state = 'awaiting_approval' ORDER BY task_id"
            )
        ]
        exceptions = [
            {"type": "task", "id": row["task_id"], "state": row["state"]}
            for row in self.store.conn.execute(
                """SELECT task_id, state FROM tasks
                   WHERE state IN ('needs_reconciliation','failed_terminal') ORDER BY task_id"""
            )
        ]
        exceptions.extend(
            {"type": "memory_conflict", "id": row["conflict_id"], "state": row["state"]}
            for row in self.store.conn.execute(
                "SELECT conflict_id, state FROM memory_conflicts WHERE state = 'open' ORDER BY conflict_id"
            )
        )
        return {
            "schema_version": "city2.ceo-projection/v1",
            "authority_class": "A0",
            "objectives": objectives,
            "approvals": approvals,
            "exceptions": exceptions,
            "event_high_water": int(self.store.meta("global_sequence")),
        }


class Runner(Protocol):
    def capabilities(self) -> dict[str, Any]: ...

    def run(self, request: dict[str, Any]) -> dict[str, Any]: ...


class PfTerminalRunnerAdapter:
    """Portable boundary for fresh PfTerminal turns; execution is activation-gated."""

    def __init__(self, store: Store, *, runner_version: str) -> None:
        self.store = store
        self.runner_version = runner_version

    def capabilities(self) -> dict[str, Any]:
        manifest = {
            "schema_version": "city2.runner-capability/v1",
            "runner_id": "pfterminal-headless",
            "runner_version": self.runner_version,
            "contract_versions": ["city2.task/v1", "city2.result/v1"],
            "capabilities": {
                "structured_output": "enforced",
                "tool_schema_fidelity": "enforced",
                "sandboxing": "host_policy",
                "cancellation": "hard",
                "usage_accounting": "estimated",
                "model_controls": "partial",
                "budget_enforcement": "best_effort",
                "artifact_hashing": "sha256",
            },
            "unsupported": [],
            "degraded": [
                {"capability": "usage_accounting", "reason_code": "provider_estimate"},
                {"capability": "model_controls", "reason_code": "provider_boundary"},
                {
                    "capability": "budget_enforcement",
                    "reason_code": "cooperative_limit",
                },
            ],
            "manifest_sha256": "",
            "generated_at": utc_now(),
        }
        manifest["manifest_sha256"] = digest_profile(manifest, {"manifest_sha256"})
        validate_named(manifest, "runner-capability.schema.json", self.store.schemas)
        return manifest

    def negotiate(
        self, manifest: dict[str, Any], required: dict[str, set[str]]
    ) -> dict[str, Any]:
        try:
            validate_named(
                manifest, "runner-capability.schema.json", self.store.schemas
            )
        except ValidationError as error:
            raise CoreError(f"invalid runner manifest: {error}") from error
        if manifest["manifest_sha256"] != digest_profile(manifest, {"manifest_sha256"}):
            raise CoreError("runner capability manifest hash mismatch")
        degraded = {item["capability"] for item in manifest["degraded"]}
        failures = []
        for capability, accepted_values in sorted(required.items()):
            actual = manifest["capabilities"].get(capability)
            if (
                actual is None
                or actual == "unsupported"
                or actual not in accepted_values
            ):
                failures.append(f"{capability}:unsupported")
            elif capability in degraded:
                failures.append(f"{capability}:degraded")
        if failures:
            raise CoreError(
                "runner capability negotiation denied: " + ",".join(failures)
            )
        return {
            "decision": "allow",
            "runner_id": manifest["runner_id"],
            "manifest_sha256": manifest["manifest_sha256"],
        }

    def render_fresh_request(
        self, task_envelope: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        validate_named(task_envelope, "task-envelope.schema.json", self.store.schemas)
        manifest = context["manifest"]
        if task_envelope["task_envelope_sha256"] != digest_profile(
            task_envelope, {"task_envelope_sha256"}
        ):
            raise CoreError("task envelope hash mismatch")
        if manifest["pack_sha256"] != digest_profile(manifest, {"pack_sha256"}):
            raise CoreError("context manifest hash mismatch")
        if manifest["task_envelope_sha256"] != task_envelope["task_envelope_sha256"]:
            raise CoreError("context does not bind the task envelope")
        return {
            "schema_version": "city2.runner-request/v1",
            "fresh_session": True,
            "task_envelope": task_envelope,
            "context_manifest": manifest,
            "context_content": context["content"],
            "conversation_history": [],
        }

    def prepare_dispatch(
        self,
        run_id: str,
        task_envelope: dict[str, Any],
        context_manifest: dict[str, Any],
        manifest: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.negotiate(manifest, {})
        if task_envelope["task_envelope_sha256"] != digest_profile(
            task_envelope, {"task_envelope_sha256"}
        ):
            raise CoreError("task envelope hash mismatch")
        if context_manifest["pack_sha256"] != digest_profile(
            context_manifest, {"pack_sha256"}
        ):
            raise CoreError("context manifest hash mismatch")
        command = {
            "command": "prepare_runner_dispatch",
            "run_id": run_id,
            "task_envelope_sha256": task_envelope["task_envelope_sha256"],
            "context_manifest_sha256": sha256_json(context_manifest),
            "capability_manifest_sha256": manifest["manifest_sha256"],
        }

        def operation(_tx: Any) -> dict[str, Any]:
            prior = self.store.conn.execute(
                "SELECT * FROM runner_dispatches WHERE run_id = ?", (run_id,)
            ).fetchone()
            if prior is not None:
                return {"dispatch_id": prior["dispatch_id"], "state": prior["state"]}
            dispatch_id = "dsp_" + uuid7()
            now = utc_now()
            self.store.conn.execute(
                """INSERT INTO runner_dispatches
                   (dispatch_id, run_id, runner_id, capability_manifest_sha256,
                    task_envelope_sha256, context_manifest_sha256, state,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'prepared', ?, ?)""",
                (
                    dispatch_id,
                    run_id,
                    manifest["runner_id"],
                    manifest["manifest_sha256"],
                    task_envelope["task_envelope_sha256"],
                    sha256_json(context_manifest),
                    now,
                    now,
                ),
            )
            return {"dispatch_id": dispatch_id, "state": "prepared"}

        return self.store.command(idempotency_key, command, operation)[0]

    def validate_result(
        self, result: dict[str, Any], task_envelope: dict[str, Any]
    ) -> None:
        validate_named(result, "result.schema.json", self.store.schemas)
        if (
            result["task_id"] != task_envelope["task_id"]
            or result["task_revision"] != task_envelope["task_revision"]
            or result["lease_fencing_token"] != task_envelope["lease_fencing_token"]
        ):
            raise CoreError("runner result does not match the fenced task")


class FixtureRunner:
    """Deterministic provider-substitution fixture, never a production runner."""

    def __init__(self, provider: str) -> None:
        self.provider = provider

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        task = request["task_envelope"]
        return {
            "semantic": {
                "task_id": task["task_id"],
                "task_revision": task["task_revision"],
                "criteria": task["acceptance_criteria"],
                "authority_class": task["authority_class"],
                "fresh_session": request["fresh_session"],
                "conversation_history_empty": not request["conversation_history"],
            },
            "provider": self.provider,
            "latency_class": "fixture",
            "cost_class": "zero",
        }


def substitution_equivalent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left["semantic"] == right["semantic"]
