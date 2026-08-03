import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from city2core import MemoryService, Store  # noqa: E402
from city2core.archive import generate_checkpoint_key  # noqa: E402
from city2core.model import digest_profile  # noqa: E402
from city2core.producer import (  # noqa: E402
    ProducerError,
    ProducerObserver,
    verify_producer_observation,
    write_observation,
)
from city2core.store import IntegrityError  # noqa: E402


class ProducerObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="city2-producer-test-"))
        self.source = self.temp / "authoritative-output.json"
        self.source.write_text('{"status":"healthy"}\n', encoding="utf-8")
        modified = datetime(2026, 8, 3, tzinfo=timezone.utc).timestamp()
        os.utime(self.source, (modified, modified))
        self.contract = json.loads(
            (ROOT / "config" / "producer-contract.example.json").read_text()
        )
        self.agent = json.loads(
            (ROOT / "config" / "producer-agent.example.json").read_text()
        )
        uri = self.source.resolve().as_uri()
        self.contract.update(
            {
                "contract_id": "m6-synthetic",
                "producer_id": "synthetic-sector",
                "host_id": "synthetic-host",
                "unix_user": "synthetic-sector",
            }
        )
        self.contract["source"]["uri"] = uri
        self.agent["filesystem_scopes"] = ["read:" + uri]
        self._refresh_agent_digest()
        self.key = self.temp / "observer.key"
        self.public = self.temp / "observer.pub"
        generate_checkpoint_key(self.key, self.public)

    def tearDown(self):
        shutil.rmtree(self.temp)

    def enable(self):
        self.contract["enabled"] = True
        self.agent["enabled"] = True
        self._refresh_agent_digest()

    def _refresh_agent_digest(self):
        self.agent["manifest_sha256"] = digest_profile(
            self.agent, {"manifest_sha256", "aggregate_version"}
        )

    def test_checked_in_examples_are_disabled_and_self_digesting(self):
        contract = json.loads(
            (ROOT / "config" / "producer-contract.example.json").read_text()
        )
        agent = json.loads(
            (ROOT / "config" / "producer-agent.example.json").read_text()
        )
        self.assertFalse(contract["enabled"])
        self.assertFalse(agent["enabled"])
        self.assertEqual(
            agent["manifest_sha256"],
            digest_profile(agent, {"manifest_sha256", "aggregate_version"}),
        )
        ProducerObserver(contract, agent)

    def test_selected_ai_infra_candidate_is_disabled_and_exact_scoped(self):
        contract = json.loads(
            (ROOT / "config" / "producer-pilot.ai-infra.json").read_text()
        )
        agent = json.loads(
            (ROOT / "config" / "producer-agent.ai-infra.json").read_text()
        )
        self.assertEqual(contract["producer_id"], "ai-infra")
        self.assertEqual(contract["host_id"], "worker-1")
        self.assertEqual(
            contract["source"]["uri"],
            "file:///home/ai-infra/ai-infra-corpus/out/ai-infrastructure-aggregates.json",
        )
        self.assertFalse(contract["enabled"])
        self.assertFalse(agent["enabled"])
        self.assertEqual(
            agent["manifest_sha256"],
            digest_profile(agent, {"manifest_sha256", "aggregate_version"}),
        )
        ProducerObserver(contract, agent)

    def test_signed_observation_memory_and_removal_leave_source_unchanged(self):
        before = self.source.read_bytes()
        observer = ProducerObserver(self.contract, self.agent)
        with self.assertRaises(ProducerError):
            observer.observe(
                self.source,
                observed_at="2026-08-03T00:01:00Z",
                signing_key=self.key,
                signer_key_version="synthetic-1",
            )
        self.enable()
        observer = ProducerObserver(self.contract, self.agent)
        observation = observer.observe(
            self.source,
            observed_at="2026-08-03T00:01:00Z",
            signing_key=self.key,
            signer_key_version="synthetic-1",
        )
        verify_producer_observation(
            observation, self.contract, trusted_public_key=self.public
        )
        self.assertEqual(observation["freshness_state"], "current")
        self.assertEqual(observation["freshness_seconds"], 60)
        self.assertEqual(
            observation["source_sha256"], hashlib.sha256(before).hexdigest()
        )
        self.assertFalse(any(observation["authority_touch"].values()))
        self.assertFalse(observation["value"]["source_content_copied"])

        with Store.initialize(self.temp / "core.sqlite") as store:
            candidate = MemoryService(store).create_candidate(
                observer.memory_candidate(observation, trusted_public_key=self.public),
                actor="agent:m6-producer-observer",
                idempotency_key="producer:synthetic:memory:0001",
            )
            self.assertEqual(candidate["scope"], "project:city2")
            self.assertEqual(candidate["review_state"], "candidate")
            forged = dict(observation)
            forged["source_sha256"] = "0" * 64
            with self.assertRaises(IntegrityError):
                observer.memory_candidate(forged, trusted_public_key=self.public)

        evidence = self.temp / "observer-state" / "observation.json"
        write_observation(evidence, observation)
        self.assertTrue(evidence.is_file())
        with self.assertRaises(ProducerError):
            write_observation(self.source, observation)
        evidence.unlink()
        self.assertEqual(self.source.read_bytes(), before)

    def test_database_boundary_mutation_and_manifest_escalation_fail_closed(self):
        self.enable()
        database = self.temp / "producer.sqlite"
        database.write_bytes(b"not-a-real-database")
        contract = copy.deepcopy(self.contract)
        agent = copy.deepcopy(self.agent)
        contract["source"]["uri"] = database.resolve().as_uri()
        agent["filesystem_scopes"] = ["read:" + contract["source"]["uri"]]
        agent["manifest_sha256"] = digest_profile(
            agent, {"manifest_sha256", "aggregate_version"}
        )
        with self.assertRaises(ProducerError):
            ProducerObserver(contract, agent).observe(
                database,
                observed_at="2026-08-03T00:01:00Z",
                signing_key=self.key,
                signer_key_version="synthetic-1",
            )

        def mutate_source():
            self.source.write_bytes(self.source.read_bytes() + b"changed")

        with self.assertRaises(IntegrityError):
            ProducerObserver(
                self.contract, self.agent, after_read=mutate_source
            ).observe(
                self.source,
                observed_at="2026-08-03T00:01:00Z",
                signing_key=self.key,
                signer_key_version="synthetic-1",
            )

        escalated = copy.deepcopy(self.agent)
        escalated["tools"].append("write-output")
        escalated["manifest_sha256"] = digest_profile(
            escalated, {"manifest_sha256", "aggregate_version"}
        )
        with self.assertRaises(ProducerError):
            ProducerObserver(self.contract, escalated)


if __name__ == "__main__":
    unittest.main()
