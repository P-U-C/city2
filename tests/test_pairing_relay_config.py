from pathlib import Path
import os
import shutil
import subprocess
import tempfile
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

    def test_mobile_tls_ingress_is_loopback_only_and_hardened(self) -> None:
        compose = (ROOT / "infra/buzz/compose.yml").read_text()
        private = (ROOT / "infra/buzz/compose.private.yml").read_text()
        ingress = (ROOT / "infra/buzz/tls-ingress.conf").read_text()
        service = compose.split("  tls-ingress:\n", 1)[1].split(
            "  postgres:\n", 1
        )[0]

        self.assertIn(
            '127.0.0.1:${BUZZ_TLS_BACKEND_PORT:-13000}:8080', private
        )
        self.assertIn('user: "101:101"', service)
        self.assertIn("read_only: true", service)
        self.assertIn("cap_drop:\n      - ALL", service)
        self.assertIn("no-new-privileges:true", service)
        self.assertIn("location = /pair", ingress)
        self.assertIn("proxy_pass http://pairing-relay:5000", ingress)
        self.assertIn("location /", ingress)
        self.assertIn("proxy_pass http://relay:3000", ingress)
        self.assertIn("client_max_body_size 500m", ingress)
        self.assertIn("proxy_request_buffering off", ingress)

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
        self.assertIn('pairing_url="wss://${relay_host}:${tls_port}/pair"', bootstrap)
        self.assertIn(
            "BUZZ_PAIRING_RELAY_URL=wss://CHANGE_ME_DEVICE_NAME.CHANGE_ME_TAILNET.ts.net:8443/pair",
            example,
        )

    def test_private_tls_configuration_preserves_secret_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="city2-private-tls-test-") as raw:
            root = Path(raw)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy2(
                ROOT / "infra/buzz/scripts/configure-private-tls.sh",
                scripts / "configure-private-tls.sh",
            )
            migration_log = root / "migration.log"
            migration = scripts / "migrate-community-host.sh"
            migration.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$#\" > {migration_log}\n"
            )
            migration.chmod(0o755)
            serve_log = root / "serve.log"
            serve = scripts / "tailscale-serve.sh"
            serve.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$1\" > {serve_log}\n"
            )
            serve.chmod(0o755)
            env_file = root / ".env"
            env_file.write_text(
                "BUZZ_BIND_IP=127.0.0.1\n"
                "BUZZ_HTTP_PORT=3000\n"
                "BUZZ_PAIRING_PORT=5000\n"
                "BUZZ_DOMAIN=127.0.0.1\n"
                "RELAY_URL=ws://127.0.0.1:3000\n"
                "BUZZ_PAIRING_RELAY_URL=ws://127.0.0.1:5000/pair\n"
                "BUZZ_MEDIA_BASE_URL=http://127.0.0.1:3000/media\n"
                "BUZZ_MEDIA_SERVER_DOMAIN=127.0.0.1\n"
                "BUZZ_CORS_ORIGINS=http://127.0.0.1:3000\n"
                "POSTGRES_PASSWORD=must-remain-private\n"
            )
            env_file.chmod(0o600)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            tailscale = bin_dir / "tailscale"
            tailscale.write_text(
                "#!/bin/sh\n"
                "cat <<'EOF'\n"
                '{"BackendState":"Running","Self":{"DNSName":"node.tailnet.ts.net."},'
                '"CertDomains":["node.tailnet.ts.net"]}\n'
                "EOF\n"
            )
            tailscale.chmod(0o755)
            process_env = os.environ.copy()
            process_env["PATH"] = f"{bin_dir}:{process_env['PATH']}"
            result = subprocess.run(
                [str(scripts / "configure-private-tls.sh")],
                env=process_env,
                text=True,
                capture_output=True,
                check=True,
            )

            configured = env_file.read_text()
            self.assertIn("POSTGRES_PASSWORD=must-remain-private", configured)
            self.assertIn("RELAY_URL=wss://node.tailnet.ts.net:8443", configured)
            self.assertIn(
                "BUZZ_PAIRING_RELAY_URL=wss://node.tailnet.ts.net:8443/pair",
                configured,
            )
            self.assertNotIn("must-remain-private", result.stdout + result.stderr)
            self.assertNotIn("node.tailnet.ts.net", result.stdout + result.stderr)
            self.assertEqual(migration_log.read_text().strip(), "2")
            self.assertEqual(serve_log.read_text().strip(), "preflight")

            configure = (scripts / "configure-private-tls.sh").read_text()
            self.assertLess(
                configure.index('tailscale-serve.sh" preflight'),
                configure.index('migrate-community-host.sh"'),
            )

    def test_host_migration_is_transactional_and_fail_closed(self) -> None:
        migration = (
            ROOT / "infra/buzz/scripts/migrate-community-host.sh"
        ).read_text()
        self.assertIn("LOCK TABLE communities IN ACCESS EXCLUSIVE MODE", migration)
        self.assertIn("scripts/backup.sh", migration)
        self.assertIn("CITY2_BACKUP_ALLOW_MISSING_TLS_INGRESS=true", migration)
        self.assertIn("compose stop relay", migration)
        self.assertIn("target community already exists", migration)
        self.assertIn("target community contains non-bootstrap state", migration)
        self.assertIn("kind <> 13534", migration)
        self.assertIn("target_audit.action <> 'event_created'", migration)
        self.assertIn("target_audit.object_id = encode(target_event.id, 'hex')", migration)
        self.assertIn("DELETE FROM audit_log", migration)
        self.assertIn("DELETE FROM events", migration)
        self.assertIn("DELETE FROM relay_members", migration)
        self.assertIn("DELETE FROM communities WHERE id = target_id", migration)
        self.assertIn("SET host = current_setting('city2.new_host')", migration)
        self.assertIn("relay intentionally remains stopped", migration)
        self.assertIn("SET LOCAL city2.old_host = :'old_host'", migration)
        self.assertNotIn("SELECT set_config", migration)
        self.assertIn("port in {80, 443}", migration)
        self.assertLess(
            migration.index("restart_old=true"),
            migration.index("compose stop relay"),
        )
        self.assertLess(
            migration.index('tailscale-serve.sh" remove'),
            migration.index("compose stop tls-ingress"),
        )
        self.assertIn('tailscale-serve.sh" apply', migration)

        backup = (ROOT / "infra/buzz/scripts/backup.sh").read_text()
        self.assertIn("CITY2_BACKUP_ALLOW_MISSING_TLS_INGRESS", backup)
        self.assertIn('restart_frontends=(pairing-relay pairing-proxy relay)', backup)
        self.assertIn('restart_frontends+=(tls-ingress)', backup)

    def test_host_migration_normalizes_default_websocket_ports(self) -> None:
        with tempfile.TemporaryDirectory(prefix="city2-host-normalization-") as raw:
            root = Path(raw)
            scripts = root / "scripts"
            scripts.mkdir()
            migration = scripts / "migrate-community-host.sh"
            shutil.copy2(
                ROOT / "infra/buzz/scripts/migrate-community-host.sh",
                migration,
            )
            (root / ".env").write_text("placeholder=true\n")

            for implicit, explicit in (
                ("wss://EXAMPLE.COM", "wss://example.com:443/"),
                ("ws://EXAMPLE.COM", "ws://example.com:80/"),
                ("wss://EXAMPLE.COM", "wss://example.com:80/"),
                ("ws://EXAMPLE.COM", "ws://example.com:443/"),
            ):
                result = subprocess.run(
                    [str(migration), implicit, explicit],
                    text=True,
                    capture_output=True,
                    check=True,
                )
                self.assertIn("already current", result.stdout)

    def test_tailscale_serve_management_is_scoped_and_fail_closed(self) -> None:
        script = (ROOT / "infra/buzz/scripts/tailscale-serve.sh").read_text()
        self.assertIn('keys == ["/"]', script)
        self.assertIn(".AllowFunnel[$authority] // false", script)
        self.assertIn("refusing to replace it", script)
        self.assertIn("sudo -n tailscale serve", script)
        self.assertIn("backend_is_available", script)
        self.assertIn('label=com.docker.compose.service=tls-ingress', script)
        self.assertIn("preflight)", script)
        self.assertIn('"${tls_port}" != "80"', script)
        self.assertIn('"${tls_port}" != "443"', script)
        self.assertIn("private TLS route already absent", script)
        self.assertIn("cannot read Tailscale Serve status", script)
        self.assertIn("Tailscale Serve status is invalid", script)
        self.assertIn("absent)", script)
        self.assertNotIn("tailscale serve reset", script)
        self.assertNotIn("tailscale funnel", script)

        preflight = (ROOT / "infra/buzz/scripts/preflight.sh").read_text()
        self.assertIn(".AllowFunnel[$authority] // false", preflight)
        self.assertIn('tls_port="${tls_port:-8443}"', preflight)
        self.assertIn('tls_backend_port="${tls_backend_port:-13000}"', preflight)
        self.assertIn('"${tls_port}" != "80"', preflight)
        self.assertIn('"${tls_port}" != "443"', preflight)
        self.assertIn('"${tls_port}" != "${port}"', preflight)
        self.assertIn('"${tls_port}" != "${pairing_port}"', preflight)

        run = (ROOT / "infra/buzz/run.sh").read_text()
        stop = run.split("  stop)\n", 1)[1].split("    ;;", 1)[0]
        down = run.split("  down)\n", 1)[1].split("    ;;", 1)[0]
        self.assertLess(
            stop.index("tailscale-serve.sh remove"), stop.index("compose stop")
        )
        self.assertLess(
            down.index("tailscale-serve.sh remove"), down.index("compose down")
        )
        status = run.split("  status|ps)\n", 1)[1].split("    ;;", 1)[0]
        self.assertIn("compose ps --status running --services", status)
        self.assertIn("tailscale-serve.sh status", status)
        self.assertIn("tailscale-serve.sh absent", status)

    def test_tailscale_status_errors_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="city2-serve-status-") as raw:
            root = Path(raw)
            scripts = root / "scripts"
            scripts.mkdir()
            script = scripts / "tailscale-serve.sh"
            shutil.copy2(ROOT / "infra/buzz/scripts/tailscale-serve.sh", script)
            (root / ".env").write_text(
                "BUZZ_TLS_HOST=node.tailnet.ts.net\n"
                "BUZZ_TLS_PORT=65533\n"
                "BUZZ_TLS_BACKEND_PORT=65534\n"
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            tailscale = bin_dir / "tailscale"
            tailscale.write_text("#!/bin/sh\nexit 7\n")
            tailscale.chmod(0o755)
            process_env = os.environ.copy()
            process_env["PATH"] = f"{bin_dir}:{process_env['PATH']}"

            for action in ("preflight", "remove", "absent"):
                result = subprocess.run(
                    [str(script), action],
                    env=process_env,
                    text=True,
                    capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("cannot read Tailscale Serve status", result.stderr)

            tailscale.write_text("#!/bin/sh\nprintf 'not-json\\n'\n")
            tailscale.chmod(0o755)
            result = subprocess.run(
                [str(script), "remove"],
                env=process_env,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Tailscale Serve status is invalid", result.stderr)

    def test_disposable_e2e_reserves_a_distinct_pairing_port(self) -> None:
        e2e = (ROOT / "infra/buzz/scripts/e2e-disposable.sh").read_text()
        self.assertIn('pairing_port="${candidate_pairing}"', e2e)
        self.assertIn("BUZZ_PAIRING_PORT=${pairing_port}", e2e)
        self.assertIn("BUZZ_TLS_BACKEND_PORT=${tls_backend_port}", e2e)
        self.assertIn(
            "BUZZ_PAIRING_RELAY_URL=ws://127.0.0.1:${pairing_port}/pair",
            e2e,
        )
        self.assertIn("stage=\"pairing-proxy\"", e2e)
        self.assertIn("stage=\"tls-ingress\"", e2e)
        self.assertIn("stage=\"community-host-migration\"", e2e)
        self.assertIn("rm -sf tls-ingress", e2e)
        self.assertIn('CITY2_BACKUP_ROOT="${TMP_ROOT}/migration-backup"', e2e)
        self.assertIn("tenant-preserving-host-migration=pass", e2e)
        self.assertIn("'^HTTP/1\\.[01] 101 '", e2e)
        self.assertIn('"${pair_base}/other"', e2e)
        self.assertIn("tar --exclude='./.env'", e2e)


if __name__ == "__main__":
    unittest.main()
