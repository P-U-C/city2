#!/usr/bin/env python3
"""Validate City2 v1 schemas and golden contract fixtures without network access."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "v1"
FIXTURE_ROOT = ROOT / "fixtures" / "contracts" / "v1"

SCHEMA_KEYS = {
    "$schema", "$id", "$defs", "$ref", "title", "description", "type",
    "required", "properties", "propertyNames", "additionalProperties", "items", "minItems",
    "maxItems", "uniqueItems", "enum", "const", "pattern", "minLength",
    "maxLength", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "anyOf", "oneOf", "allOf", "not",
}
FORBIDDEN_CANONICAL_TERMS = ("anthropic", "buzz", "openai", "pfterminal", "sui", "walrus")
FORBIDDEN_PROPERTY_NAMES = {
    "access_token", "api_key", "mnemonic", "password", "private_key",
    "recovery_phrase", "secret", "seed_phrase",
}


class ValidationError(ValueError):
    pass


class SchemaStore:
    def __init__(self, schema_dir: Path = SCHEMA_DIR) -> None:
        self.paths = {path.name: path for path in schema_dir.glob("*.json")}
        self.documents = {name: load_json(path) for name, path in self.paths.items()}
        self.by_id = {doc.get("$id"): doc for doc in self.documents.values() if doc.get("$id")}

    def resolve(self, ref: str, current_name: str, current_root: dict[str, Any]) -> tuple[Any, str, dict[str, Any]]:
        target, separator, fragment = ref.partition("#")
        if not target:
            document = current_root
            name = current_name
        else:
            name = Path(target).name
            if name not in self.documents:
                raise ValidationError(f"{current_name}: unresolved schema reference {ref!r}")
            document = self.documents[name]
        node: Any = document
        if separator and fragment:
            if not fragment.startswith("/"):
                raise ValidationError(f"{current_name}: unsupported reference fragment {ref!r}")
            for raw_part in fragment[1:].split("/"):
                part = raw_part.replace("~1", "/").replace("~0", "~")
                try:
                    node = node[part]
                except (KeyError, TypeError) as error:
                    raise ValidationError(f"{current_name}: unresolved schema reference {ref!r}") from error
        return node, name, document


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid JSON: {error}") from error


def _is_type(instance: Any, expected: str) -> bool:
    return {
        "array": lambda: isinstance(instance, list),
        "boolean": lambda: isinstance(instance, bool),
        "integer": lambda: isinstance(instance, int) and not isinstance(instance, bool),
        "null": lambda: instance is None,
        "number": lambda: isinstance(instance, (int, float)) and not isinstance(instance, bool),
        "object": lambda: isinstance(instance, dict),
        "string": lambda: isinstance(instance, str),
    }.get(expected, lambda: False)()


def _json_equal(left: Any, right: Any) -> bool:
    """JSON Schema equality: booleans differ from numbers; numeric forms do not."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    return left == right


