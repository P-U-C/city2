import importlib.util
import multiprocessing
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from city2core import ConflictError, Core, Store  # noqa: E402
from city2core.archive import (  # noqa: E402
    create_backup,
    generate_checkpoint_key,
    restore_backup,
    verify_backup,
)
from city2core.core import CoreError  # noqa: E402
from city2core.model import canonical_json  # noqa: E402
from city2core.store import IdempotencyCollision, IntegrityError  # noqa: E402


VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "core_contract_validator", ROOT / "scripts" / "validate_contracts.py"
)
validator = importlib.util.module_from_spec(VALIDATOR_SPEC)
assert VALIDATOR_SPEC.loader is not None
VALIDATOR_SPEC.loader.exec_module(validator)


ACTOR = "human:chad"
AGENT_ID = "agt_01980000-0000-7000-8000-000000000001"
APPROVAL_ID = "apr_01980000-0000-7000-8000-000000000009"
ARTIFACT_ID = "art_01980000-0000-7000-8000-00000000000a"
REVIEW_ID = "rev_01980000-0000-7000-8000-00000000000b"
FINDING_ID = "fnd_01980000-0000-7000-8000-00000000000c"


def future(hours=1):
    return (
        (datetime.now(timezone.utc) + timedelta(hours=hours))
        .isoformat()
        .replace("+00:00", "Z")
    )


def objective_fields():
    return {
        "title": "M1 proof",
        "intent": "Prove deterministic Core behavior.",
        "accountable_owner": ACTOR,
        "review_at": future(24),
        "measurable_outcomes": [
            {"outcome_id": "oc_integrity", "measure": "checks", "target": "all pass"}
        ],
        "stop_conditions": ["Integrity cannot be proven."],
        "authority_ceiling": "A1",
        "budget": {
            "max_billable_usd": "1.00",
            "max_input_tokens": 1000,
            "max_output_tokens": 1000,
        },
    }


def task_fields(objective_id):
    return {
        "objective_id": objective_id,
        "task_type": "verification",
        "title": "Verify Core",
        "intent": "Exercise the M1 lifecycle.",
        "requested_role": "reviewer",
        "authority_class": "A1",
        "inputs": [],
        "constraints": ["no_external_changes"],
        "acceptance_criteria": [
            {
                "criterion_id": "ac_integrity",
                "requirement": "Integrity passes.",
                "mandatory": True,
            }
        ],
        "memory_scopes": ["company", "project:city2"],
        "time_budget_seconds": 300,
        "max_attempts": 2,
        "task_dedupe_key": "fixture:task:core-0001",
    }


def result_for(task, run_id, fence, status="completed"):
    return {
        "schema_version": "city2.result/v1",
        "task_id": task["task_id"],
        "task_revision": task["task_revision"],
        "run_id": run_id,
        "expected_task_version": task["aggregate_version"],
        "lease_fencing_token": fence,
        "run_status": status,
        "runner": {
            "id": "test-runner",
            "version": "1",
            "capability_manifest_sha256": "f" * 64,
        },
        "model": {
            "provider": "test-provider",
            "model": "test-model",
            "capability_profile": "test-v1",
        },
        "agent_manifest_version": 1,
        "agent_manifest_sha256": "a" * 64,
        "context_pack_ref": {"artifact_id": ARTIFACT_ID, "sha256": "b" * 64},
        "outcome": "done",
        "artifacts": [],
        "evidence": [],
        "checks": [],
        "memory_candidates": [],
        "approvals_requested": [],
        "usage": {"wall_seconds": 1, "input_tokens": 1, "output_tokens": 1},
        "errors": [],
    }


def kill_on(boundary):
    def hook(actual):
        if actual == boundary:
            os._exit(86)

    return hook


def killed_objective_transition(db_path, boundary, objective_id):
    store = Store.open(db_path, fault_hook=kill_on(boundary))
    Core(store).set_objective_status(
        objective_id,
        "active",
        expected_version=1,
        actor=ACTOR,
        idempotency_key="fixture:objective:activate",
    )


