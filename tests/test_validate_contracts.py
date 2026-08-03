import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_contracts", ROOT / "scripts" / "validate_contracts.py"
)
validate_contracts = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validate_contracts)


class ContractValidationTests(unittest.TestCase):
    def test_repository_contracts_and_fixtures(self):
        counts = validate_contracts.validate_repository()
        self.assertGreaterEqual(counts["schemas"], 19)
        self.assertGreaterEqual(counts["valid"], counts["schemas"] - 1)
        self.assertGreaterEqual(counts["invalid"], 12)
        self.assertGreaterEqual(counts["inline"], 4)

    def test_custom_validator_rejects_additional_property(self):
        store = validate_contracts.SchemaStore()
        instance = validate_contracts.load_json(
            ROOT / "fixtures" / "contracts" / "v1" / "valid" / "agent.json"
        )
        instance["provider_session"] = "must-not-be-canonical"
        with self.assertRaises(validate_contracts.ValidationError):
            validate_contracts.validate_instance(
                instance, store.documents["agent.schema.json"], store, "agent.schema.json"
            )

    def test_semantics_reject_allow_with_denied_dimension(self):
        instance = {
            "schema_version": "city2.authority-decision/v1",
            "decision": "allow",
            "checks": [{"result": "deny"}],
        }
        with self.assertRaises(validate_contracts.ValidationError):
            validate_contracts.validate_semantics(instance)

    def test_custom_validator_uses_json_boolean_equality(self):
        store = validate_contracts.SchemaStore()
        with self.assertRaises(validate_contracts.ValidationError):
            validate_contracts.validate_instance(
                1, {"const": True}, store, "inline.schema.json"
            )

    def test_canonical_parameters_reject_secret_shaped_keys(self):
        store = validate_contracts.SchemaStore()
        instance = validate_contracts.load_json(
            ROOT / "fixtures" / "contracts" / "v1" / "valid" / "approval.json"
        )
        instance["canonical_parameters"] = {"nested": {"api_key": "redacted"}}
        with self.assertRaises(validate_contracts.ValidationError):
            validate_contracts.validate_instance(
                instance,
                store.documents["approval.schema.json"],
                store,
                "approval.schema.json",
            )

    def test_provider_scan_uses_token_boundaries(self):
        self.assertEqual(
            validate_contracts.forbidden_canonical_terms({"suite": "portable"}),
            [],
        )
        self.assertEqual(
            validate_contracts.forbidden_canonical_terms(
                {"runtime": "openai-compatible"}
            ),
            ["openai"],
        )
        self.assertEqual(
            validate_contracts.forbidden_canonical_terms(
                {"openaiCompatible": True, "runtime": "anthropicModel"}
            ),
            ["anthropic", "openai"],
        )

    def test_repository_binding_matches_manifest_authority(self):
        from city2core.model import digest_profile

        store = validate_contracts.SchemaStore()
        instance = validate_contracts.load_json(
            ROOT / "config" / "expansion-admission.m7.json"
        )
        instance["candidate"]["kind"] = "write-authority"
        instance["candidate"]["target_authority"] = "A1"
        instance["incident_boundary"]["authority_ceiling"] = "A1"
        instance["decision_sha256"] = digest_profile(
            instance, {"aggregate_version", "decision_sha256"}
        )
        validate_contracts.validate_semantics(instance)
        with self.assertRaisesRegex(
            validate_contracts.ValidationError, "authority classes disagree"
        ):
            validate_contracts.validate_repository_bindings(instance, store)

    def test_repository_binding_enforces_manifest_budget(self):
        from city2core.model import digest_profile

        store = validate_contracts.SchemaStore()
        instance = validate_contracts.load_json(
            ROOT / "config" / "expansion-admission.m7.json"
        )
        instance["budget"]["max_runtime_seconds"] = 1
        instance["decision_sha256"] = digest_profile(
            instance, {"aggregate_version", "decision_sha256"}
        )
        validate_contracts.validate_semantics(instance)
        with self.assertRaisesRegex(
            validate_contracts.ValidationError, "runtime exceeds"
        ):
            validate_contracts.validate_repository_bindings(instance, store)

    def test_repository_binding_rejects_unresolvable_manifest(self):
        from city2core.model import digest_profile

        store = validate_contracts.SchemaStore()
        instance = validate_contracts.load_json(
            ROOT / "config" / "expansion-admission.m7.json"
        )
        instance["candidate"]["manifest_uri"] = "artifact:unresolved-manifest"
        instance["decision_sha256"] = digest_profile(
            instance, {"aggregate_version", "decision_sha256"}
        )
        validate_contracts.validate_semantics(instance)
        with self.assertRaisesRegex(
            validate_contracts.ValidationError, "resolvable Git reference"
        ):
            validate_contracts.validate_repository_bindings(instance, store)

    def test_pinned_git_reference_reads_named_commit(self):
        revision = validate_contracts.subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        pinned = validate_contracts._git_reference_bytes(
            f"git:README.md@{revision}"
        )
        self.assertIsNotNone(pinned)
        expected = validate_contracts.subprocess.check_output(
            ["git", "show", f"{revision}:README.md"], cwd=ROOT
        )
        self.assertEqual(pinned, expected)

    def test_git_blob_reference_is_history_independent(self):
        blob_sha = validate_contracts.subprocess.check_output(
            ["git", "rev-parse", "HEAD:README.md"], cwd=ROOT, text=True
        ).strip()
        content = validate_contracts._git_blob_reference_bytes(
            f"git-blob:{blob_sha}"
        )
        self.assertEqual(
            content,
            validate_contracts.subprocess.check_output(
                ["git", "cat-file", "blob", blob_sha], cwd=ROOT
            ),
        )

    def test_unpinned_git_reference_rejects_untracked_file(self):
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=build) as untracked:
            relative = Path(untracked.name).relative_to(ROOT)
            with self.assertRaisesRegex(
                validate_contracts.ValidationError, "tracked Git index"
            ):
                validate_contracts._git_reference_bytes(f"git:{relative}")

    def test_unpinned_git_reference_rejects_unstaged_change(self):
        dirty = validate_contracts.subprocess.CompletedProcess(
            ["git", "diff"], returncode=1
        )
        with mock.patch.object(validate_contracts.subprocess, "run", return_value=dirty):
            with self.assertRaisesRegex(
                validate_contracts.ValidationError, "unstaged changes"
            ):
                validate_contracts._git_reference_bytes("git:README.md")

    def test_repository_binding_requires_pinned_git_evidence(self):
        from city2core.model import digest_profile, sha256_bytes

        store = validate_contracts.SchemaStore()
        instance = validate_contracts.load_json(
            ROOT / "fixtures" / "contracts" / "v1" / "valid" / "expansion-admission.json"
        )
        content = validate_contracts._git_reference_bytes("git:README.md")
        self.assertIsNotNone(content)
        reference = instance["measurement"]["evidence_refs"][0]
        reference["uri"] = "git:README.md"
        reference["content_sha256"] = sha256_bytes(content)
        instance["decision_sha256"] = digest_profile(
            instance, {"aggregate_version", "decision_sha256"}
        )
        validate_contracts.validate_semantics(instance)
        with self.assertRaisesRegex(
            validate_contracts.ValidationError, "full commit SHA"
        ):
            validate_contracts.validate_repository_bindings(instance, store)

    def test_schema_accepts_explicit_threshold(self):
        from city2core.model import digest_profile

        store = validate_contracts.SchemaStore()
        instance = validate_contracts.load_json(
            ROOT / "fixtures" / "contracts" / "v1" / "valid" / "expansion-admission.json"
        )
        instance["measurement"].update(
            threshold_mode="explicit",
            baseline_value="multi-host-writes-required",
            admission_threshold="multi-host-writes-required",
            target_value="multi-host-writes-supported",
            direction="match",
        )
        instance["decision_sha256"] = digest_profile(
            instance, {"aggregate_version", "decision_sha256"}
        )
        validate_contracts.validate_instance(
            instance,
            store.documents["expansion-admission.schema.json"],
            store,
            "expansion-admission.schema.json",
        )
        validate_contracts.validate_semantics(instance)


if __name__ == "__main__":
    unittest.main()
