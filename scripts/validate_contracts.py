#!/usr/bin/env python3
"""Validate City2 v1 schemas and golden contract fixtures without network access."""

from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SCHEMA_DIR = ROOT / "schemas" / "v1"
FIXTURE_ROOT = ROOT / "fixtures" / "contracts" / "v1"

SCHEMA_KEYS = {
    "$schema",
    "$id",
    "$defs",
    "$ref",
    "title",
    "description",
    "type",
    "required",
    "properties",
    "propertyNames",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "uniqueItems",
    "enum",
    "const",
    "pattern",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "anyOf",
    "oneOf",
    "allOf",
    "not",
}
FORBIDDEN_CANONICAL_TERMS = (
    "anthropic",
    "buzz",
    "openai",
    "pfterminal",
    "sui",
    "walrus",
)
FORBIDDEN_PROPERTY_NAMES = {
    "access_token",
    "api_key",
    "mnemonic",
    "password",
    "private_key",
    "recovery_phrase",
    "secret",
    "seed_phrase",
}


from city2core.schema import (  # noqa: E402
    SchemaStore,
    ValidationError,
    load_json,
    validate_instance,
)
from city2core.expansion import (  # noqa: E402
    ExpansionAdmissionError,
    validate_expansion_admission,
)
from city2core.model import digest_profile, sha256_bytes  # noqa: E402


def forbidden_canonical_terms(document: Any) -> list[str]:
    text = json.dumps(document, sort_keys=True)
    found: list[str] = []
    for term in FORBIDDEN_CANONICAL_TERMS:
        for match in re.finditer(re.escape(term), text, re.IGNORECASE):
            before = text[match.start() - 1] if match.start() else ""
            after = text[match.end()] if match.end() < len(text) else ""
            starts_camel_token = (
                bool(before)
                and before.isalnum()
                and text[match.start()].isupper()
                and before.islower()
            )
            left_boundary = not before or not before.isalnum() or starts_camel_token
            right_boundary = not after or not after.isalnum() or after.isupper()
            if left_boundary and right_boundary:
                found.append(term)
                break
    return found


def lint_schema(
    schema: dict[str, Any], location: str = "$", property_names: set[str] | None = None
) -> None:
    unknown = set(schema) - SCHEMA_KEYS
    if unknown:
        raise ValidationError(
            f"{location}: unsupported schema keywords: {sorted(unknown)}"
        )
    property_names = property_names if property_names is not None else set()
    for name, child in schema.get("properties", {}).items():
        property_names.add(name)
        lint_schema(child, f"{location}.properties.{name}", property_names)
    if isinstance(schema.get("propertyNames"), dict):
        lint_schema(
            schema["propertyNames"], f"{location}.propertyNames", property_names
        )
    for name, child in schema.get("$defs", {}).items():
        lint_schema(child, f"{location}.$defs.{name}", property_names)
    if isinstance(schema.get("items"), dict):
        lint_schema(schema["items"], f"{location}.items", property_names)
    if isinstance(schema.get("additionalProperties"), dict):
        lint_schema(
            schema["additionalProperties"],
            f"{location}.additionalProperties",
            property_names,
        )
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
                "derivation_method",
                "derivation_version",
            }.issubset(evidence):
                raise ValidationError(
                    "memory: derived evidence requires method and version"
                )
    elif version == "city2.approval/v1":
        if instance["executions_consumed"] > instance["maximum_executions"]:
            raise ValidationError("approval: consumed executions exceed maximum")
    elif version == "city2.task/v1":
        criteria = [item["criterion_id"] for item in instance["acceptance_criteria"]]
        if len(criteria) != len(set(criteria)):
            raise ValidationError("task: criterion IDs must be unique")
    elif version == "city2.event/v1":
        prefixes = {
            "agent": "agt_",
            "objective": "obj_",
            "task": "tsk_",
            "run": "run_",
            "memory": "mem_",
            "approval": "apr_",
            "action": "act_",
            "deletion": "del_",
            "archive": "arc_",
        }
        if not instance["aggregate_id"].startswith(
            prefixes[instance["aggregate_type"]]
        ):
            raise ValidationError("event: aggregate type and ID prefix disagree")
    elif version == "city2.runner-capability/v1":
        unsupported = set(instance["unsupported"])
        degraded = {item["capability"] for item in instance["degraded"]}
        for capability, state in instance["capabilities"].items():
            if state == "unsupported" and capability not in unsupported:
                raise ValidationError(
                    f"runner: unsupported capability {capability!r} is not declared"
                )
            if (
                state in {"best_effort", "cooperative", "estimated", "partial"}
                and capability not in degraded
            ):
                raise ValidationError(
                    f"runner: degraded capability {capability!r} is not declared"
                )
    elif version == "city2.authority-decision/v1":
        required = {
            "task",
            "manifest",
            "runner",
            "tool",
            "filesystem",
            "network",
            "credential",
            "authority",
            "approval",
        }
        dimensions = [check.get("dimension") for check in instance["checks"]]
        if set(dimensions) != required or len(dimensions) != len(required):
            raise ValidationError(
                "authority: decision must contain each required dimension exactly once"
            )
        if instance["decision"] == "allow" and any(
            check["result"] != "allow" for check in instance["checks"]
        ):
            raise ValidationError("authority: allow requires every dimension to allow")
    elif version == "city2.expansion-admission/v1":
        try:
            validate_expansion_admission(instance)
        except ExpansionAdmissionError as error:
            raise ValidationError(str(error)) from error


