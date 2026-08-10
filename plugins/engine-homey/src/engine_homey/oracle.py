from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .charter import effective_desired


class ObligationStatus(StrEnum):
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class OracleResult:
    satisfied: bool | None
    obligations: tuple[dict[str, Any], ...]


class HomeOracle:
    """Deterministic sensor oracle; ACKs and model claims are never inputs."""

    def evaluate(
        self, state: dict[str, Any], charter: dict[str, Any] | None
    ) -> OracleResult:
        if charter is None:
            return OracleResult(None, ())
        zones = [str(item["alias"]) for item in state.get("zones", [])]
        obligations: list[dict[str, Any]] = []
        for rule in sorted(
            charter.get("rules", []),
            key=lambda item: (-int(item["priority"]), item["id"]),
        ):
            scope = rule["scope"]["zones"]
            selected = (
                zones if scope == "*" else [zone for zone in zones if zone in scope]
            )
            if rule["domain"] == "energy":
                obligations.append(self._energy(state, charter, rule))
                continue
            if not selected:
                obligations.append(
                    {
                        "id": f"{rule['id']}:scope",
                        "rule_id": rule["id"],
                        "domain": rule["domain"],
                        "zone": "*",
                        "priority": rule["priority"],
                        "desired": rule["desired"],
                        "conditions": [],
                        "allowed_device_aliases": rule.get("scope", {}).get(
                            "device_aliases"
                        ),
                        "active": None,
                        "status": ObligationStatus.UNKNOWN.value,
                        "reason": "charter scope contains no observed zones",
                    }
                )
                continue
            for zone in selected:
                obligations.append(self._zone_obligation(state, charter, rule, zone))
        statuses = {item["status"] for item in obligations}
        if ObligationStatus.UNKNOWN.value in statuses:
            satisfied: bool | None = None
        elif ObligationStatus.VIOLATED.value in statuses:
            satisfied = False
        else:
            satisfied = True
        return OracleResult(satisfied, tuple(obligations))

    def _zone_obligation(
        self,
        state: dict[str, Any],
        charter: dict[str, Any],
        rule: dict[str, Any],
        zone: str,
    ) -> dict[str, Any]:
        allowed = rule.get("scope", {}).get("device_aliases")
        signals = _signals(
            state,
            zone,
            allowed=set(allowed) if isinstance(allowed, list) else None,
        )
        condition_values: list[bool | None] = []
        condition_evidence: list[dict[str, Any]] = []
        for condition in rule["conditions"]:
            result, evidence = _condition(condition, signals)
            condition_values.append(result)
            condition_evidence.append(evidence)
        desired = effective_desired(
            charter,
            rule,
            zone=zone,
            observed_at=datetime.now(UTC).isoformat(),
            active_preference_ids=set(state.get("active_preference_ids", [])),
        )
        base = {
            "id": f"{rule['id']}:{zone}",
            "rule_id": rule["id"],
            "domain": rule["domain"],
            "zone": zone,
            "priority": rule["priority"],
            "desired": desired,
            "conditions": condition_evidence,
            "allowed_device_aliases": sorted(allowed)
            if isinstance(allowed, list)
            else None,
        }
        if any(value is None for value in condition_values):
            return {
                **base,
                "active": None,
                "status": ObligationStatus.UNKNOWN.value,
                "reason": "required condition evidence is missing, stale or unavailable",
            }
        active = all(value is True for value in condition_values)
        if rule["domain"] == "lighting":
            return self._lighting(base, signals, desired, active, condition_values)
        if not active:
            return {
                **base,
                "active": False,
                "status": ObligationStatus.SATISFIED.value,
                "reason": "rule conditions are inactive",
            }
        if rule["domain"] == "climate":
            maximum = float(desired["temperature_c"]["max"])
            temperature = signals.get("temperature_c")
            if temperature is None:
                return _unknown(base, "temperature evidence is unavailable")
            okay = float(temperature) <= maximum
            return _checked(base, okay, "observed temperature", active=True)
        return {
            **base,
            "active": active,
            "status": ObligationStatus.SATISFIED.value,
            "reason": "presence context is observed",
        }

    def _lighting(
        self,
        base: dict[str, Any],
        signals: dict[str, Any],
        desired: dict[str, Any],
        active: bool,
        condition_values: list[bool | None],
    ) -> dict[str, Any]:
        # If recent presence is known false, the data charter's vacant state is
        # authoritative. Darkness alone never turns an occupied zone off.
        presence_false = bool(condition_values) and condition_values[0] is False
        if not active and not presence_false:
            return {
                **base,
                "active": False,
                "status": ObligationStatus.SATISFIED.value,
                "reason": "lighting rule conditions are inactive",
            }
        light_states = signals.get("light_on")
        if light_states is None:
            return _unknown(base, "configured light state is unavailable")
        if presence_false:
            desired_off = desired.get("vacant_light", {}).get("on") is False
            okay = not any(light_states) if desired_off else True
            return _checked(base, okay, "observed vacant-zone light state", active=True)

        lux = signals.get("illuminance_lux")
        power = signals.get("power_w")
        if lux is None:
            return _unknown(base, "illuminance evidence is unavailable")
        if power is None:
            return _unknown(base, "power evidence is unavailable")
        band = desired["illuminance_lux"]
        watt_limit = float(desired["power_w"]["max"])
        okay = (
            float(band["min"]) <= float(lux) <= float(band["max"])
            and float(power) <= watt_limit
            and any(light_states)
        )
        return _checked(
            base,
            okay,
            "observed lux, power and light state",
            active=True,
            observations={"illuminance_lux": lux, "power_w": power},
        )

    def _energy(
        self, state: dict[str, Any], charter: dict[str, Any], rule: dict[str, Any]
    ) -> dict[str, Any]:
        desired = effective_desired(
            charter,
            rule,
            zone="*",
            observed_at=datetime.now(UTC).isoformat(),
            active_preference_ids=set(state.get("active_preference_ids", [])),
        )
        devices = list(state.get("devices", []))
        meters = [
            item
            for item in devices
            if item.get("kind") in {"meter", "energy_meter", "smart_meter"}
        ]
        readings = _capability_values(
            {
                "devices": meters
                if _capability_values({"devices": meters}, "power_w")
                else devices
            },
            "power_w",
        )
        base = {
            "id": str(rule["id"]),
            "rule_id": rule["id"],
            "domain": "energy",
            "zone": "*",
            "priority": rule["priority"],
            "desired": desired,
            "conditions": [],
        }
        if not readings:
            return _unknown(base, "house power evidence is unavailable")
        total = sum(float(value) for value in readings)
        maximum = float(desired["house_power_w"]["max"])
        active = total > maximum
        return _checked(
            base,
            not active,
            "observed house power",
            active=active,
            observations={"house_power_w": total},
        )


