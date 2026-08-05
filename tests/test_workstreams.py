import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstream_status.py"
CONFIG = ROOT / "config/workstreams.json"


class WorkstreamTests(unittest.TestCase):
    def run_status(self, *args):
        return subprocess.run(
            [str(SCRIPT), *args], cwd=ROOT, capture_output=True, text=True
        )

    def test_manifest_lists_current_and_proposed_workstreams(self):
        result = self.run_status()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("executive", result.stdout)
        self.assertIn("city2-build", result.stdout)
        self.assertIn("post-fiat", result.stdout)
        self.assertIn("city2-ops", result.stdout)
        self.assertIn("#ops", result.stdout)
        self.assertIn("one isolated coordinator session per channel", result.stdout)

    def test_plan_is_actionable_and_staged(self):
        result = self.run_status("--plan", "trading")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Create a private Buzz forum channel", result.stdout)
        self.assertIn("one top-level thread per open task", result.stdout)
        self.assertIn("dedicated agent", result.stdout)

    def test_active_plan_reuses_existing_channel(self):
        result = self.run_status("--plan", "city2-ops")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Active channel", result.stdout)
        self.assertIn("existing isolated coordinator session", result.stdout)
        self.assertNotIn("Create a private Buzz forum channel", result.stdout)

    def test_active_workstreams_name_only_the_deployed_coordinator(self):
        data = json.loads(CONFIG.read_text())
        active = [item for item in data["workstreams"] if item["state"] == "active"]
        self.assertTrue(active)
        self.assertTrue(all(item["agent"] == "City2 Coordinator" for item in active))
        self.assertTrue(all(item["agent_mode"] == "coordinator-session" for item in active))

    def test_parked_plan_does_not_print_activation_steps(self):
        data = json.loads(CONFIG.read_text())
        data["workstreams"][1]["state"] = "parked"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as handle:
            json.dump(data, handle)
            handle.flush()
            result = self.run_status(
                "--config", handle.name, "--plan", data["workstreams"][1]["id"]
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Parked", result.stdout)
        self.assertNotIn("Create a private Buzz forum channel", result.stdout)

    def test_duplicate_channel_fails_closed(self):
        data = json.loads(CONFIG.read_text())
        data["workstreams"][1]["channel"] = data["workstreams"][0]["channel"]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as handle:
            json.dump(data, handle)
            handle.flush()
            result = self.run_status("--config", handle.name)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unique", result.stderr)


if __name__ == "__main__":
    unittest.main()
