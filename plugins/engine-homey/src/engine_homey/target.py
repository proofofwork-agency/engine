from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from .contracts import (
    Affordance,
    CapabilitySpec,
    TargetManifest,
    ToolCall,
    ToolResult,
    WorldSnapshot,
)

from .charter import active_preference_ids
from .config import DeviceBinding, HomeyConfig
from .oracle import HomeOracle
from .store import HomeOpsStore
from .transport import EventSource, HomeyTransport, NullEventSource

SET_LIGHT = "engine.homey.set-light/v1"
SET_SWITCH = "engine.homey.set-switch/v1"
SET_COVER = "engine.homey.set-cover/v1"
SET_THERMOSTAT = "engine.homey.set-thermostat-target/v1"


class HomeyTarget:
    """One Homey Pro projected as a typed whole-house Engine target."""

    def __init__(
        self,
        config: HomeyConfig,
        store: HomeOpsStore,
        transport: HomeyTransport,
        *,
        event_source: EventSource | None = None,
        oracle: HomeOracle | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.transport = transport
        self.event_source = event_source or NullEventSource()
        self.oracle = oracle or HomeOracle()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._last_state: dict[str, Any] | None = None
        self._last_observed_monotonic: float | None = None
        self._suppress_override_detection_once = False
        self.manifest = TargetManifest(
            id=config.target_id,
            description="Whole-house Homey Pro target",
            plugin_id="engine.homey",
            adapter_version="0.1.0",
        )

    def capabilities(self) -> tuple[CapabilitySpec, ...]:
        specs: list[CapabilitySpec] = []
        lights = self._bindings("light", required=("onoff",))
        if lights:
            specs.append(
                CapabilitySpec(
                    id=SET_LIGHT,
                    local_name="set-light",
                    description="Set an allowlisted Homey light by stable alias",
                    input_schema=_light_schema(lights),
                    output_schema=_mutation_output_schema(),
                    affordance=Affordance.ACTION,
                    idempotent=True,
                    default_timeout_ms=int(self.config.timeout_seconds * 1000),
                )
            )
        switches = tuple(
            item
            for item in self.config.devices
            if item.kind in {"switch", "plug", "socket", "device"}
            and item.capability("on", "onoff") in item.control
        )
        if switches:
            specs.append(
                CapabilitySpec(
                    id=SET_SWITCH,
                    local_name="set-switch",
                    description="Set an allowlisted Homey switch by stable alias",
                    input_schema=_alias_value_schema(
                        switches, "on", {"type": "boolean"}
                    ),
                    output_schema=_mutation_output_schema(),
                    affordance=Affordance.ACTION,
                    idempotent=True,
                    default_timeout_ms=int(self.config.timeout_seconds * 1000),
                )
            )
        covers = tuple(
            item
            for item in self.config.devices
            if item.kind in {"cover", "blind", "curtain"}
            and item.capability("position", "windowcoverings_set") in item.control
        )
        if covers:
            specs.append(
                CapabilitySpec(
                    id=SET_COVER,
                    local_name="set-cover",
                    description="Set an allowlisted cover position (0 closed, 1 open)",
                    input_schema=_bounded_alias_schema(covers, "position", (0.0, 1.0)),
                    output_schema=_mutation_output_schema(),
                    affordance=Affordance.ACTION,
                    idempotent=True,
                    default_timeout_ms=int(self.config.timeout_seconds * 1000),
                )
            )
        thermostats = tuple(
            item
            for item in self.config.devices
            if item.kind in {"thermostat", "climate"}
            and item.capability("target", "target_temperature") in item.control
        )
        if thermostats:
            specs.append(
                CapabilitySpec(
                    id=SET_THERMOSTAT,
                    local_name="set-thermostat-target",
                    description="Set an allowlisted thermostat target in degrees Celsius",
                    input_schema=_bounded_alias_schema(
                        thermostats,
                        "temperature_c",
                        (5.0, 35.0),
                        limit_name="temperature_c",
                    ),
                    output_schema=_mutation_output_schema(),
                    affordance=Affordance.ACTION,
                    idempotent=True,
                    default_timeout_ms=int(self.config.timeout_seconds * 1000),
                )
            )
        return tuple(specs)

    def observe(self) -> WorldSnapshot:
        previous = self._last_state
        if previous is None:
            stored_previous = self.store.latest_snapshot()
            previous = stored_previous.state if stored_previous is not None else None
        suppress_override_detection = self._suppress_override_detection_once
        # No dispatch may rely on the previous snapshot while a refresh is in
        # progress or after any part of observation/persistence fails.
        self._last_observed_monotonic = None
        try:
            state, observed_at = self._fresh_state()
        finally:
            # Consume dispatch reconciliation on the first observation attempt,
            # including a failed read. Otherwise an unrelated later change could
            # be hidden indefinitely after a disconnect or lost acknowledgement.
            if suppress_override_detection:
                self._suppress_override_detection_once = False
        if not suppress_override_detection and previous is not None:
            changes = _controlled_changes(previous, state)
            if changes:
                charter = self.store.active_charter()
                self.store.record_preference(
                    grade="INFERRED",
                    source="unattributed_control_change_detected",
                    text=None,
                    context={"changes": changes, "snapshot_observed_at": observed_at},
                    charter_before=(
                        str(charter["version_id"]) if charter is not None else None
                    ),
                )
        stored = self.store.record_snapshot(state, observed_at)
        self._last_state = state
        self._last_observed_monotonic = time.monotonic()
        return WorldSnapshot(
            target_id=self.manifest.id,
            revision=stored.revision,
            state=state,
            observed_at=observed_at,
        )

    def execute(self, call: ToolCall) -> ToolResult:
        if call.target_id not in {None, self.manifest.id}:
            return ToolResult(False, False, error="target binding mismatch")
        if self.config.mode != "act":
            return ToolResult(False, False, error="DENY: ENGINE_HOMEY_MODE is observe")
        if not self.config.armed:
            return ToolResult(False, False, error="DENY: ENGINE_HOMEY_ARMED is not 1")
        if (
            self._last_observed_monotonic is None
            or time.monotonic() - self._last_observed_monotonic
            > self.config.max_snapshot_age_seconds
        ):
            return ToolResult(
                False,
                False,
                error="DENY: no fresh Homey observation is bound to this dispatch",
            )
        try:
            binding = self.config.device_by_alias[str(call.arguments["alias"])]
        except (KeyError, TypeError):
            return ToolResult(
                False, False, error="DENY: device alias is not allowlisted"
            )
        writes_or_error = self._writes(call, binding)
        if isinstance(writes_or_error, str):
            return ToolResult(False, False, error=writes_or_error)
        writes = writes_or_error
        if not writes:
            return ToolResult(False, False, error="mutation has no values")
        observed_device = self._observed_device(self._last_state, binding.alias)
        if observed_device is None or observed_device.get("available") is not True:
            return ToolResult(
                False,
                False,
                error="DENY: device is not freshly observed as available",
            )
        for capability_id, _ in writes:
            observed_capability = self._observed_capability(
                self._last_state, binding.alias, capability_id
            )
            if (
                observed_capability is None
                or observed_capability.get("evidence") != "OBSERVED"
                or observed_capability.get("controllable") is not True
            ):
                return ToolResult(
                    False,
                    False,
                    error=(
                        "DENY: allowlisted capability is not freshly observed as "
                        "controllable"
                    ),
                )
        pre_values = {
            capability: self._observed_value(
                self._last_state, binding.alias, capability
            )
            for capability, _ in writes
        }
        acknowledgements: list[dict[str, Any]] = []
        self._suppress_override_detection_once = True
        # Dispatch can change reality even when its acknowledgement is lost.
        # The pre-dispatch snapshot must not authorize a subsequent mutation.
        self._last_observed_monotonic = None
        for capability_id, value in writes:
            # Transport exceptions intentionally escape. Heart records UNKNOWN and
            # performs its own post-observation; the adapter never retries a lost ACK.
            response = self.transport.set_capability(binding.id, capability_id, value)
            acknowledgements.append(
                {
                    "capability_id": capability_id,
                    "acknowledged": True,
                    "response": bool(response),
                }
            )

        verified_state, observed_at = self._fresh_state()
        stored = self.store.record_snapshot(verified_state, observed_at)
        del stored
        self._last_state = verified_state
        self._last_observed_monotonic = time.monotonic()
        self._suppress_override_detection_once = False
        verification = [
            {
                "capability_id": capability_id,
                "requested": value,
                "observed": self._observed_value(
                    verified_state, binding.alias, capability_id
                ),
            }
            for capability_id, value in writes
        ]
        matches = all(
            _same(item["requested"], item["observed"]) for item in verification
        )
        changed = any(
            not _same(pre_values[capability_id], value)
            and _same(
                value,
                self._observed_value(verified_state, binding.alias, capability_id),
            )
            for capability_id, value in writes
        )
        output = {
            "alias": binding.alias,
            "acknowledged": bool(acknowledgements),
            "verified": matches,
            "writes": verification,
        }
        if not matches:
            return ToolResult(
                False,
                changed,
                output=output,
                error="ACK_WITHOUT_OBSERVED_EFFECT: commanded capability did not match fresh read",
                partial=changed,
            )
        return ToolResult(True, changed, output=output)

    def goal_satisfied(self, goal: Any, snapshot: WorldSnapshot) -> bool:
        if goal.target_id != self.manifest.id:
            raise ValueError("goal is bound to another target")
        result = self.oracle.evaluate(snapshot.state, self.store.active_charter())
        if result.satisfied is None:
            raise RuntimeError("HomeOracle lacks complete evidence")
        return result.satisfied

    def goal_relevant_change(
        self, goal: Any, previous: WorldSnapshot, current: WorldSnapshot
    ) -> bool:
        del goal
        return previous.state.get("obligations") != current.state.get("obligations")

    def subscribe(self, callback: Callable[[object], None]) -> Callable[[], None]:
        # Discover subscription identities, but never treat event payloads as
        # state. If this read or Socket.IO setup fails, LiveEngine records the
        # subscription failure and its polling path remains authoritative.
        _, raw_devices = self.transport.read_house()
        device_ids = tuple(
            sorted(
                str(raw.get("id", fallback_id))
                for fallback_id, raw in raw_devices.items()
                if isinstance(raw, dict)
            )
        )
        return self.event_source.subscribe(device_ids, callback)

    def _fresh_state(self) -> tuple[dict[str, Any], str]:
        boundary = self._clock()
        observed_at = boundary.isoformat()
        raw_zones, raw_devices = self.transport.read_house()
        state = self._project(raw_zones, raw_devices)
        charter = self.store.active_charter()
        state["active_preference_ids"] = (
            list(active_preference_ids(charter, boundary)) if charter else []
        )
        oracle_result = self.oracle.evaluate(state, charter)
        state["obligations"] = list(oracle_result.obligations)
        state["oracle"] = {
            "grade": "DERIVED",
            "satisfied": oracle_result.satisfied,
            "charter_version": charter.get("version_id") if charter else None,
        }
        return state, observed_at

    def _project(
        self, raw_zones: dict[str, Any], raw_devices: dict[str, Any]
    ) -> dict[str, Any]:
        zone_bindings = self.config.zone_by_id
        zones_by_id: dict[str, dict[str, Any]] = {}
        for fallback_id, raw in sorted(raw_zones.items()):
            if not isinstance(raw, dict):
                continue
            zone_id = str(raw.get("id", fallback_id))
            name = str(raw.get("name", zone_id))
            fixed = zone_bindings.get(zone_id)
            alias = self.store.alias_for(
                "zone", zone_id, name, fixed=fixed.alias if fixed else None
            )
            zones_by_id[zone_id] = {
                "alias": alias,
                "homey_id": zone_id,
                "name": name,
                "parent_homey_id": (
                    str(raw["parent"]) if raw.get("parent") is not None else None
                ),
            }
        zones: list[dict[str, Any]] = []
        for zone_id, item in sorted(
            zones_by_id.items(), key=lambda pair: pair[1]["alias"]
        ):
            parent_id = item.pop("parent_homey_id")
            item["parent_alias"] = (
                zones_by_id[parent_id]["alias"] if parent_id in zones_by_id else None
            )
            zones.append(item)

        bindings = self.config.device_by_id
        devices: list[dict[str, Any]] = []
        for fallback_id, raw in sorted(raw_devices.items()):
            if not isinstance(raw, dict):
                continue
            device_id = str(raw.get("id", fallback_id))
            binding = bindings.get(device_id)
            raw_zone_id = str(raw["zone"]) if raw.get("zone") is not None else None
            projected_zone = (
                binding.zone
                if binding is not None and binding.zone is not None
                else zones_by_id.get(raw_zone_id or "", {}).get("alias")
            )
            name = str(raw.get("name", device_id))
            suggested = f"{projected_zone or 'unassigned'}_{name}"
            alias = self.store.alias_for(
                "device",
                device_id,
                suggested,
                fixed=binding.alias if binding else None,
            )
            raw_capabilities = raw.get("capabilitiesObj", {})
            if not isinstance(raw_capabilities, dict):
                raw_capabilities = {}
            listed = raw.get("capabilities", [])
            capability_ids = set(raw_capabilities)
            if isinstance(listed, list):
                capability_ids.update(str(item) for item in listed)
            capabilities = [
                self._project_capability(
                    capability_id,
                    raw_capabilities.get(capability_id),
                    binding,
                )
                for capability_id in sorted(capability_ids)
            ]
            devices.append(
                {
                    "alias": alias,
                    "homey_id": device_id,
                    "name": name,
                    "zone_alias": projected_zone,
                    "zone_homey_id": raw_zone_id,
                    "kind": (
                        binding.kind
                        if binding is not None
                        else str(raw.get("class", "device"))
                    ),
                    "available": (
                        raw["available"] if type(raw.get("available")) is bool else None
                    ),
                    "availability_evidence": (
                        "OBSERVED" if type(raw.get("available")) is bool else "UNKNOWN"
                    ),
                    "control_allowed": bool(binding and binding.control),
                    "rated_power_w": binding.rated_power_w if binding else None,
                    "priority": binding.priority if binding else 0,
                    "capabilities": capabilities,
                }
            )
        return {
            "schema": "engine.homey.house-snapshot/v1",
            "target_alias": self.manifest.id,
            "mode": self.config.mode,
            "coverage": {
                "zones": "complete",
                "devices": "complete",
                "capability_values": "reported_by_homey",
            },
            "zones": zones,
            "devices": sorted(devices, key=lambda item: item["alias"]),
        }

    def _project_capability(
        self,
        capability_id: str,
        raw: object,
        binding: DeviceBinding | None,
    ) -> dict[str, Any]:
        value = raw if not isinstance(raw, dict) else raw.get("value")
        details = raw if isinstance(raw, dict) else {}
        value_is_typed = value is None or type(value) in {bool, int, float, str}
        observed = (
            (isinstance(raw, dict) and "value" in details)
            or (raw is not None and not isinstance(raw, dict))
        ) and value_is_typed
        setable = details.get("setable")
        configured = bool(binding and capability_id in binding.control)
        semantic = _semantic(capability_id, binding)
        return {
            "id": capability_id,
            "semantic": semantic,
            "value": value if value_is_typed else None,
            "unit": details.get("units") or _unit(semantic),
            "value_type": details.get("type") or _value_type(value),
            "observed_at": details.get("lastUpdated"),
            "timestamp_evidence": (
                "OBSERVED" if isinstance(details.get("lastUpdated"), str) else "UNKNOWN"
            ),
            "readable": details.get("getable") is not False,
            "control_allowed": configured,
            "controllable": configured and setable is True,
            "evidence": "OBSERVED" if observed else "UNKNOWN",
        }

    def _writes(
        self, call: ToolCall, binding: DeviceBinding
    ) -> list[tuple[str, bool | float | str]] | str:
        arguments = call.arguments
        if call.capability_id == SET_LIGHT and binding.kind == "light":
            writes: list[tuple[str, bool | float | str]] = []
            if "brightness" in arguments:
                error = self._bounded_write(
                    binding,
                    "brightness",
                    "dim",
                    arguments["brightness"],
                    (0.0, 1.0),
                )
                if isinstance(error, str):
                    return error
                writes.append(error)
            if "on" in arguments:
                capability = binding.capability("on", "onoff")
                if capability not in binding.control:
                    return "DENY: light on capability is not allowlisted"
                if type(arguments["on"]) is not bool:
                    return "DENY: on must be a boolean"
                writes.append((capability, arguments["on"]))
            return writes
        if call.capability_id == SET_SWITCH and binding.kind in {
            "switch",
            "plug",
            "socket",
            "device",
        }:
            capability = binding.capability("on", "onoff")
            if (
                capability not in binding.control
                or type(arguments.get("on")) is not bool
            ):
                return "DENY: switch value or capability is outside its allowlist"
            return [(capability, arguments["on"])]
        if call.capability_id == SET_COVER and binding.kind in {
            "cover",
            "blind",
            "curtain",
        }:
            result = self._bounded_write(
                binding,
                "position",
                "windowcoverings_set",
                arguments.get("position"),
                (0.0, 1.0),
            )
            return result if isinstance(result, str) else [result]
        if call.capability_id == SET_THERMOSTAT and binding.kind in {
            "thermostat",
            "climate",
        }:
            result = self._bounded_write(
                binding,
                "temperature_c",
                "target_temperature",
                arguments.get("temperature_c"),
                (5.0, 35.0),
                capability_semantic="target",
            )
            return result if isinstance(result, str) else [result]
        return "DENY: capability is not valid for the configured device kind"

    @staticmethod
    def _observed_value(
        state: dict[str, Any] | None, alias: str, capability_id: str
    ) -> object:
        capability = HomeyTarget._observed_capability(state, alias, capability_id)
        return capability.get("value") if capability is not None else None

    @staticmethod
    def _observed_capability(
        state: dict[str, Any] | None, alias: str, capability_id: str
    ) -> dict[str, Any] | None:
        device = HomeyTarget._observed_device(state, alias)
        if device is None:
            return None
        for capability in device.get("capabilities", []):
            if capability.get("id") == capability_id:
                return capability
        return None

    @staticmethod
    def _observed_device(
        state: dict[str, Any] | None, alias: str
    ) -> dict[str, Any] | None:
        if state is None:
            return None
        for device in state.get("devices", []):
            if device.get("alias") != alias:
                continue
            return device
        return None

    @staticmethod
    def _bounded_write(
        binding: DeviceBinding,
        limit_name: str,
        default_capability: str,
        raw_value: object,
        default_limit: tuple[float, float],
        *,
        capability_semantic: str | None = None,
    ) -> tuple[str, float] | str:
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            return f"DENY: {limit_name} must be numeric"
        value = float(raw_value)
        low, high = binding.limit(limit_name, default_limit)
        if not low <= value <= high:
            return f"DENY: {limit_name} is outside configured [{low}, {high}]"
        capability = binding.capability(
            capability_semantic or limit_name, default_capability
        )
        if capability not in binding.control:
            return f"DENY: {limit_name} capability is not allowlisted"
        return capability, value

    def _bindings(
        self, kind: str, *, required: tuple[str, ...]
    ) -> tuple[DeviceBinding, ...]:
        return tuple(
            item
            for item in self.config.devices
            if item.kind == kind
            and all(
                item.capability("on" if value == "onoff" else value, value)
                in item.control
                for value in required
            )
        )


def _semantic(capability_id: str, binding: DeviceBinding | None) -> str:
    if binding is not None:
        inverse = {value: key for key, value in binding.capability_map.items()}
        if capability_id in inverse:
            return {
                "position": "cover_position",
                "target": "thermostat_target_c",
                "temperature_c": "thermostat_target_c",
            }.get(inverse[capability_id], inverse[capability_id])
    exact = {
        "onoff": "on",
        "dim": "brightness",
        "measure_luminance": "illuminance_lux",
        "measure_temperature": "temperature_c",
        "measure_power": "power_w",
        "meter_power": "energy_kwh",
        "alarm_motion": "presence",
        "alarm_presence": "presence",
        "target_temperature": "thermostat_target_c",
        "windowcoverings_set": "cover_position",
    }
    if capability_id in exact:
        return exact[capability_id]
    if capability_id.startswith("measure_"):
        return capability_id.removeprefix("measure_")
    if capability_id.startswith("alarm_"):
        return capability_id.removeprefix("alarm_")
    return capability_id


def _unit(semantic: str) -> str | None:
    return {
        "brightness": "ratio",
        "illuminance_lux": "lx",
        "temperature_c": "degC",
        "thermostat_target_c": "degC",
        "power_w": "W",
        "energy_kwh": "kWh",
        "cover_position": "ratio",
    }.get(semantic)


def _value_type(value: object) -> str:
    if value is None:
        return "unknown"
    if type(value) is bool:
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    return "unknown"


def _same(left: object, right: object) -> bool:
    if (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
    ):
        return abs(float(left) - float(right)) <= 1e-6
    return type(left) is type(right) and left == right


# Homey actuator capability ids whose value changes are human-or-automation
# overrides. Detection is independent of the write allowlist; execute gating
# still uses control_allowed / binding.control.
_OVERRIDE_ACTUATOR_CAPABILITIES = frozenset(
    {"onoff", "dim", "target_temperature", "windowcoverings_set"}
)


def _override_visible_capability(capability: dict[str, Any]) -> bool:
    if capability.get("control_allowed") is True:
        return True
    return str(capability.get("id")) in _OVERRIDE_ACTUATOR_CAPABILITIES


def _controlled_changes(
    previous: dict[str, Any], current: dict[str, Any]
) -> list[dict[str, Any]]:
    previous_values = {
        (str(device["alias"]), str(capability["id"])): capability.get("value")
        for device in previous.get("devices", [])
        for capability in device.get("capabilities", [])
        if _override_visible_capability(capability)
    }
    current_values = {
        (str(device["alias"]), str(capability["id"])): capability.get("value")
        for device in current.get("devices", [])
        for capability in device.get("capabilities", [])
        if _override_visible_capability(capability)
    }
    return [
        {
            "alias": alias,
            "capability_id": capability_id,
            "previous": previous_values[key],
            "observed": current_values[key],
        }
        for key in sorted(previous_values.keys() & current_values.keys())
        if not _same(previous_values[key], current_values[key])
        for alias, capability_id in (key,)
    ]


def _light_schema(bindings: tuple[DeviceBinding, ...]) -> dict[str, Any]:
    branches: list[dict[str, Any]] = []
    for binding in bindings:
        low, high = binding.limit("brightness", (0.0, 1.0))
        properties: dict[str, Any] = {
            "alias": {"const": binding.alias},
            "on": {"type": "boolean"},
        }
        if binding.capability("brightness", "dim") in binding.control:
            properties["brightness"] = {
                "type": "number",
                "minimum": low,
                "maximum": high,
            }
        branches.append(
            {
                "type": "object",
                "properties": properties,
                "required": ["alias"],
                "anyOf": [
                    {"required": ["on"]},
                    {"required": ["brightness"]},
                ],
                "additionalProperties": False,
            }
        )
    return {"oneOf": branches}


def _alias_value_schema(
    bindings: tuple[DeviceBinding, ...], field: str, value_schema: dict[str, Any]
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "alias": {"enum": sorted(item.alias for item in bindings)},
            field: value_schema,
        },
        "required": ["alias", field],
        "additionalProperties": False,
    }


def _bounded_alias_schema(
    bindings: tuple[DeviceBinding, ...],
    field: str,
    default: tuple[float, float],
    *,
    limit_name: str | None = None,
) -> dict[str, Any]:
    return {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "alias": {"const": item.alias},
                    field: {
                        "type": "number",
                        "minimum": item.limit(limit_name or field, default)[0],
                        "maximum": item.limit(limit_name or field, default)[1],
                    },
                },
                "required": ["alias", field],
                "additionalProperties": False,
            }
            for item in bindings
        ]
    }


def _mutation_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "alias": {"type": "string"},
            "acknowledged": {"type": "boolean"},
            "verified": {"type": "boolean"},
            "writes": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["alias", "acknowledged", "verified", "writes"],
        "additionalProperties": False,
    }
