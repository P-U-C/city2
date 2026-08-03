from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "runtime_status.py"
SPEC = importlib.util.spec_from_file_location("runtime_status", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


class RuntimeStatusTests(unittest.TestCase):
    def test_tailscale_reports_connection_state_not_binary_presence(self):
        for backend, expected in (
            ("Running", "connected"),
            ("NeedsLogin", "logged-out"),
            ("Stopped", "stopped"),
        ):
            with self.subTest(backend=backend):
                state = MODULE.tailscale_state(
                    run=lambda *args, **kwargs: completed(
                        '{"BackendState":"' + backend + '"}'
                    ),
                    which=lambda command: "/usr/bin/tailscale",
                )
                self.assertEqual(state, expected)
        self.assertEqual(MODULE.tailscale_state(which=lambda command: None), "missing")

    def test_tailscale_malformed_status_fails_honestly(self):
        state = MODULE.tailscale_state(
            run=lambda *args, **kwargs: completed("not-json", returncode=1),
            which=lambda command: "/usr/bin/tailscale",
        )
        self.assertEqual(state, "unavailable")

    def test_coordinator_uses_system_unit_state(self):
        state = MODULE.coordinator_state(
            "city2-buzz-agent@ubuntu.service",
            run=lambda *args, **kwargs: completed(
                "LoadState=loaded\nActiveState=active\nSubState=running\n"
            ),
            which=lambda command: "/usr/bin/systemctl",
        )
        self.assertEqual(state, "active")
        absent = MODULE.coordinator_state(
            "city2-buzz-agent@ubuntu.service",
            run=lambda *args, **kwargs: completed(
                "LoadState=not-found\nActiveState=inactive\nSubState=dead\n"
            ),
            which=lambda command: "/usr/bin/systemctl",
        )
        self.assertEqual(absent, "not-installed")


if __name__ == "__main__":
    unittest.main()
