from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ObserverBundleTests(unittest.TestCase):
    def test_bundle_is_reproducible_complete_and_credential_free(self):
        with tempfile.TemporaryDirectory(prefix="city2-bundle-test-") as raw:
            output = Path(raw)
            env = os.environ.copy()
            env["CITY2_OBSERVER_BUNDLE_DIR"] = str(output)
            command = [str(ROOT / "scripts" / "build-producer-observer-bundle.sh")]
            first = subprocess.run(
                command, cwd=ROOT, env=env, check=True, capture_output=True
            )
            archive = output / "city2-producer-observer-ai-infra.tar.gz"
            first_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
            second = subprocess.run(
                command, cwd=ROOT, env=env, check=True, capture_output=True
            )
            self.assertEqual(
                first_hash, hashlib.sha256(archive.read_bytes()).hexdigest()
            )
            self.assertIn(b"bundle=", first.stdout)
            self.assertIn(b"bundle=", second.stdout)

            with tarfile.open(archive, "r:gz") as bundle:
                names = set(bundle.getnames())
                required = {
                    "ai-infra/MANIFEST.sha256",
                    "ai-infra/REMOVAL.md",
                    "ai-infra/etc/city2/producer/ai-infra.contract.json",
                    "ai-infra/etc/city2/producer/ai-infra.agent.json",
                    "ai-infra/etc/systemd/system/city2-producer-observer-ai-infra.service",
                    "ai-infra/opt/city2/lib/city2/scripts/observe_producer.py",
                    "ai-infra/opt/city2/lib/city2/src/city2core/producer.py",
                    "ai-infra/opt/city2/lib/city2/schemas/v1/producer-contract.schema.json",
                }
                self.assertTrue(required.issubset(names))
                prohibited = (".key", ".env", ".sqlite", "auth.json")
                self.assertFalse(any(name.endswith(prohibited) for name in names))

                manifest = bundle.extractfile("ai-infra/MANIFEST.sha256")
                assert manifest
                for line in io.TextIOWrapper(manifest, encoding="utf-8"):
                    expected, relative = line.rstrip().split("  ", 1)
                    member = bundle.extractfile(
                        "ai-infra/" + relative.removeprefix("./")
                    )
                    assert member
                    self.assertEqual(
                        hashlib.sha256(member.read()).hexdigest(), expected
                    )
                for name in (
                    "ai-infra/etc/city2/producer/ai-infra.contract.json",
                    "ai-infra/etc/city2/producer/ai-infra.agent.json",
                ):
                    member = bundle.extractfile(name)
                    assert member
                    self.assertFalse(json.load(member)["enabled"])


if __name__ == "__main__":
    unittest.main()
