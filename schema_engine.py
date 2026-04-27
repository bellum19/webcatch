"""
Webhook schema inference and validation engine.
Analyzes JSON webhook bodies to infer a JSON Schema-like structure,
then validates new webhooks against it.
"""

import json
from typing import Any, Optional


def _get_json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _merge_types(existing: list, new_type: str) -> list:
    types = set(existing) if isinstance(existing, list) else {existing} if existing else set()
    types.add(new_type)
    return sorted(types)


def _infer_value_schema(value: Any, current: Optional[dict] = None) -> dict:
    """Infer schema for a single value, merging with existing schema if provided."""
    current = current or {}
    vtype = _get_json_type(value)

    schema = {"type": _merge_types(current.get("type", []), vtype)}

    if vtype == "array" and value:
        # Merge schemas of all items
        item_schema = current.get("items", {})
        for item in value:
            item_schema = _infer_value_schema(item, item_schema)
        schema["items"] = item_schema
    elif vtype == "object" and value:
        properties = dict(current.get("properties", {}))
        required = set(current.get("required", []))
        for key, val in value.items():
            properties[key] = _infer_value_schema(val, properties.get(key))
            required.add(key)
        schema["properties"] = properties
        schema["required"] = sorted(required)
    elif vtype == "string" and value:
        # Track enum-like values (if few distinct values seen)
        enum_vals = set(current.get("enum", []))
        enum_vals.add(value)
        if len(enum_vals) <= 10:
            schema["enum"] = sorted(enum_vals)
        elif "enum" in current:
            # Too many distinct values, drop enum
            pass
    elif vtype in ("integer", "number") and value is not None:
        # Track min/max
        nums = current.get("_samples", []) + [value]
        schema["minimum"] = min(nums)
        schema["maximum"] = max(nums)
        schema["_samples"] = nums[-100:]  # keep last 100 samples

    return schema


def infer_schema(bodies: list[str]) -> Optional[dict]:
    """
    Infer a JSON schema from a list of webhook body strings.
    Only JSON bodies are considered; non-JSON returns None.
    """
    schemas = []
    for body in bodies:
        if not body:
            continue
        try:
            data = json.loads(body)
            if isinstance(data, dict):
                schemas.append(data)
        except (json.JSONDecodeError, ValueError):
            continue

    if not schemas:
        return None

    merged = {}
    for data in schemas:
        merged = _infer_value_schema(data, merged)

    # Clean up internal tracking fields
    def clean(s: dict) -> dict:
        s.pop("_samples", None)
        if "properties" in s:
            for k, v in s["properties"].items():
                clean(v)
        if "items" in s:
            clean(s["items"])
        return s

    return clean(merged)


def _validate_value(value: Any, schema: dict, path: str) -> list[str]:
    """Validate a value against a schema, returning a list of error messages."""
    errors = []
    if not schema:
        return errors

    vtype = _get_json_type(value)
    allowed_types = schema.get("type", [])
    if isinstance(allowed_types, str):
        allowed_types = [allowed_types]

    # Coerce number/integer overlap
    if vtype == "integer" and "number" in allowed_types:
        vtype = "number"
    if vtype == "number" and "integer" in allowed_types and isinstance(value, float) and value.is_integer():
        vtype = "integer"

    if vtype not in allowed_types and "null" not in allowed_types:
        errors.append(f"{path}: expected type {allowed_types}, got {vtype}")
        return errors

    if vtype == "object" and "properties" in schema:
        props = schema["properties"]
        required = set(schema.get("required", []))
        if isinstance(value, dict):
            for key in required:
                if key not in value:
                    errors.append(f"{path}: missing required field '{key}'")
            for key, val in value.items():
                if key in props:
                    errors.extend(_validate_value(val, props[key], f"{path}.{key}"))
                else:
                    errors.append(f"{path}: unexpected field '{key}'")

    if vtype == "array" and "items" in schema:
        if isinstance(value, list):
            for i, item in enumerate(value):
                errors.extend(_validate_value(item, schema["items"], f"{path}[{i}]"))

    if vtype == "string" and "enum" in schema:
        if value not in schema["enum"]:
            errors.append(f"{path}: value '{value}' not in enum {schema['enum']}")

    if vtype in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: value {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: value {value} > maximum {schema['maximum']}")

    return errors


def validate_body(body: Optional[str], schema: dict) -> list[str]:
    """Validate a webhook body string against an inferred schema."""
    if not body:
        return ["body is empty but schema expects JSON"]
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError) as e:
        return [f"body is not valid JSON: {e}"]
    return _validate_value(data, schema, "body")


def to_openapi(schema: dict, title: str = "Webhook") -> dict:
    """Convert an inferred schema to an OpenAPI-compatible schema object."""
    return {
        "openapi": "3.0.0",
        "info": {"title": title, "version": "1.0.0"},
        "paths": {
            "/webhook": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": schema,
                            }
                        }
                    }
                }
            }
        },
    }
