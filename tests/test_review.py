from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from city2core import Core, ReviewService, Store  # noqa: E402
from city2core.core import CoreError  # noqa: E402
from city2core.model import digest_profile  # noqa: E402
from test_core import result_for  # noqa: E402
from test_memory import ACTOR, objective_fields, task_fields, timestamp  # noqa: E402


MAKER_ID = "agt_01980000-0000-7000-8000-000000000001"
REVIEWER_ID = "agt_01980000-0000-7000-8000-000000000002"
WRAPPER = (ROOT / "city2").read_text(encoding="utf-8")


def manifest(agent_id, name, tools, policy):
    value = {
        "schema_version": "city2.agent/v1",
        "agent_id": agent_id,
        "aggregate_version": 1,
        "manifest_version": 1,
        "manifest_sha256": "",
        "name": name,
        "role": name,
        "department": "engineering",
        "runner_policy": "pfterminal-v1",
        "required_capabilities": ["structured_output"],
        "model_policy": policy,
        "authority_class": "A1",
        "allowed_task_types": ["verification"],
        "tools": tools,
        "filesystem_scopes": ["repository:city2"],
        "network_policy": "deny",
        "credential_handles": ["credential:maker"] if name == "maker" else [],
        "memory_read_scopes": ["project:city2"],
        "memory_write_scopes": ["candidate:project:city2"],
        "context_profile": "default-v1",
        "time_budget_seconds": 300,
        "cost_budget": {
            "max_billable_usd": "1.00",
            "max_input_tokens": 1000,
            "max_output_tokens": 1000,
        },
        "concurrency": 1,
        "review_policy": "independent" if name == "reviewer" else "none",
        "enabled": True,
    }
    value["manifest_sha256"] = digest_profile(
        value, {"manifest_sha256", "aggregate_version"}
    )
    return value


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="city2-review-test-"))
        self.store = Store.initialize(self.temp / "core.sqlite")
        self.core = Core(self.store)
        self.review = ReviewService(self.store)
        self.maker = manifest(MAKER_ID, "maker", ["git_write"], "maker-model")
        self.reviewer = manifest(
            REVIEWER_ID, "reviewer", ["read_review"], "reviewer-model"
        )
        self.review.register_manifest(self.maker, idempotency_key="manifest:maker")
        self.review.register_manifest(
            self.reviewer, idempotency_key="manifest:reviewer"
        )

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp)

    def completed_task(self):
        objective = self.core.create_objective(
            objective_fields(), actor=ACTOR, idempotency_key="review:objective:create"
        )
        objective = self.core.set_objective_status(
            objective["objective_id"],
            "active",
            expected_version=1,
            actor=ACTOR,
            idempotency_key="review:objective:active",
        )
        task = self.core.create_task(
            task_fields(objective["objective_id"]),
            actor=ACTOR,
            idempotency_key="review:task:create",
        )
        task = self.core.set_task_ready(
            task["task_id"],
            expected_version=1,
            actor=ACTOR,
            idempotency_key="review:task:ready",
        )
        lease = self.core.lease_task(
            task["task_id"],
            expected_version=2,
            owner="service:runner",
            expires_at=timestamp(hours=1),
            resolved_agent_id=MAKER_ID,
            resolved_manifest_version=1,
            resolved_manifest_sha256=self.maker["manifest_sha256"],
            actor="service:city2-core",
            idempotency_key="review:task:lease",
        )
        task = self.core.start_run(
            task["task_id"],
            lease["run_id"],
            lease["task_envelope"]["lease_fencing_token"],
            expected_version=3,
            actor="agent:maker",
            idempotency_key="review:task:start",
        )
        result = result_for(
            task, lease["run_id"], lease["task_envelope"]["lease_fencing_token"]
        )
        result["checks"] = [
            {
                "schema_version": "city2.evidence/v1",
                "criterion_id": "ac_context",
                "subject_sha256": "d" * 64,
                "result": "pass",
                "validator": {"id": "deterministic", "version": "1"},
                "checked_at": timestamp(),
                "provenance": [],
            }
        ]
        return self.core.submit_result(
            result, actor="agent:maker", idempotency_key="review:task:result"
        )["task"]

    def test_maker_cannot_accept_and_independent_reviewer_can(self):
        task = self.completed_task()
        with self.assertRaises(CoreError):
            self.review.review_task(
                task["task_id"],
                MAKER_ID,
                "accepted",
                expected_version=5,
                findings=[],
                finding_dispositions={},
                idempotency_key="review:self",
            )
        accepted = self.review.review_task(
            task["task_id"],
            REVIEWER_ID,
            "accepted",
            expected_version=5,
            findings=[],
            finding_dispositions={},
            idempotency_key="review:independent",
        )
        self.assertEqual(accepted["task"]["state"], "accepted")
        row = self.store.conn.execute("SELECT * FROM task_reviews").fetchone()
        self.assertNotEqual(row["maker_agent_id"], row["reviewer_agent_id"])
        self.store.verify_integrity()

    def test_missing_evidence_and_tool_overlap_block_acceptance(self):
        task = self.completed_task()
        self.store.conn.execute(
            "UPDATE runs SET result_json = json_set(result_json, '$.checks', json('[]'))"
        )
        with self.assertRaises(CoreError):
            self.review.review_task(
                task["task_id"],
                REVIEWER_ID,
                "accepted",
                expected_version=5,
                findings=[],
                finding_dispositions={},
                idempotency_key="review:no-evidence",
            )


class ReviewWrapperBoundaryTests(unittest.TestCase):
    def test_review_is_fail_closed_inside_root_created_boundary(self):
        review_case = WRAPPER.split("  review)", 1)[1].split("  core)", 1)[0]
        self.assertIn("sudo -n systemd-run", review_case)
        self.assertIn("--uid=\"$(id -u)\"", review_case)
        self.assertIn("--property=NoNewPrivileges=yes", review_case)
        self.assertIn("--property=CapabilityBoundingSet=", review_case)
        self.assertIn("--property=ProtectHome=tmpfs", review_case)
        self.assertIn("--property=ProtectSystem=strict", review_case)
        self.assertIn("--property=PrivateTmp=yes", review_case)
        self.assertIn("--property=SystemCallFilter=~@mount", review_case)
        self.assertIn('BindReadOnlyPaths=${ROOT}', review_case)
        self.assertIn('BindReadOnlyPaths=${PFTERMINAL_INSTALL}', review_case)
        self.assertIn('BindPaths=${REVIEW_STATE}', review_case)
        self.assertIn(
            'BindPaths=${CODEX_AUTH}:${REVIEW_STATE}/auth.json', review_case
        )
        self.assertIn('CODEX_HOME="${REVIEW_STATE}"', review_case)
        self.assertIn("city2-review-state.XXXXXX", review_case)
        self.assertNotIn('BindPaths=${PFTERMINAL_STATE}', review_case)
        self.assertNotIn("exec pfterminal review", review_case)

    def test_review_rejects_unscoped_custom_prompt(self):
        review_case = WRAPPER.split("  review)", 1)[1].split("  core)", 1)[0]
        rejection = "custom review prompts are unsupported"
        self.assertIn('[[ "$#" -eq 0 ]]', review_case)
        self.assertIn(rejection, review_case)


if __name__ == "__main__":
    unittest.main()