def setup_process_fixture(db_path, through):
    with Store.initialize(db_path) as store:
        core = Core(store)
        objective = core.create_objective(
            objective_fields(), actor=ACTOR, idempotency_key="process:objective:create"
        )
        objective = core.set_objective_status(
            objective["objective_id"],
            "active",
            expected_version=1,
            actor=ACTOR,
            idempotency_key="process:objective:active",
        )
        task = core.create_task(
            task_fields(objective["objective_id"]),
            actor=ACTOR,
            idempotency_key="process:task:create",
        )
        task = core.set_task_ready(
            task["task_id"],
            expected_version=1,
            actor=ACTOR,
            idempotency_key="process:task:ready",
        )
        state = {"task_id": task["task_id"]}
        if through == "ready":
            return state
        lease = core.lease_task(
            task["task_id"],
            expected_version=2,
            owner="service:test-runner",
            expires_at=future(),
            resolved_agent_id=AGENT_ID,
            resolved_manifest_version=1,
            resolved_manifest_sha256="a" * 64,
            actor="service:city2-core",
            idempotency_key="process:task:lease",
        )
        fence = lease["task_envelope"]["lease_fencing_token"]
        task = core.start_run(
            task["task_id"],
            lease["run_id"],
            fence,
            expected_version=3,
            actor="service:test-runner",
            idempotency_key="process:task:start",
        )
        state.update(run_id=lease["run_id"], fence=fence, task=task)
        if through == "running":
            return state
        action = core.prepare_action(
            {
                "task_id": task["task_id"],
                "run_id": lease["run_id"],
                "capability": "test_side_effect",
                "target": "fixture-target",
                "provider": "test-provider",
                "canonical_parameters": {"value": 1},
                "approval_id": APPROVAL_ID,
                "approval_sha256": "8" * 64,
                "operation_idempotency_key": "process:operation:0001",
            },
            fencing_token=fence,
            actor="service:test-runner",
            idempotency_key="process:action:prepare",
        )
        state["action_id"] = action["action_id"]
        if through == "prepared":
            return state
        core.begin_action_dispatch(
            action["action_id"],
            expected_version=1,
            actor="service:dispatcher",
            idempotency_key="process:action:dispatch",
        )
        return state


def killed_core_operation(db_path, boundary, operation, state):
    with Store.open(db_path, fault_hook=kill_on(boundary)) as store:
        core = Core(store)
        if operation == "lease":
            core.lease_task(
                state["task_id"],
                expected_version=2,
                owner="service:test-runner",
                expires_at=future(),
                resolved_agent_id=AGENT_ID,
                resolved_manifest_version=1,
                resolved_manifest_sha256="a" * 64,
                actor="service:city2-core",
                idempotency_key="process:kill:lease",
            )
        elif operation == "dispatch":
            core.begin_action_dispatch(
                state["action_id"],
                expected_version=1,
                actor="service:dispatcher",
                idempotency_key="process:kill:dispatch",
            )
        elif operation == "acknowledge":
            core.reconcile_action(
                state["action_id"],
                "confirmed",
                expected_version=2,
                actor="service:reconciler",
                idempotency_key="process:kill:ack",
                provider_operation_id="remote-1",
                provider_evidence={"artifact_id": ARTIFACT_ID, "sha256": "c" * 64},
            )
        elif operation == "result":
            core.submit_result(
                result_for(state["task"], state["run_id"], state["fence"]),
                actor="service:test-runner",
                idempotency_key="process:kill:result",
            )
        else:
            raise AssertionError(operation)


def killed_backup(db_path, output, private_key):
    with Store.open(db_path, fault_hook=kill_on("after_sqlite_backup")) as store:
        create_backup(store, output, signing_key=private_key, key_version="process-v1")


