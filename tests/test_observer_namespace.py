from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from city2core.archive import generate_checkpoint_key  # noqa: E402
from city2core.model import digest_profile  # noqa: E402
from city2core.producer import verify_producer_observation  # noqa: E402


UNIT = (
    ROOT
    / "infra"
    / "producer"
    / "ai-infra"
    / "city2-producer-observer-ai-infra.service"
)


class ObserverNamespaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="city2-observer-unit-test-"))

    def tearDown(self):
        shutil.rmtree(self.temp)

    def test_unit_exposes_only_exact_source_and_persistent_evidence(self):
        text = UNIT.read_text(encoding="utf-8")
        source = "/home/ai-infra/ai-infra-corpus/out/ai-infrastructure-aggregates.json"
        runtime = "/run/city2-producer-observer-ai-infra/source.json"
        state = "/var/lib/city2-producer-observer-ai-infra"
        required = (
            "Type=oneshot",
            "User=ai-infra",
            "NoNewPrivileges=true",
            "PrivateNetwork=true",
            "ProtectSystem=strict",
            "ProtectHome=tmpfs",
            "CapabilityBoundingSet=",
            "RestrictAddressFamilies=AF_UNIX",
            f"BindReadOnlyPaths={source}:{runtime}",
            "ReadOnlyPaths=/run/city2-producer-observer-ai-infra",
            f"ReadWritePaths={state}",
            "LoadCredential=observer.signing-key:",
            f"--source {runtime}",
            f"--output {state}/observation.json",
        )
        for value in required:
            self.assertIn(value, text)
        self.assertNotIn("db.sqlite", text)
        self.assertNotIn("EnvironmentFile=", text)
        self.assertNotIn("[Install]", text)

    def test_cli_emits_signed_observation_for_runtime_bind_path(self):
        source = self.temp / "source.json"
        source.write_text('{"status":"healthy"}\n', encoding="utf-8")
        contract = json.loads(
            (ROOT / "config" / "producer-contract.example.json").read_text()
        )
        agent = json.loads(
            (ROOT / "config" / "producer-agent.example.json").read_text()
        )
        contract.update(
            {
                "contract_id": "namespace-synthetic",
                "producer_id": "synthetic-sector",
                "host_id": "synthetic-host",
                "unix_user": "synthetic-sector",
                "enabled": True,
            }
        )
        contract["source"]["uri"] = "file:///authoritative/output.json"
        contract["source"]["runtime_uri"] = source.resolve().as_uri()
        agent["enabled"] = True
        agent["filesystem_scopes"] = ["read:" + source.resolve().as_uri()]
        agent["manifest_sha256"] = digest_profile(
            agent, {"manifest_sha256", "aggregate_version"}
        )
        contract_path = self.temp / "contract.json"
        agent_path = self.temp / "agent.json"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        agent_path.write_text(json.dumps(agent), encoding="utf-8")

        credentials = self.temp / "credentials"
        credentials.mkdir()
        key = credentials / "observer.signing-key"
        public = self.temp / "observer.pub"
        generate_checkpoint_key(key, public)
        output = self.temp / "observation.json"
        environment = os.environ.copy()
        environment["CREDENTIALS_DIRECTORY"] = str(credentials)
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "observe_producer.py"),
                "--contract",
                str(contract_path),
                "--agent",
                str(agent_path),
                "--source",
                str(source),
                "--output",
                str(output),
                "--signer-key-version",
                "synthetic-1",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split()[0:2], ["producer-observer:", "PASS"])
        observation = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(observation["source_uri"], contract["source"]["uri"])
        verify_producer_observation(observation, contract, trusted_public_key=public)

        missing_credential = environment.copy()
        missing_credential.pop("CREDENTIALS_DIRECTORY")
        failed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "observe_producer.py"),
                "--contract",
                str(contract_path),
                "--agent",
                str(agent_path),
                "--source",
                str(source),
                "--output",
                str(self.temp / "should-not-exist.json"),
                "--signer-key-version",
                "synthetic-1",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=missing_credential,
        )
        self.assertEqual(failed.returncode, 1)
        self.assertIn("signing credential is unavailable", failed.stderr)
        self.assertNotIn("Traceback", failed.stderr)


if __name__ == "__main__":
    unittest.main()
