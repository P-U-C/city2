import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from city2core import Core, MemoryService, Store  # noqa: E402
from city2core.core import CoreError  # noqa: E402
from city2core.model import sha256_bytes, utc_now  # noqa: E402
from city2core.store import IntegrityError  # noqa: E402


ACTOR = "human:chad"
AGENT = "agt_01980000-0000-7000-8000-000000000001"


def timestamp(days=0, hours=0):
    return (
        (datetime.now(timezone.utc) + timedelta(days=days, hours=hours))
        .isoformat()
        .replace("+00:00", "Z")
    )


def evidence(*, digest="a" * 64, validity="current", relationship="observed_from"):
    return {
        "relationship": relationship,
        "source_type": "git_blob",
        "authoritative_owner": "P-U-C/city2",
        "uri": "git+https://github.com/P-U-C/city2.git",
        "retrieval_method": "git_show",
        "content_sha256": digest,
        "observed_at": timestamp(),
        "validity_status": validity,
        "revocation_checked_at": timestamp(),
        "git_commit_sha1": "0123456789abcdef0123456789abcdef01234567",
        "path": "docs/COMPANY-OS-SPEC.md",
    }


def memory_fields(
    statement="City2 sessions are disposable and Core owns durable state.",
    *,
    scope="project:city2",
    memory_type="decision",
    sensitivity="internal",
    fact_class="architecture_decision",
    labels=None,
    sources=None,
    supersedes=None,
):
    return {
        "scope": scope,
        "type": memory_type,
        "statement": statement,
        "evidence_refs": sources if sources is not None else [evidence()],
        "asserted_by": ACTOR,
        "owner": ACTOR,
        "valid_from": timestamp(),
        "fact_class": fact_class,
        "revalidation_policy": "on_source_revision",
        "revalidate_at": timestamp(days=1),
        "confidence": 1.0,
        "sensitivity": sensitivity,
        "labels": labels or ["architecture", "portability"],
        "supersedes": supersedes or [],
    }


