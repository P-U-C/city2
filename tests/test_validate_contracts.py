import importlib.util
import unittest
from pathlib import Path


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
        self.assertEqual(counts["schemas"] - 1, counts["valid"])
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


if __name__ == "__main__":
    unittest.main()
