from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib import error, request

from jsonschema import Draft202012Validator


class OpenAICompatibleV2Model:
    """Stateless structured-output adapter for GoalSpec and world decisions."""

    provider_id: str
    model_id: str

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model_id: str,
        provider_id: str = "openai-compatible",
        timeout_seconds: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model_id
        self.provider_id = provider_id
        self.timeout_seconds = timeout_seconds
        self.last_usage: dict[str, Any] = {}

    def decide(self, context: dict[str, object]) -> dict[str, object]:
        return self._complete(
            purpose="world-decision",
            system=(
                "Return one schema-valid Engine brain decision. You may propose or "
                "consult, but you do not authorize, execute, or claim observed truth."
            ),
            context=context,
            schema=_decision_schema(),
        )

    def compile(self, context: dict[str, object]) -> dict[str, object]:
        return self._complete(
            purpose="goal-compiler",
            system=(
                "Translate the intent into one schema-valid declarative GoalSpec body. "
                "Use only visible capability families and entity ids. When a required_selection "
                "is present, emit one effect using exactly that target, entity, capability family, "
                "and effect schema. JSON Schema minimum and maximum values are validation bounds, "
                "not requested values. Copy explicit quantities from source_intent into the matching "
                "effect parameter and condition value; never copy a schema object into a condition. "
                "Condition paths use observation:<measurement>, never an entity id. Prefer the "
                "smallest sufficient condition. For a numeric observation, 'at least' means gte "
                "and 'at most' means lte; the count operator counts evidence rows, not the numeric "
                "measurement value. Do not create authority."
            ),
            context=context,
            schema=_goal_schema(context),
        )

    def _complete(
        self,
        *,
        purpose: str,
        system: str,
        context: dict[str, object],
        schema: dict[str, Any],
    ) -> dict[str, object]:
        projection = json.dumps(context, sort_keys=True, separators=(",", ":"))
        body = {
            "model": self.model_id,
            "temperature": 0,
            "max_tokens": 1_024 if purpose == "goal-compiler" else 512,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": projection},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "engine_" + purpose.replace("-", "_"),
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        encoded = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        http_request = request.Request(
            f"{self.base_url}/chat/completions",
            data=encoded,
            method="POST",
            headers=headers,
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"model provider rejected {purpose} ({exc.code}): {detail}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"model provider unavailable for {purpose}: {exc}") from exc
        try:
            content = payload["choices"][0]["message"]["content"]
            value = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("model provider returned no schema-valid JSON message") from exc
        if not isinstance(value, dict):
            raise TypeError("model provider returned a non-object")
        Draft202012Validator(schema).validate(value)
        self.last_usage = {
            "provider": self.provider_id,
            "model": payload.get("model", self.model_id),
            "purpose": purpose,
            "usage": payload.get("usage", {}),
            "input_sha256": hashlib.sha256(projection.encode("utf-8")).hexdigest(),
        }
        return value


def _decision_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": [
                    "query_world",
                    "consult_specialist",
                    "propose_effect",
                    "wait",
                    "complete",
                    "abandon",
                ],
            },
            "rationale": {"type": "string", "maxLength": 500},
            "specialist_id": {
                "type": ["string", "null"],
                "maxLength": 200,
            },
            "query": {"type": "object", "maxProperties": 16},
            "proposed_action": {
                "type": ["object", "null"],
                "properties": {
                    "desired_effect_id": {"type": "string", "maxLength": 200},
                    "capability_family": {"type": "string", "maxLength": 200},
                    "target_id": {"type": "string", "maxLength": 200},
                    "entity_id": {"type": "string", "maxLength": 200},
                    "semantic_parameters": {
                        "type": "object",
                        "maxProperties": 16,
                    },
                    "evidence_ids": {
                        "type": "array",
                        "maxItems": 16,
                        "items": {"type": "string", "maxLength": 200},
                    },
                },
                "required": [
                    "desired_effect_id",
                    "capability_family",
                    "target_id",
                    "entity_id",
                    "semantic_parameters",
                    "evidence_ids",
                ],
                "additionalProperties": False,
            },
        },
        "required": [
            "kind",
            "rationale",
            "specialist_id",
            "query",
            "proposed_action",
        ],
        "additionalProperties": False,
    }