def objective_fields():
    return {
        "title": "Memory proof",
        "intent": "Prove fresh-session context reconstruction.",
        "accountable_owner": ACTOR,
        "review_at": timestamp(days=7),
        "measurable_outcomes": [
            {"outcome_id": "oc_memory", "measure": "context", "target": "reconstructed"}
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
        "title": "Reconstruct context",
        "intent": "Use only Core state after a fresh session.",
        "requested_role": "reviewer",
        "authority_class": "A1",
        "inputs": [],
        "constraints": ["fresh_session"],
        "acceptance_criteria": [
            {
                "criterion_id": "ac_context",
                "requirement": "Context is deterministic.",
                "mandatory": True,
            }
        ],
        "memory_scopes": ["company", "project:city2"],
        "time_budget_seconds": 300,
        "max_attempts": 2,
        "task_dedupe_key": "fixture:memory:task-0001",
    }


class MemoryFixture(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="city2-memory-test-"))
        self.db = self.temp / "core.sqlite"
        self.store = Store.initialize(self.db)
        self.memory = MemoryService(self.store)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp)

    def create_candidate(
        self, fields=None, key="memory:candidate:0001", actor="agent:maker"
    ):
        return self.memory.create_candidate(
            fields or memory_fields(), actor=actor, idempotency_key=key
        )

    def accept(self, record, key="memory:review:0001", reviewer="agent:reviewer"):
        checks = [
            {
                "uri": source["uri"],
                "content_sha256": source["content_sha256"],
                "validity_status": source["validity_status"],
            }
            for source in record["evidence_refs"]
        ]
        return self.memory.review_candidate(
            record["memory_id"],
            "accepted",
            expected_version=record["aggregate_version"],
            reviewer=reviewer,
            source_checks=checks,
            independence={"separate_session": True, "separate_identity": True},
            idempotency_key=key,
        )["memory"]

    def test_candidate_review_accept_and_self_review_denial(self):
        candidate = self.create_candidate()
        with self.assertRaises(CoreError):
            self.accept(candidate, reviewer="agent:maker")
        accepted = self.accept(candidate)
        self.assertEqual(accepted["review_state"], "accepted")
        result = self.memory.retrieve(
            "durable sessions", allowed_scopes=["project:city2"], clearance="internal"
        )
        self.assertEqual(
            [item["memory_id"] for item in result.records], [accepted["memory_id"]]
        )
        self.store.verify_integrity()

    def test_company_acceptance_and_secret_content_fail_closed(self):
        company = self.create_candidate(memory_fields(scope="company"))
        with self.assertRaises(CoreError):
            self.accept(company)
        accepted = self.accept(company, key="memory:company:accept", reviewer=ACTOR)
        self.assertEqual(accepted["scope"], "company")
        fields = memory_fields(statement="api_key=must-not-enter-memory")
        with self.assertRaises(CoreError):
            self.create_candidate(fields, key="memory:secret:deny")
        metadata_secret = memory_fields()
        metadata_secret["evidence_refs"][0]["excerpt_locator"] = {
            "password": "must-not-enter-memory"
        }
        with self.assertRaises(CoreError):
            self.create_candidate(metadata_secret, key="memory:metadata-secret:deny")

    def test_supersession_and_conflicting_facts(self):
        old = self.accept(self.create_candidate())
        replacement = self.create_candidate(
            memory_fields(
                statement="Core state replaces model session continuity.",
                supersedes=[old["memory_id"]],
            ),
            key="memory:replacement:create",
        )
        replacement = self.accept(replacement, key="memory:replacement:accept")
        self.assertEqual(
            self.memory.get(old["memory_id"])["review_state"], "superseded"
        )
        result = self.memory.retrieve(
            "Core state", allowed_scopes=["project:city2"], clearance="internal"
        )
        self.assertEqual(
            [item["memory_id"] for item in result.records], [replacement["memory_id"]]
        )

        first_fact = self.accept(
            self.create_candidate(
                memory_fields(
                    "The service is healthy.",
                    memory_type="fact",
                    fact_class="service_status",
                    labels=["service", "status"],
                ),
                key="memory:fact:first",
            ),
            key="memory:fact:first-review",
        )
        second = self.create_candidate(
            memory_fields(
                "The service is unhealthy.",
                memory_type="fact",
                fact_class="service_status",
                labels=["service", "status"],
                sources=[evidence(digest="b" * 64)],
            ),
            key="memory:fact:second",
        )
        reviewed = self.accept(second, key="memory:fact:second-review")
        self.assertEqual(reviewed["review_state"], "quarantined")
        self.assertEqual(
            self.memory.get(first_fact["memory_id"])["review_state"], "accepted"
        )

    def test_scope_sensitivity_and_poisoned_source_isolation(self):
        project = self.accept(self.create_candidate())
        company = self.accept(
            self.create_candidate(
                memory_fields(
                    scope="company", statement="Company policy is deny by default."
                ),
                key="memory:scope:company",
                actor=ACTOR,
            ),
            key="memory:scope:company-review",
            reviewer=ACTOR,
        )
        confidential = self.accept(
            self.create_candidate(
                memory_fields(
                    scope="project:city2",
                    statement="Confidential architecture detail.",
                    sensitivity="confidential",
                ),
                key="memory:scope:confidential",
            ),
            key="memory:scope:confidential-review",
        )
        result = self.memory.retrieve(
            "policy architecture",
            allowed_scopes=["project:city2"],
            clearance="internal",
        )
        visible = {item["memory_id"] for item in result.records}
        self.assertIn(project["memory_id"], visible)
        self.assertNotIn(company["memory_id"], result.candidate_memory_ids)
        self.assertNotIn(
            company["memory_id"], {item["memory_id"] for item in result.excluded}
        )
        self.assertIn(
            {"memory_id": confidential["memory_id"], "reason": "sensitivity_denied"},
            result.excluded,
        )
        poisoned = self.create_candidate(
            memory_fields(sources=[evidence(validity="revoked")]), key="memory:poisoned"
        )
        with self.assertRaises(CoreError):
            self.accept(poisoned, key="memory:poisoned-review")

    def test_stale_source_revalidation_and_critical_slo(self):
        accepted = self.accept(self.create_candidate())
        changed = self.memory.mark_source_changed(
            accepted["evidence_refs"][0]["uri"], "f" * 64, observed_at=timestamp()
        )
        self.assertEqual(changed, [accepted["memory_id"]])
        self.assertEqual(
            self.memory.get(accepted["memory_id"])["review_state"], "stale"
        )
        refreshed_sources = copy.deepcopy(accepted["evidence_refs"])
        refreshed_sources[0]["revocation_checked_at"] = timestamp(hours=1)
        revalidated = self.memory.revalidate(
            accepted["memory_id"],
            refreshed_sources,
            timestamp(days=1),
            expected_version=3,
            actor="agent:reviewer",
            idempotency_key="memory:revalidate",
        )
        self.assertEqual(revalidated["review_state"], "accepted")
        critical = memory_fields(fact_class="service_health", memory_type="fact")
        critical["revalidate_at"] = timestamp(days=2)
        with self.assertRaises(CoreError):
            self.create_candidate(critical, key="memory:critical:slo")

    def test_fts_rebuild_is_stable_and_tamper_fails_closed(self):
        self.accept(self.create_candidate())
        before = self.memory.retrieve(
            "sessions durable", allowed_scopes=["project:city2"], clearance="internal"
        )
        self.assertEqual(self.memory.rebuild_index(), 1)
        after = self.memory.retrieve(
            "sessions durable", allowed_scopes=["project:city2"], clearance="internal"
        )
        self.assertEqual(before.ranked_candidates, after.ranked_candidates)
        self.store.conn.execute("DELETE FROM memory_fts")
        with self.assertRaises(IntegrityError):
            self.store.verify_integrity()

    def test_fresh_session_context_is_bounded_and_reproducible(self):
        accepted = self.accept(
            self.create_candidate(
                memory_fields(
                    statement="Core reconstructs durable context without conversation reuse."
                    * 4
                )
            )
        )
        core = Core(self.store)
        objective = core.create_objective(
            objective_fields(), actor=ACTOR, idempotency_key="context:objective:create"
        )
        objective = core.set_objective_status(
            objective["objective_id"],
            "active",
            expected_version=1,
            actor=ACTOR,
            idempotency_key="context:objective:active",
        )
        task = core.create_task(
            task_fields(objective["objective_id"]),
            actor=ACTOR,
            idempotency_key="context:task:create",
        )
        task = core.set_task_ready(
            task["task_id"],
            expected_version=1,
            actor=ACTOR,
            idempotency_key="context:task:ready",
        )
        core.lease_task(
            task["task_id"],
            expected_version=2,
            owner="service:test-runner",
            expires_at=timestamp(hours=1),
            resolved_agent_id=AGENT,
            resolved_manifest_version=1,
            resolved_manifest_sha256="a" * 64,
            actor="service:city2-core",
            idempotency_key="context:task:lease",
        )
        self.store.close()
        self.store = Store.open(self.db)
        self.memory = MemoryService(self.store)
        first = self.memory.assemble_context(
            task["task_id"],
            "durable context",
            allowed_scopes=["project:city2"],
            clearance="internal",
            section_budgets={"project_decisions": 8},
            actor="service:context-builder",
            idempotency_key="context:assemble:0001",
        )
        replay = self.memory.assemble_context(
            task["task_id"],
            "durable context",
            allowed_scopes=["project:city2"],
            clearance="internal",
            section_budgets={"project_decisions": 8},
            actor="service:context-builder",
            idempotency_key="context:assemble:0001",
        )
        self.assertEqual(first, replay)
        self.assertEqual(
            first["manifest"]["selected"][0]["memory_id"], accepted["memory_id"]
        )
        self.assertLessEqual(first["manifest"]["total_tokens"], 8)
        self.assertTrue(first["manifest"]["sections"][0]["truncated"])
        with self.assertRaises(CoreError):
            self.memory.assemble_context(
                task["task_id"],
                "durable",
                allowed_scopes=["department:secret"],
                clearance="restricted",
                section_budgets={"knowledge": 8},
                actor="service:context-builder",
                idempotency_key="context:scope:deny",
            )
        self.store.verify_integrity()

    def test_export_import_is_candidate_only_and_idempotent(self):
        accepted = self.accept(self.create_candidate())
        exported = self.memory.export_memories()["export"]
        destination = self.temp / "destination.sqlite"
        with Store.initialize(destination) as other:
            imported = MemoryService(other)
            first = imported.import_export(
                exported, actor="service:memory-import", import_key="fixture-export"
            )
            second = imported.import_export(
                exported, actor="service:memory-import", import_key="fixture-export-two"
            )
            self.assertEqual(
                first["imported_memory_ids"], second["imported_memory_ids"]
            )
            record = imported.get(first["imported_memory_ids"][0])
            self.assertEqual(record["review_state"], "candidate")
            self.assertNotEqual(record["memory_id"], accepted["memory_id"])
            corrupt = copy.deepcopy(exported)
            corrupt["memory_events"][0]["payload"]["scope"] = "company"
            with self.assertRaises(IntegrityError):
                imported.import_export(
                    corrupt, actor="service:memory-import", import_key="corrupt"
                )

    def test_forward_migration_from_m1_is_verified(self):
        old_db = self.temp / "m1.sqlite"
        conn = sqlite3.connect(old_db, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        migration_path = ROOT / "src" / "city2core" / "migrations" / "0001_core.sql"
        migration = migration_path.read_text(encoding="utf-8")
        conn.executescript("BEGIN IMMEDIATE;\n" + migration)
        now = utc_now()
        conn.execute(
            "INSERT INTO schema_migrations(version, sha256, applied_at) VALUES (1, ?, ?)",
            (sha256_bytes(migration.encode("utf-8")), now),
        )
        conn.executemany(
            "INSERT INTO core_meta(key, value) VALUES (?, ?)",
            sorted(
                {
                    "application_version": "0.3.0",
                    "database_id": str(uuid.uuid4()),
                    "global_sequence": "0",
                    "schema_version": "1",
                    "writer_id": "city2-core-v1",
                }.items()
            ),
        )
        conn.execute(
            "INSERT INTO writer_state(writer_id, writer_sequence) VALUES ('city2-core-v1', 0)"
        )
        conn.commit()
        conn.close()
        with Store.migrate(old_db) as migrated:
            self.assertEqual(migrated.meta("schema_version"), "4")
            self.assertEqual(migrated.meta("application_version"), "0.8.3")
            self.assertEqual(migrated.verify_integrity()["event_high_water"], 0)


if __name__ == "__main__":
    unittest.main()