def _signals(
    state: dict[str, Any], zone: str, *, allowed: set[str] | None = None
) -> dict[str, Any]:
    devices = [
        item
        for item in state.get("devices", [])
        if item.get("zone_alias") == zone
        and item.get("available") is not False
        and (
            allowed is None
            or item.get("alias") in allowed
            or not item.get("control_allowed")
        )
    ]
    result: dict[str, Any] = {}
    for semantic, aggregate in (
        ("illuminance_lux", "mean"),
        ("temperature_c", "mean"),
        ("power_w", "sum"),
    ):
        values = _capability_values({"devices": devices}, semantic)
        if values:
            result[semantic] = (
                sum(float(value) for value in values)
                if aggregate == "sum"
                else sum(float(value) for value in values) / len(values)
            )
    presence_caps = _capabilities(devices, "presence")
    if presence_caps:
        result["presence"] = presence_caps
    lights = [item for item in devices if item.get("kind") == "light"]
    on_values: list[bool] = []
    for device in lights:
        capability = next(
            (
                item
                for item in device.get("capabilities", [])
                if item.get("semantic") == "on"
                and item.get("evidence") == "OBSERVED"
                and type(item.get("value")) is bool
            ),
            None,
        )
        if capability is not None:
            on_values.append(bool(capability["value"]))
    if lights and len(on_values) == len(lights):
        result["light_on"] = on_values
    return result


def _condition(
    condition: dict[str, Any], signals: dict[str, Any]
) -> tuple[bool | None, dict[str, Any]]:
    signal = str(condition["signal"])
    operator = str(condition["operator"])
    if signal == "presence":
        capabilities = signals.get("presence")
        if not capabilities:
            return None, {"signal": signal, "result": "UNKNOWN"}
        if operator == "recent_true":
            within = int(condition["within_seconds"])
            now = datetime.now(UTC)
            saw_known = False
            for item in capabilities:
                if type(item.get("value")) is not bool:
                    continue
                saw_known = True
                if item["value"] is not True:
                    continue
                timestamp = _timestamp(item.get("observed_at"))
                if timestamp is None:
                    return None, {"signal": signal, "result": "UNKNOWN"}
                if (now - timestamp).total_seconds() <= within:
                    return True, {
                        "signal": signal,
                        "result": True,
                        "within_seconds": within,
                    }
            return (False if saw_known else None), {
                "signal": signal,
                "result": False if saw_known else "UNKNOWN",
                "within_seconds": within,
            }
        values = [item.get("value") for item in capabilities]
        return any(value is True for value in values), {
            "signal": signal,
            "result": any(value is True for value in values),
        }
    value = signals.get(signal)
    if value is None:
        return None, {"signal": signal, "result": "UNKNOWN"}
    expected = condition.get("value")
    result = {
        "lt": value < expected,
        "lte": value <= expected,
        "gt": value > expected,
        "gte": value >= expected,
        "true": value is True,
    }.get(operator)
    return result, {"signal": signal, "value": value, "result": result}


def _capabilities(devices: list[dict[str, Any]], semantic: str) -> list[dict[str, Any]]:
    return [
        capability
        for device in devices
        for capability in device.get("capabilities", [])
        if capability.get("semantic") == semantic
        and capability.get("evidence") == "OBSERVED"
    ]


def _capability_values(state: dict[str, Any], semantic: str) -> list[float]:
    values: list[float] = []
    for capability in _capabilities(list(state.get("devices", [])), semantic):
        value = capability.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return values


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _unknown(base: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        **base,
        "active": None,
        "status": ObligationStatus.UNKNOWN.value,
        "reason": reason,
    }


def _checked(
    base: dict[str, Any],
    okay: bool,
    reason: str,
    *,
    active: bool,
    observations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = {
        **base,
        "active": active,
        "status": (
            ObligationStatus.SATISFIED.value
            if okay
            else ObligationStatus.VIOLATED.value
        ),
        "reason": reason,
    }
    if observations:
        value["observations"] = observations
    return value
