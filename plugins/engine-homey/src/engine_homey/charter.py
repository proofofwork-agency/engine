from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from .config import DeviceBinding
from .store import HomeOpsStore


class CharterError(ValueError):
    pass


HOME_CHARTER_V1_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "engine.homey.home-charter/v1",
    "type": "object",
    "required": [
        "schema",
        "version_id",
        "created_at",
        "source_sha256",
        "conflict_resolution",
        "rules",
    ],
    "properties": {
        "schema": {"const": "engine.homey.home-charter/v1"},
        "version_id": {"type": "string", "minLength": 16},
        "created_at": {"type": "string", "format": "date-time"},
        "source_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "conflict_resolution": {
            "type": "array",
            "items": {"enum": ["safety", "quiet", "comfort", "energy"]},
            "minItems": 4,
            "maxItems": 4,
            "uniqueItems": True,
        },
        "rules": {
            "type": "array",
            "items": {"$ref": "#/$defs/rule"},
            "minItems": 1,
        },
        "preferences": {
            "type": "array",
            "items": {"$ref": "#/$defs/preference"},
        },
    },
    "additionalProperties": False,
    "$defs": {
        "scope": {
            "type": "object",
            "required": ["zones"],
            "properties": {
                "zones": {
                    "oneOf": [
                        {"const": "*"},
                        {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "uniqueItems": True,
                        },
                    ]
                },
                "device_aliases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "uniqueItems": True,
                },
            },
            "additionalProperties": False,
        },
        "rule": {
            "type": "object",
            "required": [
                "id",
                "domain",
                "priority",
                "scope",
                "conditions",
                "desired",
                "minimum_duration_seconds",
                "maximum_duration_seconds",
            ],
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "domain": {"enum": ["lighting", "climate", "energy", "presence"]},
                "priority": {"type": "integer"},
                "scope": {"$ref": "#/$defs/scope"},
                "conditions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["signal", "operator"],
                        "properties": {
                            "signal": {"type": "string"},
                            "operator": {
                                "enum": [
                                    "lt",
                                    "lte",
                                    "gt",
                                    "gte",
                                    "true",
                                    "recent_true",
                                ]
                            },
                            "value": {"type": ["number", "boolean", "string"]},
                            "within_seconds": {"type": "integer", "minimum": 1},
                        },
                        "additionalProperties": False,
                    },
                },
                "desired": {"type": "object"},
                "minimum_duration_seconds": {"type": "integer", "minimum": 0},
                "maximum_duration_seconds": {"type": "integer", "minimum": 1},
            },
            "additionalProperties": False,
        },
        "preference": {
            "type": "object",
            "required": ["id", "rule_id", "desired_patch", "source_evidence"],
            "properties": {
                "id": {"type": "string"},
                "rule_id": {"type": "string"},
                "zone": {"type": ["string", "null"]},
                "after": {
                    "type": ["string", "null"],
                    "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$",
                },
                "before": {
                    "type": ["string", "null"],
                    "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$",
                },
                "desired_patch": {"type": "object", "minProperties": 1},
                "source_evidence": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
}


class HomeCharterCompiler:
    """Conservative deterministic baseline for natural-language house policy.

    It compiles common intent and explicit numeric bounds into typed data. It
    never executes the text and refuses an empty or unscoped charter. A future
    model-backed proposal provider can produce the same schema without changing
    storage, evaluation or authority boundaries.
    """

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))

    def compile(
        self,
        text: str,
        *,
        zone_aliases: tuple[str, ...] = (),
        devices: tuple[DeviceBinding, ...] = (),
    ) -> dict[str, Any]:
        source = text.strip()
        if not source:
            raise CharterError("a home charter cannot be empty")
        lowered = source.casefold()
        rules: list[dict[str, Any]] = []
        allowed = [item.alias for item in devices if item.control]
        configured_zones = sorted(set(zone_aliases))
        scope: dict[str, Any] = {
            "zones": configured_zones if configured_zones else "*"
        }
        if allowed:
            scope["device_aliases"] = sorted(allowed)

        if any(word in lowered for word in ("verlicht", "licht", "dark", "donker")):
            lux_min, lux_max = _range(source, "lux", (60.0, 120.0))
            watt_max = _single(source, ("w", "watt"), 20.0)
            brightness_max = _percentage(source, 0.70)
            recent_seconds = _duration_seconds(source, 300)
            rules.append(
                {
                    "id": "lighting.used-zone-dark/v1",
                    "domain": "lighting",
                    "priority": 70,
                    "scope": deepcopy(scope),
                    "conditions": [
                        {
                            "signal": "presence",
                            "operator": "recent_true",
                            "within_seconds": recent_seconds,
                        },
                        {
                            "signal": "illuminance_lux",
                            "operator": "lt",
                            "value": lux_min,
                        },
                    ],
                    "desired": {
                        "illuminance_lux": {"min": lux_min, "max": lux_max},
                        "power_w": {"max": watt_max},
                        "light": {"on": True, "brightness_max": brightness_max},
                        "vacant_light": {"on": False},
                    },
                    "minimum_duration_seconds": 30,
                    "maximum_duration_seconds": max(300, recent_seconds),
                }
            )

        if any(
            word in lowered
            for word in ("koeling", "koel", "cooling", "temperatuur", "verwarming")
        ):
            temperature_max = _temperature(source, 25.0)
            rules.append(
                {
                    "id": "climate.passive-before-active/v1",
                    "domain": "climate",
                    "priority": 60,
                    "scope": deepcopy(scope),
                    "conditions": [
                        {
                            "signal": "temperature_c",
                            "operator": "gt",
                            "value": temperature_max,
                        }
                    ],
                    "desired": {
                        "temperature_c": {"max": temperature_max},
                        "strategy_order": ["cover", "thermostat"],
                        "thermostat_target_c": temperature_max - 1.0,
                    },
                    "minimum_duration_seconds": 300,
                    "maximum_duration_seconds": 3600,
                }
            )

        if any(word in lowered for word in ("energie", "energy", "verbruik", "watt")):
            total_watt_max = _explicit_total_watts(source, 2500.0)
            rules.append(
                {
                    "id": "energy.house-budget/v1",
                    "domain": "energy",
                    "priority": 50,
                    "scope": deepcopy(scope),
                    "conditions": [
                        {
                            "signal": "house_power_w",
                            "operator": "gt",
                            "value": total_watt_max,
                        }
                    ],
                    "desired": {"house_power_w": {"max": total_watt_max}},
                    "minimum_duration_seconds": 10,
                    "maximum_duration_seconds": 900,
                }
            )

        if not rules:
            raise CharterError(
                "charter has no supported typed domain; mention lighting/darkness, "
                "climate/temperature or energy/power"
            )
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        material = json.dumps(rules, sort_keys=True, separators=(",", ":"))
        version_id = (
            "charter_"
            + hashlib.sha256(
                f"{source_hash}:{material}:{self._clock().isoformat()}".encode()
            ).hexdigest()[:24]
        )
        charter = {
            "schema": "engine.homey.home-charter/v1",
            "version_id": version_id,
            "created_at": self._clock().isoformat(),
            "source_sha256": source_hash,
            "conflict_resolution": ["safety", "quiet", "comfort", "energy"],
            "rules": rules,
            "preferences": [],
        }
        validate_charter(charter)
        return charter


