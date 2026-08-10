from __future__ import annotations

from typing import Any, ClassVar

from .contracts import (
    BrainDecision,
    BrainManifest,
    DecisionKind,
    SpecialistAdvice,
    ToolCall,
)
from .target import SET_COVER, SET_LIGHT, SET_SWITCH, SET_THERMOSTAT


class HomeOpsExecutiveBrain:
    """Application-level router; it selects domains, never certifies outcomes."""

    manifest = BrainManifest(
        name="homeops-executive",
        description="Routes typed HomeCharter obligations to HomeOps specialists",
        id="engine.homey.homeops-executive/v1",
    )
    _specialist_for_domain: ClassVar[dict[str, str]] = {
        "lighting": "engine.homey.lighting-brain/v1",
        "climate": "engine.homey.climate-brain/v1",
        "energy": "engine.homey.energy-brain/v1",
        "presence": "engine.homey.presence-brain/v1",
    }

    def __init__(self) -> None:
        self.calls = 0

    def decide(self, context: Any) -> BrainDecision:
        self.calls += 1
        for raw in context.pending_advice:
            advice = SpecialistAdvice.from_dict(raw.get("advice", {}))
            request_id = str(raw.get("brain_request_id", ""))
            specialist = str(raw.get("specialist", "specialist"))
            if advice.suggested_action is not None:
                return BrainDecision(
                    DecisionKind.USE_TOOL,
                    name=advice.suggested_action.capability_id,
                    arguments=advice.suggested_action.arguments,
                    rationale=f"Use bounded advice from {specialist}",
                    based_on=(request_id,),
                )
            return BrainDecision(
                DecisionKind.WAIT,
                rationale=f"{specialist} deferred; wait for new observation evidence",
                based_on=(request_id,),
            )
        obligation = _next_violation(context.snapshot.state)
        if obligation is None:
            return BrainDecision(
                DecisionKind.COMPLETE,
                rationale="No typed charter violation remains; HomeOracle must verify",
            )
        domain = str(obligation["domain"])
        specialist_id = self._specialist_for_domain.get(domain)
        available = {item.qualified_id for item in context.specialists}
        if specialist_id not in available:
            return BrainDecision(
                DecisionKind.WAIT,
                rationale=f"No specialist is available for {domain}",
            )
        return BrainDecision(
            DecisionKind.CONSULT_BRAIN,
            name=specialist_id,
            arguments={"obligation_id": obligation["id"]},
            rationale=f"Route highest-priority observed violation to {domain}",
        )


class LightingBrain:
    manifest = BrainManifest(
        name="lighting-brain",
        description="Proposes one bounded light action for a typed lighting obligation",
        supported_capabilities=(SET_LIGHT,),
        plugin_id="engine.homey",
        id="engine.homey.lighting-brain/v1",
    )

    def advise(self, context: Any) -> SpecialistAdvice:
        obligation = _selected_violation(context, "lighting")
        if obligation is None:
            return SpecialistAdvice("No violated lighting obligation is observable")
        zone = str(obligation["zone"])
        lights = _devices(
            context.snapshot.state,
            zone=zone,
            kinds={"light"},
            allowed=obligation.get("allowed_device_aliases"),
        )
        lights = [item for item in lights if _can_control(item, "on")]
        if not lights:
            return SpecialistAdvice(
                f"No allowlisted controllable light is available in {zone}",
                metadata={"defer": True, "zone": zone},
            )
        desired = obligation["desired"]
        if desired.get("vacant_light", {}).get("on") is False and _presence_inactive(
            obligation
        ):
            light = next(
                (item for item in lights if _value(item, "on") is True), lights[0]
            )
            return SpecialistAdvice(
                f"Turn off {light['alias']} after observed presence expiry",
                ToolCall(SET_LIGHT, {"alias": light["alias"], "on": False}),
                metadata={"obligation_id": obligation["id"]},
            )
        light = min(
            lights,
            key=lambda item: (
                float(item["rated_power_w"] or float("inf")),
                -int(item.get("priority", 0)),
                item["alias"],
            ),
        )
        current = _number(_value(light, "brightness"), 0.0)
        lux = _number(obligation.get("observations", {}).get("illuminance_lux"), 0.0)
        minimum = float(desired["illuminance_lux"]["min"])
        brightness_max = float(desired["light"]["brightness_max"])
        correction = max(0.10, (minimum - lux) / max(minimum, 1.0) * 0.35)
        brightness = min(brightness_max, max(0.10, current + correction))
        rated = light.get("rated_power_w")
        watt_limit = float(desired["power_w"]["max"])
        if isinstance(rated, (int, float)) and rated > 0:
            brightness = min(brightness, watt_limit / float(rated))
        brightness = round(max(0.01, brightness), 3)
        arguments: dict[str, Any] = {"alias": light["alias"], "on": True}
        if _can_control(light, "brightness"):
            arguments["brightness"] = brightness
        return SpecialistAdvice(
            f"Raise observed light in {zone} toward its charter lux band",
            ToolCall(SET_LIGHT, arguments),
            metadata={
                "obligation_id": obligation["id"],
                "brightness_bound": brightness_max,
                "watt_bound": watt_limit,
            },
        )