def validate_instance(
    instance: Any,
    schema: dict[str, Any],
    store: SchemaStore,
    schema_name: str,
    path: str = "$",
    document_root: dict[str, Any] | None = None,
) -> None:
    """Validate the deliberate JSON Schema subset used by City2 contracts."""
    document_root = document_root or schema
    if "$ref" in schema:
        target, target_name, target_root = store.resolve(schema["$ref"], schema_name, document_root)
        validate_instance(instance, target, store, target_name, path, target_root)

    for keyword in ("allOf",):
        for child in schema.get(keyword, []):
            validate_instance(instance, child, store, schema_name, path, document_root)

    for keyword, expected_matches in (("anyOf", 1), ("oneOf", 1)):
        if keyword not in schema:
            continue
        matches = 0
        for child in schema[keyword]:
            try:
                validate_instance(instance, child, store, schema_name, path, document_root)
            except ValidationError:
                continue
            matches += 1
        if (keyword == "anyOf" and matches < expected_matches) or (keyword == "oneOf" and matches != expected_matches):
            raise ValidationError(f"{path}: does not satisfy {keyword}")

    if "not" in schema:
        try:
            validate_instance(instance, schema["not"], store, schema_name, path, document_root)
        except ValidationError:
            pass
        else:
            raise ValidationError(f"{path}: satisfies prohibited schema")

    expected_types = schema.get("type")
    if expected_types is not None:
        expected_types = [expected_types] if isinstance(expected_types, str) else expected_types
        if not any(_is_type(instance, expected) for expected in expected_types):
            raise ValidationError(f"{path}: expected type {expected_types}, got {type(instance).__name__}")

    if "const" in schema and not _json_equal(instance, schema["const"]):
        raise ValidationError(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and not any(_json_equal(instance, choice) for choice in schema["enum"]):
        raise ValidationError(f"{path}: value is not in enum")

    if isinstance(instance, dict):
        if isinstance(schema.get("propertyNames"), dict):
            for key in instance:
                validate_instance(
                    key, schema["propertyNames"], store, schema_name,
                    f"{path}.<property-name>", document_root,
                )
        for key in schema.get("required", []):
            if key not in instance:
                raise ValidationError(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                validate_instance(value, properties[key], store, schema_name, f"{path}.{key}", document_root)
            elif schema.get("additionalProperties") is False:
                raise ValidationError(f"{path}: unexpected property {key!r}")
            elif isinstance(schema.get("additionalProperties"), dict):
                validate_instance(value, schema["additionalProperties"], store, schema_name, f"{path}.{key}", document_root)

    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            raise ValidationError(f"{path}: fewer than minItems")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise ValidationError(f"{path}: more than maxItems")
        if schema.get("uniqueItems"):
            for index, item in enumerate(instance):
                if any(_json_equal(item, prior) for prior in instance[:index]):
                    raise ValidationError(f"{path}: array values are not unique")
        if isinstance(schema.get("items"), dict):
            for index, value in enumerate(instance):
                validate_instance(value, schema["items"], store, schema_name, f"{path}[{index}]", document_root)

    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            raise ValidationError(f"{path}: string is shorter than minLength")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise ValidationError(f"{path}: string is longer than maxLength")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            raise ValidationError(f"{path}: string does not match pattern")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            raise ValidationError(f"{path}: value is below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            raise ValidationError(f"{path}: value is above maximum")
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            raise ValidationError(f"{path}: value is not above exclusiveMinimum")
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            raise ValidationError(f"{path}: value is not below exclusiveMaximum")


def lint_schema(schema: dict[str, Any], location: str = "$", property_names: set[str] | None = None) -> None:
    unknown = set(schema) - SCHEMA_KEYS
    if unknown:
        raise ValidationError(f"{location}: unsupported schema keywords: {sorted(unknown)}")
    property_names = property_names if property_names is not None else set()
    for name, child in schema.get("properties", {}).items():
        property_names.add(name)
        lint_schema(child, f"{location}.properties.{name}", property_names)
    if isinstance(schema.get("propertyNames"), dict):
        lint_schema(schema["propertyNames"], f"{location}.propertyNames", property_names)
    for name, child in schema.get("$defs", {}).items():
        lint_schema(child, f"{location}.$defs.{name}", property_names)
    if isinstance(schema.get("items"), dict):
        lint_schema(schema["items"], f"{location}.items", property_names)
    if isinstance(schema.get("additionalProperties"), dict):
        lint_schema(schema["additionalProperties"], f"{location}.additionalProperties", property_names)
    for keyword in ("allOf", "anyOf", "oneOf"):
        for index, child in enumerate(schema.get(keyword, [])):
            lint_schema(child, f"{location}.{keyword}[{index}]", property_names)
    if isinstance(schema.get("not"), dict):
        lint_schema(schema["not"], f"{location}.not", property_names)


def validate_semantics(instance: dict[str, Any]) -> None:
    version = instance.get("schema_version")
    if version == "city2.memory/v1":
        if instance.get("type") != "hypothesis" and not instance.get("evidence_refs"):
            raise ValidationError("memory: non-hypothesis records require evidence")
        for evidence in instance.get("evidence_refs", []):
            if evidence.get("relationship") == "derived_from" and not {
                "derivation_method", "derivation_version"
            }.issubset(evidence):
                raise ValidationError("memory: derived evidence requires method and version")
    elif version == "city2.approval/v1":
        if instance["executions_consumed"] > instance["maximum_executions"]:
            raise ValidationError("approval: consumed executions exceed maximum")
    elif version == "city2.task/v1":
        criteria = [item["criterion_id"] for item in instance["acceptance_criteria"]]
        if len(criteria) != len(set(criteria)):
            raise ValidationError("task: criterion IDs must be unique")
    elif version == "city2.event/v1":
        prefixes = {
            "agent": "agt_", "objective": "obj_", "task": "tsk_", "run": "run_",
            "memory": "mem_", "approval": "apr_", "action": "act_",
            "deletion": "del_", "archive": "arc_",
        }
        if not instance["aggregate_id"].startswith(prefixes[instance["aggregate_type"]]):
            raise ValidationError("event: aggregate type and ID prefix disagree")
    elif version == "city2.runner-capability/v1":
        unsupported = set(instance["unsupported"])
        degraded = {item["capability"] for item in instance["degraded"]}
        for capability, state in instance["capabilities"].items():
            if state == "unsupported" and capability not in unsupported:
                raise ValidationError(f"runner: unsupported capability {capability!r} is not declared")
            if state in {"best_effort", "cooperative", "estimated", "partial"} and capability not in degraded:
                raise ValidationError(f"runner: degraded capability {capability!r} is not declared")
    elif version == "city2.authority-decision/v1":
        required = {
            "task", "manifest", "runner", "tool", "filesystem", "network",
            "credential", "authority", "approval",
        }
        dimensions = [check.get("dimension") for check in instance["checks"]]
        if set(dimensions) != required or len(dimensions) != len(required):
            raise ValidationError("authority: decision must contain each required dimension exactly once")
        if instance["decision"] == "allow" and any(
            check["result"] != "allow" for check in instance["checks"]
        ):
            raise ValidationError("authority: allow requires every dimension to allow")


def _standard_validate(instance: Any, schema: dict[str, Any], store: SchemaStore) -> None:
    """Cross-check with jsonschema when present; offline validation never requires it."""
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
    except ImportError:
        return
    registry = Registry().with_resources(
        (schema_id, Resource.from_contents(document))
        for schema_id, document in store.by_id.items()
    )
    errors = sorted(
        Draft202012Validator(schema, registry=registry).iter_errors(instance),
        key=lambda error: list(error.path),
    )
    if errors:
        raise ValidationError(f"standard validator: {errors[0].message}")


def validate_repository() -> dict[str, int]:
    store = SchemaStore()
    if not store.documents:
        raise ValidationError("no contract schemas found")

    ids: set[str] = set()
    versions: dict[str, str] = {}
    for name, schema in sorted(store.documents.items()):
        lint_schema(schema, name)
        schema_id = schema.get("$id")
        if not schema_id or schema_id in ids:
            raise ValidationError(f"{name}: missing or duplicate $id")
        ids.add(schema_id)
        if not schema_id.endswith("/" + name):
            raise ValidationError(f"{name}: $id does not end with filename")
        lowered = json.dumps(schema, sort_keys=True).lower()
        found = [term for term in FORBIDDEN_CANONICAL_TERMS if term in lowered]
        if found:
            raise ValidationError(f"{name}: provider/interface-specific canonical term: {found}")
        property_names: set[str] = set()
        lint_schema(schema, name, property_names)
        forbidden = property_names & FORBIDDEN_PROPERTY_NAMES
        if forbidden:
            raise ValidationError(f"{name}: secret-bearing properties are prohibited: {sorted(forbidden)}")
        version = schema.get("properties", {}).get("schema_version", {}).get("const")
        if name != "common.schema.json":
            if not version or version in versions:
                raise ValidationError(f"{name}: missing or duplicate schema_version constant")
            versions[version] = name

    manifest = load_json(FIXTURE_ROOT / "manifest.json")
    expected_schemas = set(store.documents) - {"common.schema.json"}
    covered_schemas = {item["schema"] for item in manifest["valid"]}
    if expected_schemas != covered_schemas:
        raise ValidationError(
            f"fixture coverage mismatch: missing={sorted(expected_schemas - covered_schemas)}, "
            f"extra={sorted(covered_schemas - expected_schemas)}"
        )

    valid_count = 0
    for item in manifest["valid"]:
        schema = store.documents[item["schema"]]
        instance_path = (FIXTURE_ROOT / item["instance"]).resolve()
        instance = load_json(instance_path)
        validate_instance(instance, schema, store, item["schema"])
        validate_semantics(instance)
        _standard_validate(instance, schema, store)
        round_trip = json.loads(json.dumps(instance, sort_keys=True, separators=(",", ":")))
        if round_trip != instance:
            raise ValidationError(f"{instance_path.relative_to(ROOT)}: JSON round-trip changed data")
        valid_count += 1

    invalid_count = 0
    for item in manifest["invalid"]:
        schema = store.documents[item["schema"]]
        instance_path = (FIXTURE_ROOT / item["instance"]).resolve()
        instance = load_json(instance_path)
        schema_failed = False
        try:
            validate_instance(instance, schema, store, item["schema"])
            _standard_validate(instance, schema, store)
        except ValidationError:
            schema_failed = True
        if item["validation"] == "schema":
            if not schema_failed:
                raise ValidationError(f"{instance_path.relative_to(ROOT)}: invalid schema fixture passed")
        else:
            if schema_failed:
                raise ValidationError(f"{instance_path.relative_to(ROOT)}: semantic fixture failed schema first")
            try:
                validate_semantics(instance)
            except ValidationError:
                pass
            else:
                raise ValidationError(f"{instance_path.relative_to(ROOT)}: invalid semantic fixture passed")
        invalid_count += 1

    inline_count = 0
    spec_text = (ROOT / "docs" / "COMPANY-OS-SPEC.md").read_text(encoding="utf-8")
    for match in re.finditer(r"```json\n(\{.*?\})\n```", spec_text, re.DOTALL):
        instance = json.loads(match.group(1))
        version = instance.get("schema_version")
        if version not in versions:
            raise ValidationError(f"COMPANY-OS-SPEC.md: unknown inline schema_version {version!r}")
        schema_name = versions[version]
        schema = store.documents[schema_name]
        validate_instance(instance, schema, store, schema_name)
        validate_semantics(instance)
        _standard_validate(instance, schema, store)
        inline_count += 1
    if inline_count < 4:
        raise ValidationError("COMPANY-OS-SPEC.md: expected at least four schema-valid inline examples")

    return {
        "schemas": len(store.documents),
        "valid": valid_count,
        "invalid": invalid_count,
        "inline": inline_count,
    }


def main() -> int:
    try:
        counts = validate_repository()
    except ValidationError as error:
        print(f"contract validation: FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "contract validation: PASS "
        f"({counts['schemas']} schemas, {counts['valid']} valid, "
        f"{counts['invalid']} invalid fixtures, {counts['inline']} inline examples)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