class PreferenceLearner:
    """Turns explicit corrections into auditable typed charter patches."""

    def __init__(
        self,
        store: HomeOpsStore,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self._clock = clock or (lambda: datetime.now(UTC))

    def apply_correction(
        self,
        text: str,
        *,
        zone: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        charter = self.store.active_charter()
        if charter is None:
            raise CharterError("compile a charter before applying corrections")
        lowered = text.casefold()
        if not any(word in lowered for word in ("fel", "donker", "bright", "dim")):
            raise CharterError(
                "correction does not identify a supported lighting preference"
            )
        rule = next(
            (item for item in charter["rules"] if item["domain"] == "lighting"),
            None,
        )
        if rule is None:
            raise CharterError("active charter has no lighting rule")
        old_max = float(rule["desired"]["light"]["brightness_max"])
        explicit = _optional_percentage(text)
        if explicit is not None:
            new_max = explicit
        elif "fel" in lowered or "bright" in lowered:
            observed = _context_number(context, "brightness")
            new_max = min(old_max, observed if observed is not None else old_max * 0.75)
        else:
            observed = _context_number(context, "brightness")
            new_max = max(old_max, observed if observed is not None else old_max + 0.15)
        new_max = round(min(1.0, max(0.01, new_max)), 3)
        after = _time(text, "na|after")
        before = _time(text, "voor|before")
        evidence_context = dict(context or {})
        if zone is not None:
            evidence_context["zone"] = zone
        before_version = str(charter["version_id"])
        placeholder_id = "pending"
        preference = {
            "id": "preference_"
            + hashlib.sha256(
                f"{text}:{zone}:{self._clock().isoformat()}".encode()
            ).hexdigest()[:20],
            "rule_id": str(rule["id"]),
            "zone": zone,
            "after": after,
            "before": before,
            "desired_patch": {"light": {"brightness_max": new_max}},
            "source_evidence": placeholder_id,
        }
        new_charter = deepcopy(charter)
        new_charter["created_at"] = self._clock().isoformat()
        new_charter["version_id"] = (
            "charter_"
            + hashlib.sha256(
                json.dumps(
                    {"parent": before_version, "preference": preference},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:24]
        )
        new_charter.setdefault("preferences", []).append(preference)
        patch = {
            "op": "add",
            "path": "/preferences/-",
            "old_brightness_max": old_max,
            "new_brightness_max": new_max,
            "zone": zone,
            "after": after,
            "before": before,
        }
        evidence_id = self.store.record_preference(
            grade="OBSERVED",
            source="direct_user_correction",
            text=text,
            context=evidence_context,
            charter_before=before_version,
            charter_after=str(new_charter["version_id"]),
            patch=patch,
        )
        preference["source_evidence"] = evidence_id
        new_charter["preferences"][-1] = preference
        validate_charter(new_charter)
        source = self.store.charter_source(before_version)
        self.store.save_charter(new_charter, source, parent_version_id=before_version)
        return {"evidence_id": evidence_id, "patch": patch, "charter": new_charter}

    def record_manual_override(self, context: dict[str, Any]) -> str:
        charter = self.store.active_charter()
        return self.store.record_preference(
            grade="INFERRED",
            source="manual_homey_override",
            text=None,
            context=context,
            charter_before=(str(charter["version_id"]) if charter else None),
        )


def validate_charter(charter: dict[str, Any]) -> None:
    try:
        Draft202012Validator(HOME_CHARTER_V1_SCHEMA).validate(charter)
    except ValidationError as error:
        raise CharterError(f"invalid HomeCharterV1: {error.message}") from error


def effective_desired(
    charter: dict[str, Any],
    rule: dict[str, Any],
    *,
    zone: str,
    observed_at: str,
    active_preference_ids: set[str] | None = None,
) -> dict[str, Any]:
    desired = deepcopy(rule["desired"])
    local_time = _parse_datetime(observed_at).astimezone().strftime("%H:%M")
    for preference in charter.get("preferences", []):
        if preference.get("rule_id") != rule.get("id"):
            continue
        if preference.get("zone") not in {None, zone}:
            continue
        if active_preference_ids is not None:
            active = str(preference["id"]) in active_preference_ids
        else:
            active = _preference_time_active(preference, local_time)
        if not active:
            continue
        desired = _deep_merge(desired, preference["desired_patch"])
    return desired


def active_preference_ids(
    charter: dict[str, Any], observed_at: datetime
) -> tuple[str, ...]:
    local_time = observed_at.astimezone().strftime("%H:%M")
    return tuple(
        sorted(
            str(preference["id"])
            for preference in charter.get("preferences", [])
            if _preference_time_active(preference, local_time)
        )
    )


def _preference_time_active(preference: dict[str, Any], local_time: str) -> bool:
    after = preference.get("after")
    before = preference.get("before")
    if after is not None and before is not None and after > before:
        return local_time >= after or local_time < before
    if after is not None and local_time < after:
        return False
    return before is None or local_time < before


def _deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(UTC)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _range(text: str, unit: str, default: tuple[float, float]) -> tuple[float, float]:
    match = re.search(
        rf"(?:tussen\s+|between\s+)?(\d+(?:[.,]\d+)?)\s*(?:-|–|tot|to|en|and)\s*(\d+(?:[.,]\d+)?)\s*{unit}\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return default
    low, high = (_number(match.group(1)), _number(match.group(2)))
    if low >= high:
        raise CharterError(f"invalid {unit} range")
    return low, high


def _single(text: str, units: tuple[str, ...], default: float) -> float:
    unit = "|".join(re.escape(value) for value in units)
    match = re.search(
        rf"(?:onder|max(?:imaal)?|<=)\s*(\d+(?:[.,]\d+)?)\s*(?:{unit})\b",
        text,
        re.IGNORECASE,
    )
    return _number(match.group(1)) if match else default


def _explicit_total_watts(text: str, default: float) -> float:
    match = re.search(
        r"(?:huis|totaal|house|total)[^.!?]{0,30}?(\d+(?:[.,]\d+)?)\s*(?:w|watt)\b",
        text,
        re.IGNORECASE,
    )
    return _number(match.group(1)) if match else default


def _temperature(text: str, default: float) -> float:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:°\s*)?[cC]\b", text)
    return _number(match.group(1)) if match else default


def _percentage(text: str, default: float) -> float:
    value = _optional_percentage(text)
    return value if value is not None else default


def _optional_percentage(text: str) -> float | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    if not match:
        return None
    value = _number(match.group(1)) / 100.0
    if not 0 < value <= 1:
        raise CharterError("brightness percentage must be in (0, 100]")
    return value


def _duration_seconds(text: str, default: int) -> int:
    match = re.search(
        r"(\d+)\s*(seconden?|seconds?|minuten?|minutes?)\b", text, re.IGNORECASE
    )
    if not match:
        return default
    value = int(match.group(1))
    return value * 60 if match.group(2).casefold().startswith(("min",)) else value


def _time(text: str, prefix: str) -> str | None:
    match = re.search(
        rf"\b(?:{prefix})\s+([01]?\d|2[0-3]):([0-5]\d)\b", text, re.IGNORECASE
    )
    return f"{int(match.group(1)):02d}:{match.group(2)}" if match else None


def _context_number(context: dict[str, Any] | None, key: str) -> float | None:
    if not context or key not in context or isinstance(context[key], bool):
        return None
    try:
        return float(context[key])
    except (TypeError, ValueError):
        return None


def _number(value: str) -> float:
    return float(value.replace(",", "."))