class ClimateBrain:
    manifest = BrainManifest(
        name="climate-brain",
        description="Prefers passive cover control before active thermostat control",
        supported_capabilities=(SET_COVER, SET_THERMOSTAT),
        plugin_id="engine.homey",
        id="engine.homey.climate-brain/v1",
    )

    def advise(self, context: Any) -> SpecialistAdvice:
        obligation = _selected_violation(context, "climate")
        if obligation is None:
            return SpecialistAdvice("No violated climate obligation is observable")
        zone = str(obligation["zone"])
        allowed = obligation.get("allowed_device_aliases")
        for device in _devices(
            context.snapshot.state,
            zone=zone,
            kinds={"cover", "blind", "curtain"},
            allowed=allowed,
        ):
            if (
                _can_control(device, "cover_position")
                and _number(_value(device, "cover_position"), 1.0) > 0.0
            ):
                return SpecialistAdvice(
                    f"Close {device['alias']} as passive cooling",
                    ToolCall(SET_COVER, {"alias": device["alias"], "position": 0.0}),
                    metadata={"strategy": "passive", "obligation_id": obligation["id"]},
                )
        target = float(obligation["desired"]["thermostat_target_c"])
        for device in _devices(
            context.snapshot.state,
            zone=zone,
            kinds={"thermostat", "climate"},
            allowed=allowed,
        ):
            if _can_control(device, "thermostat_target_c"):
                return SpecialistAdvice(
                    f"Set {device['alias']} only after passive options are exhausted",
                    ToolCall(
                        SET_THERMOSTAT,
                        {"alias": device["alias"], "temperature_c": target},
                    ),
                    metadata={"strategy": "active", "obligation_id": obligation["id"]},
                )
        return SpecialistAdvice(
            f"No supported climate actuator is available in {zone}",
            metadata={"defer": True, "zone": zone},
        )


class EnergyBrain:
    manifest = BrainManifest(
        name="energy-brain",
        description="Proposes one allowlisted shedding action under a house power budget",
        supported_capabilities=(SET_LIGHT, SET_SWITCH),
        plugin_id="engine.homey",
        id="engine.homey.energy-brain/v1",
    )

    def advise(self, context: Any) -> SpecialistAdvice:
        obligation = _selected_violation(context, "energy")
        if obligation is None:
            return SpecialistAdvice("No violated energy obligation is observable")
        candidates = [
            item
            for item in context.snapshot.state.get("devices", [])
            if item.get("control_allowed")
            and item.get("available") is True
            and item.get("kind") in {"light", "switch", "plug", "socket", "device"}
            and _value(item, "on") is True
        ]
        if not candidates:
            return SpecialistAdvice(
                "Power is over budget but no allowlisted load can be shed",
                metadata={"defer": True},
            )
        device = min(
            candidates, key=lambda item: (int(item.get("priority", 0)), item["alias"])
        )
        capability = SET_LIGHT if device.get("kind") == "light" else SET_SWITCH
        return SpecialistAdvice(
            f"Shed lowest-priority observed load {device['alias']}",
            ToolCall(capability, {"alias": device["alias"], "on": False}),
            metadata={"obligation_id": obligation["id"]},
        )


class PresenceBrain:
    manifest = BrainManifest(
        name="presence-brain",
        description="Handles typed vacancy obligations without inferring new preferences",
        supported_capabilities=(SET_LIGHT, SET_SWITCH),
        plugin_id="engine.homey",
        id="engine.homey.presence-brain/v1",
    )

    def advise(self, context: Any) -> SpecialistAdvice:
        obligation = _selected_violation(context, "presence")
        if obligation is None:
            return SpecialistAdvice("No violated presence obligation is observable")
        return SpecialistAdvice(
            "Presence evidence requests no direct actuation",
            metadata={"defer": True, "obligation_id": obligation["id"]},
        )


def _selected_violation(context: Any, domain: str) -> dict[str, Any] | None:
    wanted = str(context.specialist_query.get("obligation_id", ""))
    candidates = [
        item
        for item in context.snapshot.state.get("obligations", [])
        if item.get("status") == "VIOLATED" and item.get("domain") == domain
    ]
    return next((item for item in candidates if item.get("id") == wanted), None) or (
        candidates[0] if candidates else None
    )


def _next_violation(state: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [
        item
        for item in state.get("obligations", [])
        if item.get("status") == "VIOLATED"
    ]
    candidates.sort(
        key=lambda item: (-int(item.get("priority", 0)), str(item.get("id")))
    )
    return candidates[0] if candidates else None


def _devices(
    state: dict[str, Any],
    *,
    zone: str,
    kinds: set[str],
    allowed: object,
) -> list[dict[str, Any]]:
    allowed_set = set(allowed) if isinstance(allowed, list) else None
    return [
        item
        for item in state.get("devices", [])
        if item.get("zone_alias") == zone
        and item.get("kind") in kinds
        and item.get("available") is True
        and (allowed_set is None or item.get("alias") in allowed_set)
    ]


def _can_control(device: dict[str, Any], semantic: str) -> bool:
    return any(
        item.get("semantic") == semantic and item.get("controllable") is True
        for item in device.get("capabilities", [])
    )


def _value(device: dict[str, Any], semantic: str) -> object:
    capability = next(
        (
            item
            for item in device.get("capabilities", [])
            if item.get("semantic") == semantic
        ),
        None,
    )
    return capability.get("value") if capability else None


def _number(value: object, default: float) -> float:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else default
    )


def _presence_inactive(obligation: dict[str, Any]) -> bool:
    conditions = obligation.get("conditions", [])
    return (
        bool(conditions)
        and conditions[0].get("signal") == "presence"
        and conditions[0].get("result") is False
    )
