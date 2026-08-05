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

    def test_systemd_is_the_sandbox_and_runtime_stays_direct_tool_only(self):
        launcher = LAUNCHER.read_text()
        self.assertIn('export INITIAL_AGENT_MODE=agent-full-access', launcher)
        self.assertIn('export BUZZ_ACP_MODEL="${BUZZ_ACP_MODEL:-gpt-5.5}"', launcher)
        self.assertIn('sandbox_mode = "danger-full-access"', launcher)
        self.assertIn('apps = false', launcher)
        self.assertIn('code_mode = false', launcher)
        self.assertIn('multi_agent = false', launcher)
        self.assertIn('plugins = false', launcher)

        env_example = (ROOT / "infra/buzz/agents/env/agent.env.example").read_text()
        self.assertIn("BUZZ_ACP_AUTO_PUBLISH_FINAL=true", env_example)
        self.assertIn("BUZZ_ACP_MCP_COMMAND=\n", env_example)
        prompt = (ROOT / "infra/buzz/agents/prompts/coordinator.md").read_text()
        self.assertIn("harness signs and publishes that final answer", prompt)

        build_script = (ROOT / "scripts/build-buzz-tools.sh").read_text()
        self.assertIn("0001-auto-publish-final-answer.patch", build_script)
        buzz_patch = (
            ROOT / "infra/buzz/patches/0001-auto-publish-final-answer.patch"
        ).read_text()
        self.assertIn('Some("final_answer")', buzz_patch)
        self.assertIn("post_final_answer", buzz_patch)

        unit = UNIT.read_text()
        for boundary in (
            "ProtectHome=yes",
            "ProtectSystem=strict",
            "NoNewPrivileges=true",
            "MemoryDenyWriteExecute=true",
            "BindReadOnlyPaths=/home/%i/city2:/srv/city2",
        ):
            self.assertIn(boundary, unit)


if __name__ == "__main__":
    unittest.main()
