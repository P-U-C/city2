from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PairingRelayConfigTest(unittest.TestCase):
    def test_compose_runs_dedicated_pairing_binary(self) -> None:
        compose = (ROOT / "infra/buzz/compose.yml").read_text()
        self.assertIn("  pairing-relay:\n", compose)
        self.assertIn('entrypoint: ["/usr/local/bin/buzz-pair-relay"]', compose)
        self.assertIn("BUZZ_PAIR_RELAY_BIND_ADDR: 0.0.0.0:5000", compose)
        self.assertIn("BUZZ_PAIRING_RELAY_URL:", compose)

    def test_pairing_port_is_privately_bound(self) -> None:
        private = (ROOT / "infra/buzz/compose.private.yml").read_text()
        self.assertIn("  pairing-proxy:\n", private)
        self.assertIn(
            '${BUZZ_BIND_IP:?set BUZZ_BIND_IP}:${BUZZ_PAIRING_PORT:-5000}:8080',
            private,
        )

    def test_pairing_relay_is_only_reachable_through_hardened_proxy(self) -> None:
        compose = (ROOT / "infra/buzz/compose.yml").read_text()
        proxy = (ROOT / "infra/buzz/pairing-proxy.conf").read_text()
        pairing = compose.split("  pairing-relay:\n", 1)[1].split(
            "  pairing-proxy:\n", 1
        )[0]
        self.assertNotIn("ports:", pairing)
        self.assertIn('user: "65532:65532"', pairing)
        self.assertIn("read_only: true", pairing)
        self.assertIn("cap_drop:\n      - ALL", pairing)
        self.assertIn("no-new-privileges:true", pairing)
        self.assertIn("read_only: true", compose)
        self.assertIn('user: "101:101"', compose)
        self.assertIn("/tmp:uid=101,gid=101,mode=1770", compose)
        self.assertIn("/var/cache/nginx:uid=101,gid=101,mode=0750", compose)
        self.assertIn("cap_drop:\n      - ALL", compose)
        self.assertIn("location = /pair", proxy)
        self.assertIn("$http_upgrade !~* ^websocket$", proxy)
        self.assertIn("location /", proxy)
        self.assertIn("client_header_timeout 5s", proxy)
        self.assertIn("limit_conn pairing_per_ip 4", proxy)

    def test_preflight_migration_exception_is_project_and_service_scoped(self) -> None:
        preflight = (ROOT / "infra/buzz/scripts/preflight.sh").read_text()
        self.assertIn('label=com.docker.compose.project=${PROJECT}', preflight)
        self.assertIn("label=com.docker.compose.service=pairing-proxy", preflight)
        self.assertIn("label=com.docker.compose.service=pairing-relay", preflight)

    def test_bootstrap_advertises_pair_path(self) -> None:
        bootstrap = (ROOT / "infra/buzz/scripts/bootstrap-env.sh").read_text()
        example = (ROOT / "infra/buzz/.env.example").read_text()
        self.assertIn("BUZZ_PAIRING_RELAY_URL=ws://${relay_host}:5000/pair", bootstrap)
        self.assertIn(
            "BUZZ_PAIRING_RELAY_URL=ws://CHANGE_ME_RELAY_HOST:5000/pair",
            example,
        )

    def test_disposable_e2e_reserves_a_distinct_pairing_port(self) -> None:
        e2e = (ROOT / "infra/buzz/scripts/e2e-disposable.sh").read_text()
        self.assertIn('pairing_port="${candidate_pairing}"', e2e)
        self.assertIn("BUZZ_PAIRING_PORT=${pairing_port}", e2e)
        self.assertIn(
            "BUZZ_PAIRING_RELAY_URL=ws://127.0.0.1:${pairing_port}/pair",
            e2e,
        )
        self.assertIn("stage=\"pairing-proxy\"", e2e)
        self.assertIn("'^HTTP/1\\.[01] 101 '", e2e)
        self.assertIn('"${pair_base}/other"', e2e)
        self.assertIn("tar --exclude='./.env'", e2e)


if __name__ == "__main__":
    unittest.main()
