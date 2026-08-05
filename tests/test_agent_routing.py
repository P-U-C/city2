import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "infra/buzz/scripts/create-agent-routing.sh"


class AgentRoutingTests(unittest.TestCase):
    def test_generates_scoped_owner_text_mention_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "buzz-acp.toml"
            owner = "11" * 32
            channels = [
                "11111111-1111-4111-8111-111111111111",
                "22222222-2222-4222-8222-222222222222",
            ]
            subprocess.run(
                [str(SCRIPT), str(output), owner, "City2 Coordinator", *channels],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            content = output.read_text()
            self.assertIn('name = "owner-text-mention"', content)
            self.assertIn(f'author == "{owner}"', content)
            self.assertIn('str_starts_with(content, "@City2 Coordinator")', content)
            for channel in channels:
                self.assertIn(channel, content)
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o644)

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "buzz-acp.toml"
            output.write_text("existing\n")
            result = subprocess.run(
                [
                    str(SCRIPT),
                    str(output),
                    "11" * 32,
                    "City2 Coordinator",
                    "11111111-1111-4111-8111-111111111111",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_text(), "existing\n")

    def test_does_not_chmod_existing_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "existing"
            parent.mkdir(mode=0o700)
            output = parent / "buzz-acp.toml"
            subprocess.run(
                [
                    str(SCRIPT),
                    str(output),
                    "11" * 32,
                    "City2 Coordinator",
                    "11111111-1111-4111-8111-111111111111",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(os.stat(parent).st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()