def _git_reference_bytes(uri: str) -> bytes | None:
    if not uri.startswith("git:"):
        return None
    locator = uri.removeprefix("git:")
    relative, separator, revision = locator.rpartition("@")
    if not separator:
        relative, revision = locator, ""
    elif not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValidationError("expansion: Git revision must be a full commit SHA")
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", relative):
        raise ValidationError("expansion: invalid Git repository path")
    repository_path = PurePosixPath(relative)
    if repository_path.is_absolute() or ".." in repository_path.parts:
        raise ValidationError("expansion: Git reference escapes repository")

    if revision:
        commit = subprocess.run(
            ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if commit.returncode:
            raise ValidationError("expansion: Git evidence commit is unavailable")
        content = subprocess.run(
            ["git", "show", f"{revision}:{relative}"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if content.returncode:
            raise ValidationError("expansion: missing file at Git evidence commit")
        return content.stdout

    dirty = subprocess.run(
        ["git", "diff", "--quiet", "--no-ext-diff", "--no-textconv", "--", relative],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if dirty.returncode:
        raise ValidationError(
            f"expansion: unpinned Git reference has unstaged changes {relative!r}"
        )
    content = subprocess.run(
        ["git", "show", f":{relative}"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if content.returncode:
        raise ValidationError(
            f"expansion: missing tracked Git index reference {relative!r}"
        )
    return content.stdout


def _git_blob_reference_bytes(uri: str) -> bytes | None:
    if not uri.startswith("git-blob:"):
        return None
    blob_sha = uri.removeprefix("git-blob:")
    if not re.fullmatch(r"[0-9a-f]{40}", blob_sha):
        raise ValidationError("expansion: Git blob reference must use a full SHA")
    exists = subprocess.run(
        ["git", "cat-file", "-e", f"{blob_sha}^{{blob}}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if exists.returncode:
        raise ValidationError("expansion: Git evidence blob is unavailable")
    content = subprocess.run(
        ["git", "cat-file", "blob", blob_sha],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if content.returncode:
        raise ValidationError("expansion: Git evidence blob is unreadable")
    return content.stdout


def validate_repository_bindings(
    instance: dict[str, Any], store: SchemaStore
) -> None:
    if instance.get("schema_version") != "city2.expansion-admission/v1":
        return

    candidate = instance["candidate"]
    manifest_bytes = _git_reference_bytes(candidate["manifest_uri"])
    if manifest_bytes is None:
        raise ValidationError(
            "expansion: candidate manifest must use a resolvable Git reference"
        )
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(
            "expansion: bound agent manifest is invalid JSON"
        ) from error
    agent_schema = store.documents["agent.schema.json"]
    validate_instance(manifest, agent_schema, store, "agent.schema.json")
    expected = digest_profile(manifest, {"aggregate_version", "manifest_sha256"})
    if manifest["manifest_sha256"] != expected:
        raise ValidationError("expansion: bound agent manifest digest mismatch")
    if candidate["manifest_sha256"] != expected:
        raise ValidationError("expansion: admission binds the wrong agent manifest")
    if candidate["agent_id"] != manifest["agent_id"]:
        raise ValidationError("expansion: admission and agent IDs disagree")
    if candidate["target_authority"] != manifest["authority_class"]:
        raise ValidationError(
            "expansion: admission and manifest authority classes disagree"
        )
    budget = instance["budget"]
    if manifest["time_budget_seconds"] > budget["max_runtime_seconds"]:
        raise ValidationError("expansion: manifest runtime exceeds admission budget")
    if manifest["concurrency"] > budget["max_concurrency"]:
        raise ValidationError("expansion: manifest concurrency exceeds admission budget")
    if Decimal(manifest["cost_budget"]["max_billable_usd"]) > Decimal(
        budget["max_pilot_cost_usd"]
    ):
        raise ValidationError("expansion: manifest billable cost exceeds admission budget")
    if manifest["enabled"]:
        raise ValidationError("expansion: candidate manifest must remain disabled")

    references = list(instance["measurement"]["evidence_refs"])
    for criterion in instance["evaluation"]["criteria"]:
        references.extend(criterion["evidence_refs"])
    for reference in references:
        uri = reference["uri"]
        if uri.startswith("git:") and not re.search(r"@[0-9a-f]{40}$", uri):
            raise ValidationError(
                "expansion: Git evidence must use a full commit SHA"
            )
        content = _git_blob_reference_bytes(uri)
        if content is None:
            content = _git_reference_bytes(uri)
        if content is not None and reference["content_sha256"] != sha256_bytes(
            content
        ):
            raise ValidationError("expansion: Git evidence digest mismatch")


def _standard_validate(
    instance: Any, schema: dict[str, Any], store: SchemaStore
) -> None:
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
        found = forbidden_canonical_terms(schema)
        if found:
            raise ValidationError(
                f"{name}: provider/interface-specific canonical term: {found}"
            )
        property_names: set[str] = set()
        lint_schema(schema, name, property_names)
        forbidden = property_names & FORBIDDEN_PROPERTY_NAMES
        if forbidden:
            raise ValidationError(
                f"{name}: secret-bearing properties are prohibited: {sorted(forbidden)}"
            )
        version = schema.get("properties", {}).get("schema_version", {}).get("const")
        if name != "common.schema.json":
            if not version or version in versions:
                raise ValidationError(
                    f"{name}: missing or duplicate schema_version constant"
                )
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
        validate_repository_bindings(instance, store)
        _standard_validate(instance, schema, store)
        round_trip = json.loads(
            json.dumps(instance, sort_keys=True, separators=(",", ":"))
        )
        if round_trip != instance:
            raise ValidationError(
                f"{instance_path.relative_to(ROOT)}: JSON round-trip changed data"
            )
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
                raise ValidationError(
                    f"{instance_path.relative_to(ROOT)}: invalid schema fixture passed"
                )
        else:
            if schema_failed:
                raise ValidationError(
                    f"{instance_path.relative_to(ROOT)}: semantic fixture failed schema first"
                )
            try:
                validate_semantics(instance)
            except ValidationError:
                pass
            else:
                raise ValidationError(
                    f"{instance_path.relative_to(ROOT)}: invalid semantic fixture passed"
                )
        invalid_count += 1

    inline_count = 0
    spec_text = (ROOT / "docs" / "COMPANY-OS-SPEC.md").read_text(encoding="utf-8")
    for match in re.finditer(r"```json\n(\{.*?\})\n```", spec_text, re.DOTALL):
        instance = json.loads(match.group(1))
        version = instance.get("schema_version")
        if version not in versions:
            raise ValidationError(
                f"COMPANY-OS-SPEC.md: unknown inline schema_version {version!r}"
            )
        schema_name = versions[version]
        schema = store.documents[schema_name]
        validate_instance(instance, schema, store, schema_name)
        validate_semantics(instance)
        _standard_validate(instance, schema, store)
        inline_count += 1
    if inline_count < 4:
        raise ValidationError(
            "COMPANY-OS-SPEC.md: expected at least four schema-valid inline examples"
        )

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