class CoreFixture(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="city2-core-test-"))
        self.db = self.temp / "core.sqlite"
        self.store = Store.initialize(self.db)
        self.core = Core(self.store)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp)

    def create_objective(self):
        objective = self.core.create_objective(
            objective_fields(), actor=ACTOR, idempotency_key="fixture:objective:create"
        )
        return self.core.set_objective_status(
            objective["objective_id"],
            "active",
            expected_version=1,
            actor=ACTOR,
            idempotency_key="fixture:objective:active",
        )

    def create_running_task(self):
        objective = self.create_objective()
        task = self.core.create_task(
            task_fields(objective["objective_id"]),
            actor=ACTOR,
            idempotency_key="fixture:task:create",
        )
        task = self.core.set_task_ready(
            task["task_id"],
            expected_version=1,
            actor=ACTOR,
            idempotency_key="fixture:task:ready",
        )
        lease = self.core.lease_task(
            task["task_id"],
            expected_version=2,
            owner="service:test-runner",
            expires_at=future(),
            resolved_agent_id=AGENT_ID,
            resolved_manifest_version=1,
            resolved_manifest_sha256="a" * 64,
            actor="service:city2-core",
            idempotency_key="fixture:task:lease",
        )
        task = self.core.start_run(
            task["task_id"],
            lease["run_id"],
            lease["task_envelope"]["lease_fencing_token"],
            expected_version=3,
            actor="service:test-runner",
            idempotency_key="fixture:task:start",
        )
        return task, lease

    def prepare_action(self, task, lease, operation_key="fixture:operation:0001"):
        return self.core.prepare_action(
            {
                "task_id": task["task_id"],
                "run_id": lease["run_id"],
                "capability": "git_push_branch",
                "target": "repository:P-U-C/city2",
                "provider": "git-host-reference",
                "canonical_parameters": {"branch": "codex/company-os-m1"},
                "approval_id": APPROVAL_ID,
                "approval_sha256": "8" * 64,
                "operation_idempotency_key": operation_key,
            },
            fencing_token=lease["task_envelope"]["lease_fencing_token"],
            actor="service:test-runner",
            idempotency_key="fixture:action:prepare:"
            + operation_key.rsplit(":", 1)[-1],
        )

    def validate(self, instance, schema):
        schemas = validator.SchemaStore()
        validator.validate_instance(
            instance, schemas.documents[schema], schemas, schema
        )

    def test_contract_outputs_and_happy_lifecycle(self):
        task, lease = self.create_running_task()
        self.validate(
            self.core.objective(task["objective_id"]), "objective.schema.json"
        )
        self.validate(task, "task-record.schema.json")
        self.validate(lease["task_envelope"], "task-envelope.schema.json")
        result = result_for(
            task, lease["run_id"], lease["task_envelope"]["lease_fencing_token"]
        )
        completed = self.core.submit_result(
            result, actor="service:test-runner", idempotency_key="fixture:result:submit"
        )
        self.assertEqual(completed["task"]["state"], "review")
        self.assertEqual(self.store.verify_integrity()["event_high_water"], 7)

    def test_objective_and_task_revisions_preserve_pinned_history(self):
        objective = self.create_objective()
        task = self.core.create_task(
            task_fields(objective["objective_id"]),
            actor=ACTOR,
            idempotency_key="fixture:revision:task-create",
        )
        revised_objective = self.core.revise_objective(
            objective["objective_id"],
            {"intent": "A materially revised objective."},
            expected_version=2,
            actor=ACTOR,
            idempotency_key="fixture:revision:objective",
        )
        self.assertEqual(revised_objective["objective_revision"], 2)
        self.assertEqual(task["objective_revision"], 1)
        self.assertNotEqual(
            revised_objective["objective_sha256"], task["objective_sha256"]
        )

        task = self.core.set_task_ready(
            task["task_id"],
            expected_version=1,
            actor=ACTOR,
            idempotency_key="fixture:revision:ready",
        )
        lease = self.core.lease_task(
            task["task_id"],
            expected_version=2,
            owner="service:test-runner",
            expires_at=future(),
            resolved_agent_id=AGENT_ID,
            resolved_manifest_version=1,
            resolved_manifest_sha256="a" * 64,
            actor="service:city2-core",
            idempotency_key="fixture:revision:lease",
        )
        task = self.core.start_run(
            task["task_id"],
            lease["run_id"],
            lease["task_envelope"]["lease_fencing_token"],
            expected_version=3,
            actor="service:test-runner",
            idempotency_key="fixture:revision:start",
        )
        result = result_for(
            task, lease["run_id"], lease["task_envelope"]["lease_fencing_token"]
        )
        task = self.core.submit_result(
            result,
            actor="service:test-runner",
            idempotency_key="fixture:revision:result",
        )["task"]
        task = self.core.review_task(
            task["task_id"],
            "changes_requested",
            expected_version=5,
            review_id=REVIEW_ID,
            finding_ids=[FINDING_ID],
            finding_dispositions=None,
            actor="agent:reviewer",
            idempotency_key="fixture:revision:review",
        )
        revised_task = self.core.revise_task(
            task["task_id"],
            {"intent": "Exercise the corrected M1 lifecycle."},
            expected_version=6,
            review_id=REVIEW_ID,
            unresolved_finding_ids=[FINDING_ID],
            actor=ACTOR,
            idempotency_key="fixture:revision:revise-task",
        )
        self.assertEqual(revised_task["state"], "ready")
        self.assertEqual(revised_task["task_revision"], 2)
        self.assertEqual(revised_task["attempt_count"], 1)
        second_lease = self.core.lease_task(
            task["task_id"],
            expected_version=7,
            owner="service:test-runner",
            expires_at=future(),
            resolved_agent_id=AGENT_ID,
            resolved_manifest_version=1,
            resolved_manifest_sha256="a" * 64,
            actor="service:city2-core",
            idempotency_key="fixture:revision:lease-two",
        )
        envelope = second_lease["task_envelope"]
        self.assertEqual(envelope["task_revision"], 2)
        self.assertEqual(envelope["review_id"], REVIEW_ID)
        self.assertEqual(envelope["unresolved_finding_ids"], [FINDING_ID])
        self.assertEqual(envelope["supersedes_run_id"], lease["run_id"])
        self.store.verify_integrity()

    def test_generated_values_are_stable_under_idempotent_retry(self):
        fields = objective_fields()
        first = self.core.create_objective(
            fields, actor=ACTOR, idempotency_key="fixture:objective:retry"
        )
        second = self.core.create_objective(
            fields, actor=ACTOR, idempotency_key="fixture:objective:retry"
        )
        self.assertEqual(first, second)
        first_task = self.core.create_task(
            task_fields(first["objective_id"]),
            actor=ACTOR,
            idempotency_key="fixture:task:retry",
        )
        second_task = self.core.create_task(
            task_fields(first["objective_id"]),
            actor=ACTOR,
            idempotency_key="fixture:task:retry",
        )
        self.assertEqual(first_task, second_task)
        self.assertEqual(self.store.meta("global_sequence"), "2")

    def test_idempotency_collision_and_version_conflict_change_nothing(self):
        objective = self.core.create_objective(
            objective_fields(), actor=ACTOR, idempotency_key="fixture:collision:key"
        )
        changed = objective_fields()
        changed["title"] = "Different"
        with self.assertRaises(IdempotencyCollision):
            self.core.create_objective(
                changed, actor=ACTOR, idempotency_key="fixture:collision:key"
            )
        with self.assertRaises(ConflictError):
            self.core.set_objective_status(
                objective["objective_id"],
                "active",
                expected_version=9,
                actor=ACTOR,
                idempotency_key="fixture:wrong:version",
            )
        self.assertEqual(self.store.meta("global_sequence"), "1")

    def test_stale_fence_is_denied(self):
        task, lease = self.create_running_task()
        with self.assertRaises(ConflictError):
            self.core.prepare_action(
                {
                    "task_id": task["task_id"],
                    "run_id": lease["run_id"],
                    "capability": "git_push_branch",
                    "target": "repository:P-U-C/city2",
                    "provider": "git-host-reference",
                    "canonical_parameters": {},
                    "approval_id": APPROVAL_ID,
                    "approval_sha256": "8" * 64,
                    "operation_idempotency_key": "fixture:operation:stale",
                },
                fencing_token="stale-fencing-token",
                actor="service:test-runner",
                idempotency_key="fixture:action:stale",
            )

    def test_secret_shaped_action_parameter_is_denied(self):
        task, lease = self.create_running_task()
        with self.assertRaises(CoreError):
            self.core.prepare_action(
                {
                    "task_id": task["task_id"],
                    "run_id": lease["run_id"],
                    "capability": "provider_call",
                    "target": "test",
                    "provider": "test-provider",
                    "canonical_parameters": {"nested": {"api_key": "not-allowed"}},
                    "approval_id": APPROVAL_ID,
                    "approval_sha256": "8" * 64,
                    "operation_idempotency_key": "fixture:operation:secret",
                },
                fencing_token=lease["task_envelope"]["lease_fencing_token"],
                actor="service:test-runner",
                idempotency_key="fixture:action:secret",
            )

    def test_unknown_action_escalates_and_never_redispatches(self):
        task, lease = self.create_running_task()
        action = self.prepare_action(task, lease)
        action = self.core.begin_action_dispatch(
            action["action_id"],
            expected_version=1,
            actor="service:dispatcher",
            idempotency_key="fixture:action:dispatch",
        )
        self.assertEqual(action["state"], "dispatched")
        action = self.core.reconcile_action(
            action["action_id"],
            "unknown",
            expected_version=2,
            actor="service:reconciler",
            idempotency_key="fixture:action:unknown",
        )
        self.assertEqual(action["state"], "unknown")
        self.assertEqual(
            self.core.task(task["task_id"])["state"], "needs_reconciliation"
        )
        with self.assertRaises(CoreError):
            self.core.begin_action_dispatch(
                action["action_id"],
                expected_version=3,
                actor="service:dispatcher",
                idempotency_key="fixture:action:blind-retry",
            )

    def test_operation_idempotency_key_cannot_create_two_actions(self):
        task, lease = self.create_running_task()
        first = self.prepare_action(task, lease)
        replay = self.prepare_action(task, lease)
        self.assertEqual(first, replay)
        with self.assertRaises(CoreError):
            self.core.prepare_action(
                {
                    "task_id": task["task_id"],
                    "run_id": lease["run_id"],
                    "capability": "git_push_branch",
                    "target": "repository:P-U-C/city2",
                    "provider": "git-host-reference",
                    "canonical_parameters": {"branch": "different"},
                    "approval_id": APPROVAL_ID,
                    "approval_sha256": "8" * 64,
                    "operation_idempotency_key": "fixture:operation:0001",
                },
                fencing_token=lease["task_envelope"]["lease_fencing_token"],
                actor="service:test-runner",
                idempotency_key="fixture:action:different-command",
            )
        self.assertEqual(
            self.store.conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0], 1
        )

    def test_confirmed_action_then_result_never_repeats_side_effect(self):
        for provider in ("native-idempotency-provider", "non-idempotent-provider"):
            with self.subTest(provider=provider):
                if self.store.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]:
                    self.store.close()
                    shutil.rmtree(self.temp)
                    self.setUp()
                task, lease = self.create_running_task()
                action = self.core.prepare_action(
                    {
                        "task_id": task["task_id"],
                        "run_id": lease["run_id"],
                        "capability": "test_side_effect",
                        "target": "fixture-target",
                        "provider": provider,
                        "canonical_parameters": {"value": 1},
                        "approval_id": APPROVAL_ID,
                        "approval_sha256": "8" * 64,
                        "operation_idempotency_key": "fixture:operation:provider",
                    },
                    fencing_token=lease["task_envelope"]["lease_fencing_token"],
                    actor="service:test-runner",
                    idempotency_key="fixture:action:provider-prepare",
                )
                action = self.core.begin_action_dispatch(
                    action["action_id"],
                    expected_version=1,
                    actor="service:dispatcher",
                    idempotency_key="fixture:action:provider-dispatch",
                )
                remote_calls = (
                    1  # durable remote success; local confirmation has not happened yet
                )
                with self.assertRaises(CoreError):
                    self.core.begin_action_dispatch(
                        action["action_id"],
                        expected_version=2,
                        actor="service:dispatcher",
                        idempotency_key="fixture:action:provider-blind-retry",
                    )
                action = self.core.reconcile_action(
                    action["action_id"],
                    "confirmed",
                    expected_version=2,
                    actor="service:reconciler",
                    idempotency_key="fixture:action:provider-confirm",
                    provider_operation_id="remote-op-1",
                    provider_evidence={"artifact_id": ARTIFACT_ID, "sha256": "c" * 64},
                )
                self.assertEqual(remote_calls, 1)
                result = result_for(
                    task, lease["run_id"], lease["task_envelope"]["lease_fencing_token"]
                )
                completed = self.core.submit_result(
                    result,
                    actor="service:test-runner",
                    idempotency_key="fixture:result:provider",
                )
                self.assertEqual(completed["task"]["state"], "review")
                self.assertEqual(
                    self.core.action(action["action_id"])["state"], "confirmed"
                )
                self.assertEqual(remote_calls, 1)

    def test_expired_lease_retries_then_hits_attempt_ceiling(self):
        objective = self.create_objective()
        task = self.core.create_task(
            task_fields(objective["objective_id"]),
            actor=ACTOR,
            idempotency_key="fixture:expiry:create",
        )
        task = self.core.set_task_ready(
            task["task_id"],
            expected_version=1,
            actor=ACTOR,
            idempotency_key="fixture:expiry:ready",
        )
        self.core.lease_task(
            task["task_id"],
            expected_version=2,
            owner="service:test-runner",
            expires_at=future(),
            resolved_agent_id=AGENT_ID,
            resolved_manifest_version=1,
            resolved_manifest_sha256="a" * 64,
            actor="service:city2-core",
            idempotency_key="fixture:expiry:lease-one",
        )
        task = self.core.expire_lease(
            task["task_id"],
            expected_version=3,
            replay_safe=True,
            now=future(2),
            actor="service:city2-core",
            idempotency_key="fixture:expiry:expire-one",
        )
        self.assertEqual(task["state"], "ready")
        second = self.core.lease_task(
            task["task_id"],
            expected_version=4,
            owner="service:test-runner",
            expires_at=future(),
            resolved_agent_id=AGENT_ID,
            resolved_manifest_version=1,
            resolved_manifest_sha256="a" * 64,
            actor="service:city2-core",
            idempotency_key="fixture:expiry:lease-two",
        )
        final = self.core.expire_lease(
            task["task_id"],
            expected_version=5,
            replay_safe=True,
            now=future(2),
            actor="service:city2-core",
            idempotency_key="fixture:expiry:expire-two",
        )
        self.assertEqual(second["task"]["attempt_count"], 2)
        self.assertEqual(final["state"], "failed_terminal")

    def test_confirmation_requires_evidence_and_is_deduplicated(self):
        task, lease = self.create_running_task()
        action = self.prepare_action(task, lease)
        action = self.core.begin_action_dispatch(
            action["action_id"],
            expected_version=1,
            actor="service:dispatcher",
            idempotency_key="fixture:action:dispatch-confirm",
        )
        with self.assertRaises(CoreError):
            self.core.reconcile_action(
                action["action_id"],
                "confirmed",
                expected_version=2,
                actor="service:reconciler",
                idempotency_key="fixture:action:bad-confirm",
            )
        kwargs = dict(
            expected_version=2,
            actor="service:reconciler",
            idempotency_key="fixture:action:confirm",
            provider_operation_id="remote-123",
            provider_evidence={"artifact_id": ARTIFACT_ID, "sha256": "c" * 64},
        )
        first = self.core.reconcile_action(action["action_id"], "confirmed", **kwargs)
        second = self.core.reconcile_action(action["action_id"], "confirmed", **kwargs)
        self.assertEqual(first, second)
        self.validate(first, "action.schema.json")
        count = self.store.conn.execute(
            "SELECT COUNT(*) FROM events WHERE aggregate_id = ?", (action["action_id"],)
        ).fetchone()[0]
        self.assertEqual(count, 3)

    def test_cancellation_fences_and_quarantines_late_result(self):
        task, lease = self.create_running_task()
        self.core.request_cancellation(
            task["task_id"],
            expected_version=4,
            actor=ACTOR,
            idempotency_key="fixture:task:cancel-request",
        )
        result = result_for(
            task, lease["run_id"], lease["task_envelope"]["lease_fencing_token"]
        )
        late = self.core.submit_result(
            result, actor="service:test-runner", idempotency_key="fixture:result:late"
        )
        self.assertEqual(late["result_status"], "completed_after_cancel")
        self.assertEqual(late["task"]["state"], "cancellation_requested")
        final = self.core.confirm_cancellation(
            task["task_id"],
            expected_version=6,
            actor=ACTOR,
            idempotency_key="fixture:task:cancel-confirm",
        )
        self.assertEqual(final["state"], "cancelled")
        status = self.store.conn.execute(
            "SELECT status FROM runs WHERE run_id = ?", (lease["run_id"],)
        ).fetchone()[0]
        self.assertEqual(status, "completed_after_cancel")

    def test_unsafe_synchronous_setting_refuses_write(self):
        self.store.conn.execute("PRAGMA synchronous=OFF")
        with self.assertRaises(IntegrityError):
            self.core.create_objective(
                objective_fields(), actor=ACTOR, idempotency_key="fixture:unsafe:write"
            )

    def test_projection_and_event_tampering_fail_closed(self):
        objective = self.create_objective()
        self.store.conn.execute(
            "UPDATE objectives SET last_event_sha256 = ? WHERE objective_id = ?",
            ("0" * 64, objective["objective_id"]),
        )
        with self.assertRaises(IntegrityError):
            self.store.verify_integrity()

    def test_task_projection_field_tampering_fails_closed(self):
        task, _ = self.create_running_task()
        for field, value in (("state", "ready"), ("attempt_count", 0)):
            with self.subTest(field=field):
                original = self.store.conn.execute(
                    f"SELECT {field} FROM tasks WHERE task_id = ?", (task["task_id"],)
                ).fetchone()[0]
                self.store.conn.execute(
                    f"UPDATE tasks SET {field} = ? WHERE task_id = ?",
                    (value, task["task_id"]),
                )
                with self.assertRaises(IntegrityError):
                    self.store.verify_integrity()
                self.store.conn.execute(
                    f"UPDATE tasks SET {field} = ? WHERE task_id = ?",
                    (original, task["task_id"]),
                )
        self.store.verify_integrity()

    def test_non_wal_database_refuses_startup(self):
        self.store.close()
        conn = sqlite3.connect(self.db)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.close()
        with self.assertRaises(IntegrityError):
            Store.open(self.db)
        self.store = sqlite3.connect(":memory:")  # tearDown-compatible close only

    def test_signed_backup_restore_and_tamper_detection(self):
        self.create_running_task()
        private_key = self.temp / "checkpoint.key"
        public_key = self.temp / "checkpoint.pub"
        generate_checkpoint_key(private_key, public_key)
        archive = self.temp / "archive"
        checkpoint = create_backup(
            self.store, archive, signing_key=private_key, key_version="test-v1"
        )
        verified, _ = verify_backup(archive, trusted_public_key=public_key)
        self.assertEqual(checkpoint, verified)
        restored = restore_backup(
            archive, self.temp / "empty-restore", trusted_public_key=public_key
        )
        with Store.open(restored["database"]) as store:
            self.assertEqual(
                store.verify_integrity()["terminal_hashes"],
                checkpoint["terminal_hashes"],
            )
        (archive / "events.jsonl").write_text("{}\n", encoding="utf-8")
        with self.assertRaises(IntegrityError):
            verify_backup(archive, trusted_public_key=public_key)

    def test_backup_fault_does_not_publish_partial_archive(self):
        private_key = self.temp / "checkpoint.key"
        public_key = self.temp / "checkpoint.pub"
        generate_checkpoint_key(private_key, public_key)
        self.store._fault_hook = lambda boundary: (
            (_ for _ in ()).throw(RuntimeError("injected"))
            if boundary == "after_sqlite_backup"
            else None
        )
        archive = self.temp / "partial-archive"
        with self.assertRaises(RuntimeError):
            create_backup(
                self.store, archive, signing_key=private_key, key_version="test-v1"
            )
        self.assertFalse(archive.exists())


