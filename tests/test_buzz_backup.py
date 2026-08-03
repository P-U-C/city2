from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = ROOT / "infra/buzz/scripts/backup.sh"


class BuzzBackupSafetyTest(unittest.TestCase):
    def run_absent_bind_case(
        self, *, file_bind_ip: str, environment_bind_ip: str | None = None
    ) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            buzz = tmp / "buzz"
            scripts = buzz / "scripts"
            bin_dir = tmp / "bin"
            destination = tmp / "backups"
            scripts.mkdir(parents=True)
            bin_dir.mkdir()

            shutil.copy2(BACKUP_SCRIPT, scripts / "backup.sh")
            (buzz / ".env").write_text(f"BUZZ_BIND_IP={file_bind_ip}\n")
            os.chmod(buzz / ".env", 0o600)

            docker_marker = tmp / "docker-called"
            (bin_dir / "ip").write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' '1: lo    inet 127.0.0.1/8 scope host lo'\n"
            )
            (bin_dir / "docker").write_text(
                "#!/usr/bin/env bash\n"
                f"touch {docker_marker!s}\n"
                "exit 99\n"
            )
            os.chmod(bin_dir / "ip", 0o755)
            os.chmod(bin_dir / "docker", 0o755)

            env = os.environ.copy()
            env.pop("BUZZ_BIND_IP", None)
            if environment_bind_ip is not None:
                env["BUZZ_BIND_IP"] = environment_bind_ip
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            result = subprocess.run(
                [str(scripts / "backup.sh"), str(destination)],
                cwd=tmp,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "BUZZ_BIND_IP is not assigned; refusing to stop the relay",
                result.stderr,
            )
            self.assertFalse(docker_marker.exists())
            self.assertFalse(destination.exists())

    def test_absent_file_bind_ip_fails_before_mutation(self) -> None:
        self.run_absent_bind_case(file_bind_ip="198.51.100.9")

    def test_exported_bind_ip_takes_compose_precedence(self) -> None:
        self.run_absent_bind_case(
            file_bind_ip="127.0.0.1", environment_bind_ip="198.51.100.9"
        )


if __name__ == "__main__":
    unittest.main()
