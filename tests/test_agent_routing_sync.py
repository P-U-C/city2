import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "infra/buzz/scripts/sync-agent-routing.sh"


class AgentRoutingSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env_file = self.root / "agent.env"
        self.env_file.write_text(
            "\n".join(
                [
                    "BUZZ_RELAY_URL=ws://relay.invalid",
                    "BUZZ_PRIVATE_KEY=" + "22" * 32,
                    "BUZZ_ACP_AGENT_OWNER=" + "11" * 32,
                    'BUZZ_ACP_DISPLAY_NAME="City2 Coordinator"',
                    "",
                ]
            )
        )
        self.env_file.chmod(0o600)
        self.buzz = self.root / "buzz"
        self.output = self.root / "buzz-acp.toml"

    def tearDown(self):
        self.tmp.cleanup()

    def write_buzz(self, channels):
        payload = json.dumps(channels)
        self.buzz.write_text(f"#!/bin/sh\nprintf '%s\\n' '{payload}'\n")
        self.buzz.chmod(0o755)

    def run_sync(self, *names):
        env = os.environ.copy()
        env["CITY2_BUZZ_BIN"] = str(self.buzz)
        return subprocess.run(
            [str(SCRIPT), str(self.env_file), str(self.output), *names],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_resolves_names_and_atomically_replaces_routing(self):
        channels = [
            {"name": "control", "channel_id": "11111111-1111-4111-8111-111111111111"},
            {"name": "ops", "channel_id": "22222222-2222-4222-8222-222222222222"},
            {"name": "city2", "channel_id": "33333333-3333-4333-8333-333333333333"},
            {"name": "unrelated", "channel_id": "44444444-4444-4444-8444-444444444444"},
        ]
        self.write_buzz(channels)
        self.output.write_text("stale\n")

        result = self.run_sync("control", "city2", "ops")

        self.assertEqual(result.returncode, 0, result.stderr)
        content = self.output.read_text()
        for channel in channels[:3]:
            self.assertIn(channel["channel_id"], content)
            self.assertNotIn(channel["channel_id"], result.stdout + result.stderr)
        self.assertNotIn(channels[3]["channel_id"], content)
        self.assertIn('str_starts_with(content, "@City2 Coordinator")', content)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o644)

    def test_missing_name_fails_without_replacing_existing_routing(self):
        self.write_buzz(
            [{"name": "control", "channel_id": "11111111-1111-4111-8111-111111111111"}]
        )
        self.output.write_text("known-good\n")

        result = self.run_sync("control", "ops")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_text(), "known-good\n")

    def test_duplicate_name_fails_without_replacing_existing_routing(self):
        self.write_buzz(
            [
                {"name": "ops", "channel_id": "11111111-1111-4111-8111-111111111111"},
                {"name": "ops", "channel_id": "22222222-2222-4222-8222-222222222222"},
            ]
        )
        self.output.write_text("known-good\n")

        result = self.run_sync("ops")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_text(), "known-good\n")


if __name__ == "__main__":
    unittest.main()