class ProcessKillTests(unittest.TestCase):
    def test_kills_before_commit_roll_back_and_after_commit_deduplicates(self):
        for boundary in (
            "after_begin",
            "after_event_append",
            "after_projection_update",
            "before_dedup_record",
            "before_commit",
            "after_commit",
        ):
            with self.subTest(boundary=boundary):
                root = Path(tempfile.mkdtemp(prefix="city2-kill-test-"))
                db = root / "core.sqlite"
                with Store.initialize(db) as store:
                    objective = Core(store).create_objective(
                        objective_fields(),
                        actor=ACTOR,
                        idempotency_key="fixture:objective:create",
                    )
                process = multiprocessing.Process(
                    target=killed_objective_transition,
                    args=(str(db), boundary, objective["objective_id"]),
                )
                process.start()
                process.join(10)
                self.assertEqual(process.exitcode, 86)
                with Store.open(db) as store:
                    core = Core(store)
                    if boundary == "after_commit":
                        self.assertEqual(
                            core.objective(objective["objective_id"])["status"],
                            "active",
                        )
                        replay = core.set_objective_status(
                            objective["objective_id"],
                            "active",
                            expected_version=1,
                            actor=ACTOR,
                            idempotency_key="fixture:objective:activate",
                        )
                        self.assertEqual(replay["status"], "active")
                        self.assertEqual(store.meta("global_sequence"), "2")
                    else:
                        self.assertEqual(
                            core.objective(objective["objective_id"])["status"],
                            "proposed",
                        )
                        self.assertEqual(store.meta("global_sequence"), "1")
                shutil.rmtree(root)

    def test_operation_specific_kills_leave_atomic_pre_state(self):
        cases = (
            ("lease", "ready", "after_lease_acquisition", "ready", None),
            ("dispatch", "prepared", "after_dispatch_recorded", "running", "prepared"),
            (
                "acknowledge",
                "dispatched",
                "after_action_acknowledgement",
                "running",
                "dispatched",
            ),
            ("result", "running", "after_result_persistence", "running", None),
        )
        for operation, through, boundary, task_state, action_state in cases:
            with self.subTest(operation=operation):
                root = Path(tempfile.mkdtemp(prefix="city2-operation-kill-"))
                db = root / "core.sqlite"
                state = setup_process_fixture(db, through)
                process = multiprocessing.Process(
                    target=killed_core_operation,
                    args=(str(db), boundary, operation, state),
                )
                process.start()
                process.join(10)
                self.assertEqual(process.exitcode, 86)
                with Store.open(db) as store:
                    core = Core(store)
                    self.assertEqual(core.task(state["task_id"])["state"], task_state)
                    if action_state:
                        self.assertEqual(
                            core.action(state["action_id"])["state"], action_state
                        )
                    if operation == "lease":
                        self.assertEqual(
                            store.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[
                                0
                            ],
                            0,
                        )
                    if operation == "result":
                        result_count = store.conn.execute(
                            "SELECT COUNT(*) FROM runs WHERE result_json IS NOT NULL"
                        ).fetchone()[0]
                        self.assertEqual(result_count, 0)
                    store.verify_integrity()
                shutil.rmtree(root)

    def test_backup_process_kill_never_publishes_partial_destination(self):
        root = Path(tempfile.mkdtemp(prefix="city2-backup-kill-"))
        db = root / "core.sqlite"
        setup_process_fixture(db, "running")
        private_key = root / "checkpoint.key"
        public_key = root / "checkpoint.pub"
        generate_checkpoint_key(private_key, public_key)
        output = root / "archive"
        process = multiprocessing.Process(
            target=killed_backup, args=(str(db), str(output), str(private_key))
        )
        process.start()
        process.join(10)
        self.assertEqual(process.exitcode, 86)
        self.assertFalse(output.exists())
        with Store.open(db) as store:
            store.verify_integrity()
        shutil.rmtree(root)


class CanonicalJsonTests(unittest.TestCase):
    def test_jcs_safe_profile(self):
        self.assertEqual(canonical_json({"b": 2, "a": "é"}), '{"a":"é","b":2}')
        self.assertEqual(canonical_json(1e-6), "0.000001")
        self.assertEqual(canonical_json(1e-7), "1e-7")
        self.assertEqual(canonical_json(1e20), "100000000000000000000")
        self.assertEqual(canonical_json(1e21), "1e+21")
        self.assertEqual(canonical_json(-0.0), "0")
        self.assertEqual(
            canonical_json({"\U0001f600": 1, "\u20ac": 2}), '{"€":2,"😀":1}'
        )
        for invalid in (float("nan"), float("inf"), 9_007_199_254_740_992):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                canonical_json(invalid)


if __name__ == "__main__":
    unittest.main()
