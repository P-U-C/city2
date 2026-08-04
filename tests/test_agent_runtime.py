from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "infra/buzz/agents/bin/city2-agent-launcher"
UNIT = ROOT / "infra/buzz/agents/systemd/city2-buzz-agent@.service"


class AgentRuntimeTests(unittest.TestCase):
    def test_oauth_rotation_uses_one_shared_file(self):
        unit = UNIT.read_text()
        self.assertIn(
            "BindPaths=/home/%i/.codex/auth.json:"
            "/run/city2-agent-%i/auth.json",
            unit,
        )
        self.assertNotIn("LoadCredential=codex.auth:", unit)
        self.assertIn("ProtectHome=yes", unit)
        self.assertIn("Environment=CODEX_HOME=/run/city2-agent-%i/codex", unit)
        self.assertIn(
            "Environment=CITY2_SHARED_AUTH_FILE=/run/city2-agent-%i/auth.json",
            unit,
        )

    def test_launcher_does_not_clone_rotating_oauth_credential(self):
        launcher = LAUNCHER.read_text()
        self.assertIn('credential="${CITY2_SHARED_AUTH_FILE}"', launcher)
        self.assertNotIn('install -m 0600 "${credential}"', launcher)
        self.assertIn('ln -s "${credential}" "${CODEX_HOME}/auth.json"', launcher)


if __name__ == "__main__":
    unittest.main()
