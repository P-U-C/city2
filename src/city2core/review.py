"""Independent maker/checker enforcement for M4."""

from __future__ import annotations

import json
from typing import Any

from .core import Core, CoreError
from .memory import MemoryService
from .model import canonical_json, digest_profile, new_id, sha256_json, utc_now
from .schema import ValidationError, validate_named
from .store import Store


class ReviewService:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.core = Core(store)
        self.memory = MemoryService(store)

    def register_manifest(
        self, manifest: dict[str, Any], *, idempotency_key: str
    ) -> dict[str, Any]:
        try:
            validate_named(manifest, "agent.schema.json", self.store.schemas)
        except ValidationError as error:
            raise CoreError(f"agent manifest invalid: {error}") from error
        if manifest["manifest_sha256"] != digest_profile(
            manifest, {"manifest_sha256", "aggregate_version"}
        ):
            raise CoreError("agent manifest hash mismatch")
        command = {"command": "register_agent_manifest", "manifest": manifest}

        def operation(_tx: Any) -> dict[str, Any]:
            self.store.conn.execute(
                """INSERT OR IGNORE INTO agent_manifests
                   (agent_id, manifest_version, manifest_sha256, manifest_json, registered_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    manifest["agent_id"],
                    manifest["manifest_version"],
                    manifest["manifest_sha256"],
                    canonical_json(manifest),
                    utc_now(),
                ),
            )
            return manifest

        return self.store.command(idempotency_key, command, operation)[0]

    def review_task(
        self,
        task_id: str,
        reviewer_agent_id: str,
        decision: str,
        *,
        expected_version: int,
        findings: list[dict[str, Any]],
        finding_dispositions: dict[str, str] | None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        task = self.core.task(task_id)
        if task["state"] != "review":
            raise CoreError("task is not ready for review")
        run = self.store.conn.execute(
            "SELECT * FROM runs WHERE task_id = ? ORDER BY attempt_number DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if run is None or run["result_json"] is None:
            raise CoreError("review requires a persisted result")
        envelope = json.loads(run["task_envelope_json"])
        result = json.loads(run["result_json"])
        maker_id = envelope["resolved_agent_id"]
        maker = self._manifest(maker_id, envelope["resolved_manifest_version"])
        reviewer = self._latest_manifest(reviewer_agent_id)
        independence = self._independence(maker, reviewer)
        if maker_id == reviewer_agent_id:
            raise CoreError("maker cannot review its own work")
        if reviewer["review_policy"] != "independent" or not reviewer["enabled"]:
            raise CoreError("reviewer manifest is not enabled for independent review")
        if not independence["operation_capability_separation"]:
            raise CoreError("reviewer can execute the maker operation")
        checks = self._deterministic_checks(envelope, result)
        if decision == "accepted" and not all(checks.values()):
            raise CoreError("deterministic evidence/policy checks block acceptance")
        proposed_review_id = new_id("review")
        finding_ids = [item["finding_id"] for item in findings]
        reviewed = self.core.review_task(
            task_id,
            decision,
            expected_version=expected_version,
            review_id=proposed_review_id,
            finding_ids=finding_ids,
            finding_dispositions=finding_dispositions,
            actor=f"agent:{reviewer['name']}",
            idempotency_key=idempotency_key + ":transition",
        )
        latest_event = self.store.conn.execute(
            """SELECT payload_json FROM events WHERE aggregate_id = ?
               ORDER BY aggregate_sequence DESC LIMIT 1""",
            (task_id,),
        ).fetchone()
        review_id = json.loads(latest_event["payload_json"])["review_id"]
        command = {
            "command": "record_independent_review",
            "review_id": review_id,
            "task_id": task_id,
            "decision": decision,
            "checks": checks,
            "findings": findings,
            "independence": independence,
        }

        def record(_tx: Any) -> dict[str, Any]:
            self.store.conn.execute(
                """INSERT OR IGNORE INTO task_reviews
                   (review_id, task_id, run_id, maker_agent_id, reviewer_agent_id,
                    decision, deterministic_checks_sha256, findings_json,
                    independence_json, reviewed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    review_id,
                    task_id,
                    run["run_id"],
                    maker_id,
                    reviewer_agent_id,
                    decision,
                    sha256_json(checks),
                    canonical_json(findings),
                    canonical_json(independence),
                    utc_now(),
                ),
            )
            return {"task": reviewed, "review_id": review_id}

        return self.store.command(idempotency_key + ":record", command, record)[0]

    def promote_memory(
        self,
        memory_id: str,
        reviewer_agent_id: str,
        *,
        expected_version: int,
        source_checks: list[dict[str, str]],
        idempotency_key: str,
    ) -> dict[str, Any]:
        record = self.memory.get(memory_id)
        reviewer = self._latest_manifest(reviewer_agent_id)
        maker = self._manifest_by_actor(record["created_by"])
        independence = self._independence(maker, reviewer)
        if (
            not independence["identity_separation"]
            or not independence["operation_capability_separation"]
        ):
            raise CoreError("memory promotion lacks independent reviewer separation")
        return self.memory.review_candidate(
            memory_id,
            "accepted",
            expected_version=expected_version,
            reviewer=f"agent:{reviewer['name']}",
            source_checks=source_checks,
            independence={
                "separate_identity": True,
                "separate_session": True,
                "no_shared_write_credential": independence["credential_separation"],
            },
            idempotency_key=idempotency_key,
        )

    def _deterministic_checks(
        self, envelope: dict[str, Any], result: dict[str, Any]
    ) -> dict[str, bool]:
        passed = {
            item["criterion_id"]
            for item in result["checks"] + result["evidence"]
            if item["result"] == "pass"
        }
        mandatory = {
            item["criterion_id"]
            for item in envelope["acceptance_criteria"]
            if item["mandatory"]
        }
        unresolved_actions = self.store.conn.execute(
            """SELECT COUNT(*) FROM actions WHERE run_id = ?
               AND state IN ('prepared','dispatched','unknown')""",
            (result["run_id"],),
        ).fetchone()[0]
        return {
            "mandatory_criteria_pass": mandatory.issubset(passed),
            "result_completed": result["run_status"] == "completed",
            "no_unresolved_actions": unresolved_actions == 0,
            "fence_matches": result["lease_fencing_token"]
            == envelope["lease_fencing_token"],
        }

    @staticmethod
    def _independence(
        maker: dict[str, Any], reviewer: dict[str, Any]
    ) -> dict[str, bool]:
        return {
            "identity_separation": maker["agent_id"] != reviewer["agent_id"],
            "operation_capability_separation": not set(maker["tools"]).intersection(
                reviewer["tools"]
            ),
            "credential_separation": not set(maker["credential_handles"]).intersection(
                reviewer["credential_handles"]
            ),
            "model_policy_separation": maker["model_policy"]
            != reviewer["model_policy"],
        }

    def _manifest(self, agent_id: str, version: int) -> dict[str, Any]:
        row = self.store.conn.execute(
            "SELECT manifest_json FROM agent_manifests WHERE agent_id = ? AND manifest_version = ?",
            (agent_id, version),
        ).fetchone()
        if row is None:
            raise CoreError("agent manifest is not registered")
        return json.loads(row[0])

    def _latest_manifest(self, agent_id: str) -> dict[str, Any]:
        row = self.store.conn.execute(
            """SELECT manifest_json FROM agent_manifests WHERE agent_id = ?
               ORDER BY manifest_version DESC LIMIT 1""",
            (agent_id,),
        ).fetchone()
        if row is None:
            raise CoreError("reviewer manifest is not registered")
        return json.loads(row[0])

    def _manifest_by_actor(self, actor: str) -> dict[str, Any]:
        name = actor.removeprefix("agent:")
        for row in self.store.conn.execute("SELECT manifest_json FROM agent_manifests"):
            manifest = json.loads(row[0])
            if manifest["name"] == name:
                return manifest
        raise CoreError("maker manifest is not registered")