def _goal_schema(context: dict[str, object]) -> dict[str, Any]:
    leaf_condition: dict[str, Any] = {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": [
                    "eq",
                    "ne",
                    "lt",
                    "lte",
                    "gt",
                    "gte",
                    "exists",
                    "changed",
                    "count",
                    "duration",
                    "within",
                ],
            },
            "path": {"type": "string", "maxLength": 300},
            "value": {"type": ["string", "number", "boolean", "null"]},
            "unit": {"type": ["string", "null"], "maxLength": 100},
            "children": {"type": "array", "maxItems": 0},
            "window_seconds": {"type": ["number", "null"], "minimum": 0},
            "duration_seconds": {"type": ["number", "null"], "minimum": 0},
            "count": {"type": ["integer", "null"], "minimum": 0},
        },
        "required": ["op", "path", "value", "unit", "children"],
        "additionalProperties": False,
    }
    condition: dict[str, Any] = {
        "anyOf": [
            leaf_condition,
            {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": ["all", "any", "not"]},
                    "path": {"type": "null"},
                    "value": {"type": "null"},
                    "unit": {"type": "null"},
                    "children": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 4,
                        "items": leaf_condition,
                    },
                },
                "required": ["op", "path", "value", "unit", "children"],
                "additionalProperties": False,
            },
        ]
    }
    string_ids = {
        "type": "array",
        "minItems": 1,
        "maxItems": 16,
        "uniqueItems": True,
        "items": {"type": "string", "maxLength": 300},
    }
    entity_scope: dict[str, Any] = {
        "type": "object",
        "properties": {"target_ids": string_ids, "entity_ids": string_ids},
        "required": ["target_ids"],
        "additionalProperties": False,
    }
    entity_selector: dict[str, Any] = {
        "type": "object",
        "properties": {"target_ids": string_ids, "entity_ids": string_ids},
        "required": ["entity_ids"],
        "additionalProperties": False,
    }
    capability_family: dict[str, Any] = {
        "type": "string",
        "maxLength": 300,
    }
    parameters: dict[str, Any] = {"type": "object", "maxProperties": 16}
    max_effects = 4
    selection = context.get("required_selection")
    if isinstance(selection, dict):
        target_id = selection.get("target_id")
        entity_id = selection.get("entity_id")
        family = selection.get("capability_family")
        effect_schema = selection.get("effect_schema")
        if all(isinstance(item, str) and item for item in (target_id, entity_id, family)):
            entity_scope = {"const": {"target_ids": [target_id]}}
            entity_selector = {"const": {"entity_ids": [entity_id]}}
            capability_family = {"const": family}
            max_effects = 1
            measurements = selection.get("effect_measurements")
            if (
                isinstance(measurements, list)
                and measurements
                and all(isinstance(item, str) for item in measurements)
            ):
                leaf_condition["properties"]["path"] = {
                    "enum": [f"observation:{item}" for item in measurements]
                }
                if len(measurements) == 1:
                    condition = leaf_condition
                    measurement_units = selection.get("measurement_units")
                    if isinstance(measurement_units, dict):
                        unit = measurement_units.get(measurements[0])
                        if isinstance(unit, str) and unit:
                            leaf_condition["properties"]["unit"] = {
                                "type": ["string", "null"],
                                "const": unit,
                            }
        if isinstance(effect_schema, dict):
            parameters = effect_schema
    return {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["achieve", "maintain"]},
            "entity_scope": entity_scope,
            "desired_effects": {
                "type": "array",
                "minItems": 1,
                "maxItems": max_effects,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "minLength": 1, "maxLength": 200},
                        "capability_family": capability_family,
                        "entity_selector": entity_selector,
                        "condition": condition,
                        "parameters": parameters,
                        "description": {"type": "string", "maxLength": 500},
                    },
                    "required": [
                        "id",
                        "capability_family",
                        "entity_selector",
                        "condition",
                        "parameters",
                        "description",
                    ],
                    "additionalProperties": False,
                },
            },
            "constraints": {
                "type": "array",
                "maxItems": 8,
                "items": condition,
            },
            "budgets": {
                "type": "object",
                "maxProperties": 8,
                "additionalProperties": {
                    "type": ["string", "number", "boolean", "null"]
                },
            },
            "stop_conditions": {
                "type": "array",
                "maxItems": 8,
                "items": condition,
            },
            "priority": {"type": "integer", "minimum": -100, "maximum": 100},
        },
        "required": [
            "mode",
            "entity_scope",
            "desired_effects",
            "constraints",
            "budgets",
            "stop_conditions",
            "priority",
        ],
        "additionalProperties": False,
    }
