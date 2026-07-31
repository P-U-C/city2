from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "fleet_status.py"
SPEC = importlib.util.spec_from_file_location("fleet_status", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def manifest() -> dict:
    return {
        "schema_version": 1,
        "hosts": [
            {
                "id": "worker-1",
                "role": "producer",
                "access": {"type": "ssh", "alias": "worker"},
                "minimum_free_gib": 5,
            }
        ],
        "producers": [
            {
                "id": "sector",
                "kind": "sector",
                "state": "active",
                "host": "worker-1",
                "unix_user": "sector",
                "runtime_root": "/home/sector/sector-corpus",
                "database": "/home/sector/sector-corpus/db.sqlite",
                "freshness_hours": 30,
                "cron": {"type": "system", "path": "/etc/cron.d/sector-corpus"},
                "aggregate_log": "/home/sector/logs/sector-aggregates.log",
            }
        ],
    }


def snapshot(*, database_age_hours: float = 1, free_gib: float = 6) -> dict:
    now = datetime(2026, 7, 31, 20, tzinfo=timezone.utc)
    return {
        "checked_at": now.isoformat(),
        "hosts": {
            "worker-1": {
                "disk_free_bytes": int(free_gib * 1024**3),
                "producers": [
                    {
                        "id": "sector",
                        "unix_user_exists": True,
                        "runtime_root_exists": True,
                        "cron_ok": True,
                        "database": {
                            "exists": True,
                            "bytes": 1024,
                            "mtime": now.timestamp() - database_age_hours * 3600,
                        },
                        "aggregate_log": {"exists": True, "bytes": 100, "mtime": now.timestamp()},
                    }
                ],
            }
        },
    }


class FleetStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 31, 20, tzinfo=timezone.utc)

    def test_manifest_is_valid(self) -> None:
        MODULE.validate_manifest(manifest())

    def test_duplicate_producer_is_rejected(self) -> None:
        value = manifest()
        value["producers"].append(dict(value["producers"][0]))
        with self.assertRaisesRegex(MODULE.ManifestError, "duplicate producer"):
            MODULE.validate_manifest(value)

    def test_healthy_snapshot(self) -> None:
        report = MODULE.evaluate(manifest(), snapshot(), now=self.now)
        self.assertEqual(report["overall"], "ok")
        self.assertEqual(report["producers"][0]["status"], "ok")

    def test_stale_database_is_critical(self) -> None:
        report = MODULE.evaluate(manifest(), snapshot(database_age_hours=31), now=self.now)
        self.assertEqual(report["overall"], "critical")
        self.assertIn("stale", report["producers"][0]["detail"])

    def test_low_disk_is_warning(self) -> None:
        report = MODULE.evaluate(manifest(), snapshot(free_gib=2), now=self.now)
        self.assertEqual(report["overall"], "warn")


if __name__ == "__main__":
    unittest.main()
