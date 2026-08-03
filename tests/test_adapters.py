from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from city2core import (  # noqa: E402
    BuzzAdapter,
    Core,
    MemoryService,
    PfTerminalRunnerAdapter,
    Store,
)
from city2core.adapters import (  # noqa: E402
    FixtureRunner,
    substitution_equivalent,
)
from city2core.core import CoreError  # noqa: E402
from test_memory import (  # noqa: E402
    ACTOR,
    AGENT,
    memory_fields,
    objective_fields,
    task_fields,
    timestamp,
)


OWNER_KEY = "1" * 64


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="city2-adapter-test-"))
        self.db = self.temp / "core.sqlite"
        self.store = Store.initialize(self.db)
        self.core = Core(self.store)
        objective = self.core.create_objective(
            objective_fields(), actor=ACTOR, idempotency_key="adapter:objective:create"
        )
        self.objective = self.core.set_objective_status(
            objective["objective_id"],
            "active",
            expected_version=1,
            actor=ACTOR,
            idempotency_key="adapter:objective:active",
        )

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp)

    def message(
        self, message_id="buzz-event-0001", author=OWNER_KEY, channel="control"
    ):
        return {
            "message_id": message_id,
            "author_public_key": author,
            "channel_id": channel,
            "thread_id": "thread-1",
            "created_at": timestamp(),
        }

    def a0_task_fields(self):
        fields = task_fields(self.objective["objective_id"])
        fields["authority_class"] = "A0"
        return fields

    def accept_memory(self):
        memory = MemoryService(self.store)
        candidate = memory.create_candidate(
            memory_fields(),
            actor="agent:maker",
            idempotency_key="adapter:memory:create",
        )
        source = candidate["evidence_refs"][0]
        return memory.review_candidate(
            candidate["memory_id"],
            "accepted",
            expected_version=1,
            reviewer="agent:reviewer",
            source_checks=[
                {
                    "uri": source["uri"],
                    "content_sha256": source["content_sha256"],
                    "validity_status": "current",
                }
            ],
            independence={"separate_identity": True, "separate_session": True},
            idempotency_key="adapter:memory:accept",
        )["memory"]

    def test_owner_only_a0_ingress_survives_buzz_restart(self):
        adapter = BuzzAdapter(
            self.store,
            owner_public_key=OWNER_KEY,
            allowed_channels={"control", "city2"},
        )
        message = self.message()
        created = adapter.ingest_task(message, self.a0_task_fields())
        self.assertFalse(created["deduplicated"])
        task_id = created["task"]["task_id"]
        with self.assertRaises(CoreError):
            adapter.ingest_task(
                self.message("outsider", author="2" * 64), self.a0_task_fields()
            )
        elevated = self.a0_task_fields()
        elevated["authority_class"] = "A1"
        with self.assertRaises(CoreError):
            adapter.ingest_task(self.message("elevated"), elevated)

        self.store.close()
        self.store = Store.open(self.db)
        restarted = BuzzAdapter(
            self.store,
            owner_public_key=OWNER_KEY,
            allowed_channels={"control", "city2"},
        )
        replay = restarted.ingest_task(message, self.a0_task_fields())
        self.assertTrue(replay["deduplicated"])
        self.assertEqual(replay["task"]["task_id"], task_id)
        self.assertEqual(restarted.render_task(task_id)["state"], "proposed")
        self.assertEqual(restarted.ceo_projection()["authority_class"], "A0")
        self.store.verify_integrity()

    def test_capability_negotiation_fails_closed_on_degradation(self):
        runner = PfTerminalRunnerAdapter(self.store, runner_version="0.1.20")
        manifest = runner.capabilities()
        allowed = runner.negotiate(
            manifest,
            {
                "structured_output": {"enforced"},
                "artifact_hashing": {"sha256"},
                "sandboxing": {"host_policy"},
            },
        )
        self.assertEqual(allowed["decision"], "allow")
        with self.assertRaises(CoreError):
            runner.negotiate(manifest, {"usage_accounting": {"estimated"}})
        mutated = dict(manifest)
        mutated["capabilities"] = dict(manifest["capabilities"])
        mutated["capabilities"]["structured_output"] = "unsupported"
        mutated["manifest_sha256"] = "0" * 64
        with self.assertRaises(CoreError):
            runner.negotiate(mutated, {"structured_output": {"enforced"}})
        stale_hash = dict(manifest)
        stale_hash["runner_version"] = "mutated"
        with self.assertRaises(CoreError):
            runner.negotiate(stale_hash, {})

    def test_fresh_request_dispatch_and_provider_substitution(self):
        accepted = self.accept_memory()
        fields = self.a0_task_fields()
        task = self.core.create_task(
            fields, actor=ACTOR, idempotency_key="adapter:task:create"
        )
        task = self.core.set_task_ready(
            task["task_id"],
            expected_version=1,
            actor=ACTOR,
            idempotency_key="adapter:task:ready",
        )
        lease = self.core.lease_task(
            task["task_id"],
            expected_version=2,
            owner="service:pfterminal-runner",
            expires_at=timestamp(hours=1),
            resolved_agent_id=AGENT,
            resolved_manifest_version=1,
            resolved_manifest_sha256="a" * 64,
            actor="service:city2-core",
            idempotency_key="adapter:task:lease",
        )
        context = MemoryService(self.store).assemble_context(
            task["task_id"],
            "durable state",
            allowed_scopes=["project:city2"],
            clearance="internal",
            section_budgets={"project_decisions": 40},
            actor="service:context-builder",
            idempotency_key="adapter:context",
        )
        runner = PfTerminalRunnerAdapter(self.store, runner_version="0.1.20")
        request = runner.render_fresh_request(lease["task_envelope"], context)
        self.assertTrue(request["fresh_session"])
        self.assertEqual(request["conversation_history"], [])
        self.assertEqual(
            request["context_content"]["memory"][0]["memory_id"], accepted["memory_id"]
        )
        dispatch = runner.prepare_dispatch(
            lease["run_id"],
            lease["task_envelope"],
            context["manifest"],
            runner.capabilities(),
            idempotency_key="adapter:dispatch",
        )
        self.assertEqual(dispatch["state"], "prepared")
        left = FixtureRunner("provider-a").run(request)
        right = FixtureRunner("provider-b").run(request)
        self.assertTrue(substitution_equivalent(left, right))
        schema = "\n".join(
            row[0]
            for row in self.store.conn.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
            )
        )
        self.assertNotIn("conversation_history", schema)
        self.assertNotIn("provider_session", schema)
        self.store.verify_integrity()


if __name__ == "__main__":
    unittest.main()
