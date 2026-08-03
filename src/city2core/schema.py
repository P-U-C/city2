"""Offline JSON Schema subset shared by Core and repository conformance tests."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_DIR = REPOSITORY_ROOT / "schemas" / "v1"


class ValidationError(ValueError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        try:
            label = path.relative_to(REPOSITORY_ROOT)
        except ValueError:
            label = path
        raise ValidationError(f"{label}: invalid JSON: {error}") from error


class SchemaStore:
    def __init__(self, schema_dir: Path = DEFAULT_SCHEMA_DIR) -> None:
        self.paths = {path.name: path for path in schema_dir.glob("*.json")}
        self.documents = {name: load_json(path) for name, path in self.paths.items()}
        self.by_id = {
            document.get("$id"): document
            for document in self.documents.values()
            if document.get("$id")
        }

    def resolve(
        self, ref: str, current_name: str, current_root: dict[str, Any]
    ) -> tuple[Any, str, dict[str, Any]]:
        target, separator, fragment = ref.partition("#")
        if not target:
            document = current_root
            name = current_name
        else:
            name = Path(target).name
            if name not in self.documents:
                raise ValidationError(
                    f"{current_name}: unresolved schema reference {ref!r}"
                )
            document = self.documents[name]
        node: Any = document
        if separator and fragment:
            if not fragment.startswith("/"):
                raise ValidationError(
                    f"{current_name}: unsupported reference fragment {ref!r}"
                )
            for raw_part in fragment[1:].split("/"):
                part = raw_part.replace("~1", "/").replace("~0", "~")
                try:
                    node = node[part]
                except (KeyError, TypeError) as error:
                    raise ValidationError(
                        f"{current_name}: unresolved schema reference {ref!r}"
                    ) from error
        return node, name, document


def _is_type(instance: Any, expected: str) -> bool:
    return {
        "array": lambda: isinstance(instance, list),
        "boolean": lambda: isinstance(instance, bool),
        "integer": lambda: isinstance(instance, int) and not isinstance(instance, bool),
        "null": lambda: instance is None,
        "number": lambda: (
            isinstance(instance, (int, float)) and not isinstance(instance, bool)
        ),
        "object": lambda: isinstance(instance, dict),
        "string": lambda: isinstance(instance, str),
    }.get(expected, lambda: False)()


def json_equal(left: Any, right: Any) -> bool:
    """JSON Schema equality: booleans differ from numbers; numeric forms do not."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(
            json_equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            json_equal(left[key], right[key]) for key in left
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
        target, target_name, target_root = store.resolve(
            schema["$ref"], schema_name, document_root
        )
        validate_instance(instance, target, store, target_name, path, target_root)

    for child in schema.get("allOf", []):
        validate_instance(instance, child, store, schema_name, path, document_root)

    for keyword, expected_matches in (("anyOf", 1), ("oneOf", 1)):
        if keyword not in schema:
            continue
        matches = 0
        for child in schema[keyword]:
            try:
                validate_instance(
                    instance, child, store, schema_name, path, document_root
                )
            except ValidationError:
                continue
            matches += 1
        if (keyword == "anyOf" and matches < expected_matches) or (
            keyword == "oneOf" and matches != expected_matches
        ):
            raise ValidationError(f"{path}: does not satisfy {keyword}")

    if "not" in schema:
        try:
            validate_instance(
                instance, schema["not"], store, schema_name, path, document_root
            )
        except ValidationError:
            pass
        else:
            raise ValidationError(f"{path}: satisfies prohibited schema")

    expected_types = schema.get("type")
    if expected_types is not None:
        expected_types = (
            [expected_types] if isinstance(expected_types, str) else expected_types
        )
        if not any(_is_type(instance, expected) for expected in expected_types):
            raise ValidationError(
                f"{path}: expected type {expected_types}, got {type(instance).__name__}"
            )

    if "const" in schema and not json_equal(instance, schema["const"]):
        raise ValidationError(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and not any(
        json_equal(instance, choice) for choice in schema["enum"]
    ):
        raise ValidationError(f"{path}: value is not in enum")

    if isinstance(instance, dict):
        if isinstance(schema.get("propertyNames"), dict):
            for key in instance:
                validate_instance(
                    key,
                    schema["propertyNames"],
                    store,
                    schema_name,
                    f"{path}.<property-name>",
                    document_root,
                )
        for key in schema.get("required", []):
            if key not in instance:
                raise ValidationError(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                validate_instance(
                    value,
                    properties[key],
                    store,
                    schema_name,
                    f"{path}.{key}",
                    document_root,
                )
            elif schema.get("additionalProperties") is False:
                raise ValidationError(f"{path}: unexpected property {key!r}")
            elif isinstance(schema.get("additionalProperties"), dict):
                validate_instance(
                    value,
                    schema["additionalProperties"],
                    store,
                    schema_name,
                    f"{path}.{key}",
                    document_root,
                )

    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            raise ValidationError(f"{path}: fewer than minItems")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise ValidationError(f"{path}: more than maxItems")
        if schema.get("uniqueItems"):
            for index, item in enumerate(instance):
                if any(json_equal(item, prior) for prior in instance[:index]):
                    raise ValidationError(f"{path}: array values are not unique")
        if isinstance(schema.get("items"), dict):
            for index, value in enumerate(instance):
                validate_instance(
                    value,
                    schema["items"],
                    store,
                    schema_name,
                    f"{path}[{index}]",
                    document_root,
                )

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


def validate_named(
    instance: Any, schema_name: str, store: SchemaStore | None = None
) -> None:
    schemas = store or SchemaStore()
    try:
        schema = schemas.documents[schema_name]
    except KeyError as error:
        raise ValidationError(f"unknown City2 schema: {schema_name}") from error
    validate_instance(instance, schema, schemas, schema_name)
