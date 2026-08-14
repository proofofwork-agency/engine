from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from math import ceil
from pathlib import Path
from typing import Any
from uuid import uuid4

from engine_sdk import (
    ActionRequestV1,
    AuthorizationV1,
    AutonomyContextV1,
    AutonomyDecisionKindV1,
    AutonomyDecisionV1,
    AutonomyProfileV1,
    AutonomyStrategySpecV1,
    BehaviorBatchV1,
    BehaviorSignalV1,
    CapabilitySpecV2,
    ConditionV1,
    DesiredEffectV1,
    EffectDeltaV1,
    EntityV1,
    EvidenceGrade,
    ExecutionReceiptV2,
    ExecutionStateV2,
    GoalCandidateV1,
    GoalModeV2,
    GoalSpecV2,
    GoalTemplateSpecV1,
    ObservationV1,
    PluginManifestV2,
    ProposedActionV1,
    RelationV1,
    RoutineSpecV1,
    RoutineStatus,
    RoutineTemplateSpecV1,
    ScopedConditionV1,
    SpecialistAdviceV1,
    TargetObservationV2,
    WorldSnapshotV2,
    artifact_sha256,
    load_static_manifest,
    locate_distribution_manifest,
)

from .config import HomeyConfig, load_config
from .contracts import ToolCall
from .store import HomeOpsStore
from .target import SET_COVER, SET_LIGHT, SET_SWITCH, SET_THERMOSTAT, HomeyTarget
from .transport import (
    CLIHomeyTransport,
    EventSource,
    HomeyTransport,
    HTTPHomeyTransport,
    NullEventSource,
    SocketIOEventSource,
)

LIGHTING = "homey.lighting.zone"
LIGHTING_ZONE_STATE = "homey.lighting.zone-state"
SWITCH = "homey.switch"
COVER = "homey.cover.position"
CLIMATE = "homey.climate.target"
LIGHTING_PREFERENCE = "engine.homey.preference.lighting-brightness-band/v1"
DAILY_OFF = "lighting.daily-off/v1"
PRESENCE_DARK_ON = "lighting.presence-dark-on/v1"
PRESENCE_ABSENT_OFF = "lighting.presence-absent-off/v1"
FAMILY_TO_V1 = {
    LIGHTING: SET_LIGHT,
    LIGHTING_ZONE_STATE: SET_LIGHT,
    SWITCH: SET_SWITCH,
    COVER: SET_COVER,
    CLIMATE: SET_THERMOSTAT,
}
V1_TO_FAMILY = {
    SET_SWITCH: SWITCH,
    SET_COVER: COVER,
    SET_THERMOSTAT: CLIMATE,
}


def _static_manifest() -> PluginManifestV2:
    path = Path(__file__).resolve().parents[2] / "engine-plugin.toml"
    if not path.is_file():
        from importlib import metadata

        path = locate_distribution_manifest(metadata.distribution("engine-homey"))
        if path is None:
            raise FileNotFoundError("engine-homey static manifest is not installed")
    return load_static_manifest(path)


class HomeyWorldProvider:
    id = "homey-world"
    plugin_id = "engine.homey"

    def __init__(
        self,
        target: HomeyTarget,
        manifest: PluginManifestV2,
        *,
        poll_interval_seconds: float,
        freshness_seconds: float,
    ) -> None:
        self.target = target
        self.target_id = target.manifest.id
        self.manifest = manifest
        self.poll_interval_seconds = poll_interval_seconds
        self.freshness_seconds = freshness_seconds
        self._persisted_projection = target.store.provider_projection(self.id)
        self._presence_inactive_since = _persisted_inactive_since(
            self._persisted_projection.presence_state
            if self._persisted_projection is not None
            else {}
        )
        self._last_observed_at = (
            _datetime(self._persisted_projection.last_observed_at)
            if self._persisted_projection is not None
            else None
        )
        self.latest_observation: TargetObservationV2 | None = None

    def discover(self) -> tuple[CapabilitySpecV2, ...]:
        discovered = {item.id for item in self.target.capabilities()}
        available = {
            V1_TO_FAMILY[item]
            for item in discovered
            if item in V1_TO_FAMILY
        }
        if SET_LIGHT in discovered:
            available.update({LIGHTING, LIGHTING_ZONE_STATE})
        return tuple(
            item for item in self.manifest.capabilities if item.family in available
        )

    def observe(self) -> TargetObservationV2:
        snapshot = self.target.observe()
        boundary = _datetime(snapshot.observed_at)
        continuous = _is_continuous_observation(
            self._last_observed_at, boundary, self.freshness_seconds
        )
        comparison_revision = (
            self.latest_observation.revision
            if self.latest_observation is not None
            else (
                self._persisted_projection.revision
                if self._persisted_projection is not None
                else 0
            )
        )
        result, inactive_since = self._project_observation(
            snapshot, comparison_revision, continuous=continuous
        )
        if self.latest_observation is not None:
            result = _preserve_observation_timestamps(
                result,
                self.latest_observation,
                preserve_presence=continuous,
            )
        elif self._persisted_projection is not None and continuous:
            result = _preserve_persisted_presence_timestamps(
                result, self._persisted_projection.presence_state
            )
        presence_state = _provider_presence_state(result, inactive_since)
        self._persisted_projection, _ = self.target.store.save_provider_projection(
            self.id,
            result.semantic_fingerprint(),
            presence_state,
            snapshot.observed_at,
        )
        result = _restamp_observation(
            result, self._persisted_projection.revision
        )

        # Continuity bookkeeping is committed only after the semantic change
        # decision. Absolute inactive-since timestamps remain stable while the
        # observed presence state is unchanged.
        self._presence_inactive_since = inactive_since
        self._last_observed_at = boundary
        self.latest_observation = result
        return result

    def _project_observation(
        self, snapshot: Any, revision: int, *, continuous: bool
    ) -> tuple[TargetObservationV2, dict[str, datetime]]:
        state = snapshot.state
        source = self.plugin_id
        home_id = f"homey:{self.target_id}:home"
        entities: list[EntityV1] = [
            EntityV1(
                home_id, self.target_id, "homey.home", source,
                name=self.target_id,
                attributes={
                    "mode": state.get("mode"),
                    "coverage": state.get("coverage", {}),
                },
            )
        ]
        relations: list[RelationV1] = []
        observations: list[ObservationV1] = []
        zone_ids: dict[str, str] = {}
        for zone in state.get("zones", ()):
            alias = str(zone["alias"])
            entity_id = f"homey:{self.target_id}:zone:{alias}"
            zone_ids[alias] = entity_id
            entities.append(
                EntityV1(
                    entity_id, self.target_id, "homey.zone", source,
                    name=str(zone.get("name", alias)),
                    attributes={
                        "alias": alias,
                        "homey_id": zone.get("homey_id"),
                        "parent_alias": zone.get("parent_alias"),
                    },
                )
            )
            relations.append(
                RelationV1(
                    f"{home_id}:contains:{entity_id}", "contains", home_id,
                    entity_id, source, snapshot.observed_at, EvidenceGrade.OBSERVED,
                )
            )
        devices_by_zone: dict[str, list[dict[str, Any]]] = {}
        for device in state.get("devices", ()):
            alias = str(device["alias"])
            kind = str(device.get("kind", "device"))
            entity_type = "homey.camera" if kind == "camera" else "homey.device"
            entity_id = f"homey:{self.target_id}:device:{alias}"
            zone_alias = str(device.get("zone_alias")) if device.get("zone_alias") is not None else None
            zone_entity_id = zone_ids.get(zone_alias or "")
            attributes = {
                "alias": alias,
                "homey_id": device.get("homey_id"),
                "kind": kind,
                "zone_alias": zone_alias,
                "zone_entity_id": zone_entity_id,
                "available": device.get("available"),
                "control_allowed": device.get("control_allowed", False),
                "rated_power_w": device.get("rated_power_w"),
                "priority": device.get("priority", 0),
            }
            entities.append(EntityV1(entity_id, self.target_id, entity_type, source, str(device.get("name", alias)), attributes))
            relations.append(
                RelationV1(
                    f"{home_id}:contains:{entity_id}", "contains", home_id,
                    entity_id, source, snapshot.observed_at, EvidenceGrade.OBSERVED,
                )
            )
            if zone_entity_id is not None:
                relations.append(
                    RelationV1(
                        f"{entity_id}:located-in:{zone_entity_id}", "located_in",
                        entity_id, zone_entity_id, source, snapshot.observed_at,
                        EvidenceGrade.OBSERVED,
                    )
                )
                if kind == "light":
                    relations.append(
                        RelationV1(
                            f"{entity_id}:illuminates:{zone_entity_id}", "illuminates",
                            entity_id, zone_entity_id, source, snapshot.observed_at,
                            EvidenceGrade.DERIVED,
                        )
                    )
            devices_by_zone.setdefault(zone_alias or "", []).append(device)
            for capability in device.get("capabilities", ()):
                semantic = str(capability.get("semantic", capability.get("id", "unknown")))
                if kind == "camera" and semantic in {
                    "presence", "motion", "person", "tamper", "alarm_motion"
                }:
                    semantic = "camera.detection"
                if capability.get("evidence") != "OBSERVED":
                    grade = EvidenceGrade.UNKNOWN
                    value = None
                else:
                    grade = EvidenceGrade.OBSERVED
                    value = _quantize_sensor_value(
                        semantic, capability.get("value")
                    )
                observed_at = capability.get("observed_at") or snapshot.observed_at
                observations.append(
                    ObservationV1(
                        id=f"{entity_id}:{semantic}:r{revision}",
                        entity_id=entity_id, property=semantic, value=value,
                        unit=capability.get("unit"), source=source,
                        observed_at=str(observed_at), evidence_grade=grade,
                        quality=1.0 if grade is EvidenceGrade.OBSERVED else None,
                        coverage="reported_by_homey",
                    )
                )
                if zone_entity_id is not None and semantic in {
                    "illuminance_lux", "power_w", "temperature_c", "presence"
                }:
                    relations.append(
                        RelationV1(
                            f"{entity_id}:measures:{zone_entity_id}:{semantic}",
                            "measures", entity_id, zone_entity_id, source,
                            snapshot.observed_at, EvidenceGrade.DERIVED,
                            attributes={"property": semantic},
                        )
                    )
        next_inactive_since: dict[str, datetime] = {}
        for zone_alias, zone_entity_id in zone_ids.items():
            zone_devices = devices_by_zone.get(zone_alias, [])
            inactive_since = _add_zone_aggregates(
                observations, zone_entity_id, zone_devices, revision,
                snapshot.observed_at, source,
                inactive_since=self._presence_inactive_since.get(zone_alias),
                continuous=continuous,
            )
            if inactive_since is not None:
                next_inactive_since[zone_alias] = inactive_since
        result = TargetObservationV2(
            target_id=self.target_id,
            revision=revision,
            observed_at=snapshot.observed_at,
            entities=tuple(entities), relations=tuple(relations),
            observations=tuple(observations),
            coverage={
                "zones": state.get("coverage", {}).get("zones", "UNKNOWN"),
                "devices": state.get("coverage", {}).get("devices", "UNKNOWN"),
                "camera_artifacts": "not_exported",
                "opaque_capabilities": "observation_only",
            },
            source=source,
        )
        return result, next_inactive_since

    def subscribe(self, wake: Any) -> Any:
        return self.target.subscribe(wake)


class HomeyDomainController:
    id = "homey-domain-controller"
    plugin_id = "engine.homey"
    supported_families = (LIGHTING, LIGHTING_ZONE_STATE, SWITCH, COVER, CLIMATE)

    def concretize(
        self,
        proposal: ProposedActionV1,
        snapshot: WorldSnapshotV2,
        capability: CapabilitySpecV2,
    ) -> ActionRequestV1:
        entity = next(item for item in snapshot.entities if item.id == proposal.entity_id)
        if proposal.capability_family == LIGHTING:
            parameters = self._lighting_parameters(proposal, snapshot, entity)
        elif proposal.capability_family == LIGHTING_ZONE_STATE:
            parameters = self._zone_state_parameters(proposal, snapshot, entity)
        else:
            alias = entity.attributes.get("alias")
            if not isinstance(alias, str):
                raise ValueError("Homey actuator entity lacks a stable alias")
            key = {SWITCH: "on", COVER: "position", CLIMATE: "temperature_c"}[proposal.capability_family]
            parameters = {"alias": alias, key: proposal.semantic_parameters[key]}
        return ActionRequestV1(
            id="request:" + uuid4().hex,
            proposal_id=proposal.id, goal_id=proposal.goal_id,
            plugin_id=self.plugin_id, target_id=proposal.target_id,
            entity_id=proposal.entity_id, capability_id=capability.id,
            capability_family=capability.family, parameters=parameters,
            snapshot_id=snapshot.id, world_revision=snapshot.revision,
            target_revision=int(snapshot.target_revisions[proposal.target_id]),
            preconditions=(), idempotency_key=proposal.id,
            deadline_at=(datetime.now(UTC) + timedelta(milliseconds=capability.deadline_ms)).isoformat(),
            invocation_mode=capability.invocation_mode,
        )

    def _lighting_parameters(
        self, proposal: ProposedActionV1, snapshot: WorldSnapshotV2, zone: EntityV1
    ) -> dict[str, Any]:
        lights = [
            item for item in snapshot.entities
            if item.entity_type == "homey.device"
            and item.attributes.get("kind") == "light"
            and item.attributes.get("zone_entity_id") == zone.id
            and item.attributes.get("control_allowed") is True
            and item.attributes.get("available") is True
        ]
        if not lights:
            raise ValueError("zone has no observed controllable light")
        light = min(
            lights,
            key=lambda item: (
                float(item.attributes.get("rated_power_w") or float("inf")),
                -int(item.attributes.get("priority", 0)),
                item.id,
            ),
        )
        current_lux = _number(_value(snapshot, zone.id, "illuminance_lux"), 0.0)
        minimum = float(proposal.semantic_parameters["minimum_lux"])
        current = _number(_value(snapshot, light.id, "brightness"), 0.0)
        maximum_brightness = float(proposal.semantic_parameters["brightness_max"])
        correction = max(0.10, (minimum - current_lux) / max(minimum, 1.0) * 0.35)
        brightness = min(maximum_brightness, max(0.10, current + correction))
        rated = light.attributes.get("rated_power_w")
        if isinstance(rated, (int, float)) and rated > 0:
            brightness = min(
                brightness,
                float(proposal.semantic_parameters["max_power_w"]) / float(rated),
            )
        return {
            "alias": str(light.attributes["alias"]),
            "on": True,
            "brightness": round(max(0.01, brightness), 3),
        }

    def _zone_state_parameters(
        self, proposal: ProposedActionV1, snapshot: WorldSnapshotV2, zone: EntityV1
    ) -> dict[str, Any]:
        wanted = proposal.semantic_parameters.get("on")
        if type(wanted) is not bool:
            raise ValueError("zone-state proposal requires boolean on")
        lights = [
            item for item in snapshot.entities
            if item.entity_type == "homey.device"
            and item.attributes.get("kind") == "light"
            and item.attributes.get("zone_entity_id") == zone.id
            and item.attributes.get("control_allowed") is True
            and item.attributes.get("available") is True
        ]
        if not wanted:
            lights = [item for item in lights if _value(snapshot, item.id, "on") is True]
        if not lights:
            raise ValueError("zone has no fresh controllable lamp requiring this state")
        light = min(
            lights,
            key=lambda item: (
                float(item.attributes.get("rated_power_w") or float("inf")),
                -int(item.attributes.get("priority", 0)),
                item.id,
            ),
        )
        return {"alias": str(light.attributes["alias"]), "on": wanted}


class HomeyExecutorV2:
    id = "homey-executor"
    plugin_id = "engine.homey"

    def __init__(self, target: HomeyTarget):
        self.target = target

    def dispatch(
        self, request: ActionRequestV1, authorization: AuthorizationV1
    ) -> ExecutionReceiptV2:
        if authorization.request_sha256 != request.sha256:
            raise PermissionError("authorization is bound to another request")
        if authorization.target_id != request.target_id:
            raise PermissionError("authorization target mismatch")
        requested_at = datetime.now(UTC).isoformat()
        result = self.target.execute(
            ToolCall(
                capability_id=FAMILY_TO_V1[request.capability_family],
                arguments=request.parameters,
                target_id=request.target_id,
            )
        )
        state = (
            ExecutionStateV2.SUCCEEDED if result.succeeded
            else ExecutionStateV2.PARTIAL if result.partial
            else ExecutionStateV2.FAILED
        )
        return ExecutionReceiptV2(
            id="receipt:" + uuid4().hex,
            request_id=request.id, authorization_id=authorization.id,
            target_id=request.target_id, capability_id=request.capability_id,
            state=state, requested_at=requested_at,
            completed_at=datetime.now(UTC).isoformat(),
            acknowledged=result.output.get("acknowledged") if result.output else None,
            result=result.to_dict(), error=result.error,
            adapter_version="0.2.0",
        )

    def poll(self, external_handle: str) -> ExecutionReceiptV2:
        raise KeyError(external_handle)

    def cancel(self, external_handle: str) -> ExecutionReceiptV2:
        raise KeyError(external_handle)


class HomeyEffectOracleV2:
    id = "homey-effect-oracle"
    plugin_id = "engine.homey"
    supported_families = (LIGHTING, LIGHTING_ZONE_STATE, SWITCH, COVER, CLIMATE)

    def reconcile(
        self,
        proposal: ProposedActionV1,
        pre_state: WorldSnapshotV2,
        receipt: ExecutionReceiptV2,
        post_state: WorldSnapshotV2,
    ) -> EffectDeltaV1:
        entity_id = proposal.entity_id
        evidence: list[str] = []
        if proposal.capability_family == LIGHTING:
            lux, lux_id = _value_and_id(post_state, entity_id, "illuminance_lux")
            power, power_id = _value_and_id(post_state, entity_id, "power_w")
            evidence.extend(item for item in (lux_id, power_id) if item)
            if not isinstance(lux, (int, float)) or isinstance(lux, bool) or not isinstance(power, (int, float)) or isinstance(power, bool):
                achieved = None
                reason = "fresh zone lux or power evidence is missing"
            else:
                achieved = (
                    float(proposal.semantic_parameters["minimum_lux"]) <= float(lux)
                    <= float(proposal.semantic_parameters["maximum_lux"])
                    and float(power) <= float(proposal.semantic_parameters["max_power_w"])
                )
                reason = "fresh zone lux and power satisfy requested effect" if achieved else "ACK did not produce the requested zone effect"
            changes = {
                "lux_before": _value(pre_state, entity_id, "illuminance_lux"),
                "lux_after": lux,
                "power_after_w": power,
            }
        elif proposal.capability_family == LIGHTING_ZONE_STATE:
            actual, observation_id = _value_and_id(
                post_state, entity_id, "lighting.any_on"
            )
            if observation_id:
                evidence.append(observation_id)
            expected = proposal.semantic_parameters["on"]
            achieved = actual == expected if type(actual) is bool else None
            reason = (
                "fresh zone state matches requested effect"
                if achieved else
                "ACK did not produce the requested zone state"
                if achieved is False else
                "fresh zone state evidence is missing"
            )
            changes = {
                "any_on_before": _value(pre_state, entity_id, "lighting.any_on"),
                "any_on_after": actual,
            }
        else:
            property_name, expected = {
                SWITCH: ("on", proposal.semantic_parameters["on"]),
                COVER: ("cover_position", proposal.semantic_parameters["position"]),
                CLIMATE: ("thermostat_target_c", proposal.semantic_parameters["temperature_c"]),
            }[proposal.capability_family]
            actual, observation_id = _value_and_id(post_state, entity_id, property_name)
            if observation_id:
                evidence.append(observation_id)
            achieved = None if actual is None else _same(actual, expected)
            reason = "fresh device observation matches requested effect" if achieved else "fresh device observation does not match requested effect"
            changes = {"before": _value(pre_state, entity_id, property_name), "after": actual}
        grade = EvidenceGrade.DERIVED if achieved is not None else EvidenceGrade.UNKNOWN
        return EffectDeltaV1(
            id="effect:" + uuid4().hex,
            goal_id=proposal.goal_id, proposal_id=proposal.id,
            request_id=receipt.request_id, receipt_id=receipt.id,
            pre_snapshot_id=pre_state.id, post_snapshot_id=post_state.id,
            evidence_grade=grade, achieved=achieved, changes=changes,
            measurement_observation_ids=tuple(evidence), reason=reason,
            observed_at=post_state.observed_at,
        )


class HomeyDomainSpecialistV2:
    id = "engine.homey.domain-specialist/v2"
    plugin_id = "engine.homey"
    supported_families = (LIGHTING, LIGHTING_ZONE_STATE, SWITCH, COVER, CLIMATE)

    def advise(
        self, goal: GoalSpecV2, snapshot: WorldSnapshotV2, request: dict[str, object]
    ) -> SpecialistAdviceV1:
        effect_id = str(request.get("effect_id", ""))
        effect = next((item for item in goal.desired_effects if item.id == effect_id), None)
        if effect is None or effect.capability_family not in self.supported_families:
            return SpecialistAdviceV1(self.id, False, None, "No supported Homey effect was requested")
        entities = _select(snapshot, effect.entity_selector)
        if not entities:
            return SpecialistAdviceV1(self.id, False, None, "No scoped Homey entity is observed")
        entity = next(
            (item for item in entities if not _effect_true(effect, snapshot, item.id)),
            entities[0],
        )
        evidence_ids = tuple(
            item.id for item in snapshot.observations if item.entity_id == entity.id
        )
        semantic_parameters = dict(effect.parameters)
        brightness_band = goal.preferences.get(LIGHTING_PREFERENCE)
        if (
            effect.capability_family == LIGHTING
            and isinstance(brightness_band, list)
            and len(brightness_band) == 2
            and all(
                isinstance(item, (int, float)) and not isinstance(item, bool)
                for item in brightness_band
            )
        ):
            semantic_parameters["brightness_max"] = float(brightness_band[1])
        proposal = ProposedActionV1(
            id="proposal:" + uuid4().hex,
            goal_id=goal.id, desired_effect_id=effect.id,
            capability_family=effect.capability_family,
            target_id=entity.target_id, entity_id=entity.id,
            semantic_parameters=semantic_parameters,
            based_on_snapshot_id=snapshot.id,
            based_on_world_revision=snapshot.revision,
            proposed_by=self.id,
            rationale="Translate the desired Homey domain effect without dispatch authority",
            evidence_ids=evidence_ids,
        )
        return SpecialistAdviceV1(self.id, True, proposal, "Typed Homey effect proposal")


class HomeyRoutineCompilerV1:
    """Homey pattern semantics -> inert RoutineSpec/GoalSpec data only."""

    id = "homey-routine-compiler"
    plugin_id = "engine.homey"
    supported_templates = (DAILY_OFF, PRESENCE_DARK_ON, PRESENCE_ABSENT_OFF)

    def __init__(self, target: HomeyTarget):
        self.target = target

    def compile(
        self,
        template: RoutineTemplateSpecV1,
        candidate: Any,
    ) -> tuple[RoutineSpecV1, GoalSpecV2]:
        raw = candidate.to_dict() if hasattr(candidate, "to_dict") else dict(candidate)
        target_id = str(raw["target_id"])
        entity_ids = tuple(str(item) for item in raw["entity_ids"])
        if len(entity_ids) != 1:
            raise ValueError("Homey lighting routines require exactly one zone")
        zone_id = entity_ids[0]
        pattern = dict(raw["pattern_value"])
        zone_selector = {"entity_ids": [zone_id], "target_ids": [target_id]}
        time_selector = {
            "entity_ids": ["context:local"],
            "target_ids": ["engine.context.local"],
        }
        if template.id == DAILY_OFF:
            minute = int(pattern["minute_of_day"])
            guard = ScopedConditionV1(
                "all",
                children=(
                    _minute_window_guard(minute, time_selector),
                    ScopedConditionV1(
                        "eq", zone_selector, "observation:lighting.any_on", True
                    ),
                ),
            )
            effect = DesiredEffectV1(
                id="zone-off",
                capability_family=LIGHTING_ZONE_STATE,
                entity_selector=zone_selector,
                condition=ConditionV1(
                    "eq", path="observation:lighting.any_on", value=False
                ),
                parameters={"on": False},
                description="Observe every allowlisted lamp in the zone off",
            )
            recurrence = {"kind": "daily", "window_minutes": 15}
            desired_state = {"on": False}
        elif template.id == PRESENCE_DARK_ON:
            maximum_lux = float(pattern.get("maximum_lux", 20.0))
            maximum_lux = min(100.0, max(5.0, maximum_lux))
            guard = ScopedConditionV1(
                "all",
                children=(
                    ScopedConditionV1(
                        "eq", zone_selector, "observation:presence", True
                    ),
                    ScopedConditionV1(
                        "lt", zone_selector, "observation:illuminance_lux",
                        maximum_lux, "lux",
                    ),
                    ScopedConditionV1(
                        "eq", zone_selector, "observation:lighting.any_on", False
                    ),
                ),
            )
            effect = DesiredEffectV1(
                id="presence-dark-lighting-band",
                capability_family=LIGHTING,
                entity_selector=zone_selector,
                condition=ConditionV1(
                    "all",
                    children=(
                        ConditionV1(
                            "gte", path="observation:illuminance_lux", value=60.0,
                            unit="lux",
                        ),
                        ConditionV1(
                            "lte", path="observation:illuminance_lux", value=120.0,
                            unit="lux",
                        ),
                        ConditionV1(
                            "lte", path="observation:power_w", value=20.0, unit="W"
                        ),
                    ),
                ),
                parameters={
                    "minimum_lux": 60.0,
                    "maximum_lux": 120.0,
                    "max_power_w": 20.0,
                    "brightness_max": 0.7,
                },
                description="Maintain the owner-bounded lux and watt band",
            )
            recurrence = {"kind": "event"}
            desired_state = {
                "on": True,
                "brightness_max": 0.7,
                "max_power_w": 20.0,
            }
        elif template.id == PRESENCE_ABSENT_OFF:
            inactive = int(pattern.get("minimum_inactive_seconds", 300))
            guard = ScopedConditionV1(
                "all",
                children=(
                    ScopedConditionV1(
                        "eq", zone_selector, "observation:presence", False
                    ),
                    ScopedConditionV1(
                        "duration",
                        zone_selector,
                        "observation:presence",
                        False,
                        duration_seconds=inactive,
                    ),
                    ScopedConditionV1(
                        "eq", zone_selector, "observation:lighting.any_on", True
                    ),
                ),
            )
            effect = DesiredEffectV1(
                id="absence-zone-off",
                capability_family=LIGHTING_ZONE_STATE,
                entity_selector=zone_selector,
                condition=ConditionV1(
                    "eq", path="observation:lighting.any_on", value=False
                ),
                parameters={"on": False},
                description="Observe every allowlisted lamp in the absent zone off",
            )
            recurrence = {"kind": "event"}
            desired_state = {"on": False}
        else:
            raise ValueError(f"unsupported Homey routine template: {template.id}")
        digest = artifact_sha256({
            "candidate_id": raw["id"],
            "template_id": template.id,
            "target_id": target_id,
            "entity_ids": entity_ids,
            "pattern": pattern,
        })
        goal_id = "goal:routine:" + digest
        routine = RoutineSpecV1(
            id="routine:" + digest,
            template_id=template.id,
            plugin_id=self.plugin_id,
            target_id=target_id,
            entity_ids=entity_ids,
            activation_guard=guard,
            goal_id=goal_id,
            recurrence=recurrence,
            cooldown_seconds=300,
            priority=template.priority,
            status=RoutineStatus.SHADOW,
            conflict_key="homey.lighting.zone-state",
            desired_state=desired_state,
        )
        goal = GoalSpecV2(
            id=goal_id,
            source_intent=f"Learned bounded routine {template.id}",
            mode=GoalModeV2.MAINTAIN,
            entity_scope=zone_selector,
            desired_effects=(effect,),
            preferences={LIGHTING_PREFERENCE: [0.10, 0.70]},
            budgets={"max_power_w": 20.0},
            mandate_id=None,
            priority=template.priority,
            status="active",
        )
        return routine, goal

    def validate_profile(
        self,
        profile: AutonomyProfileV1,
        routine: RoutineSpecV1,
        snapshot: WorldSnapshotV2,
    ) -> tuple[str, ...]:
        errors: list[str] = []
        if self.target.config.mode != "act":
            errors.append("Homey is in observe mode")
        if not self.target.config.armed:
            errors.append("ENGINE_HOMEY_ARMED is not 1")
        if not set(routine.entity_ids) <= {item.id for item in snapshot.entities}:
            errors.append("an enrolled Homey zone is not freshly observed")
        maximum_brightness = float(profile.limits.get("maximum_brightness", 0.7))
        maximum_power = float(profile.limits.get("maximum_power_w", 20.0))
        goal = next(
            (
                item for item in snapshot.entities
                if item.id in routine.entity_ids and item.target_id == routine.target_id
            ),
            None,
        )
        if goal is None:
            errors.append("routine target/entity identity changed")
        if maximum_brightness > 1.0 or maximum_brightness <= 0:
            errors.append("autonomy brightness limit is invalid")
        if maximum_power > 20.0 or maximum_power <= 0:
            errors.append("autonomy watt limit exceeds 20 W")
        requested_brightness = routine.desired_state.get("brightness_max")
        requested_power = routine.desired_state.get("max_power_w")
        if isinstance(requested_brightness, (int, float)) and float(requested_brightness) > maximum_brightness:
            errors.append("routine brightness expands the autonomy profile")
        if isinstance(requested_power, (int, float)) and float(requested_power) > maximum_power:
            errors.append("routine watt limit expands the autonomy profile")
        return tuple(errors)


class HomeyGoalBaselineV2:
    """Deterministic baseline; the general model compiler uses the same GoalSpec."""

    def compile_lighting(
        self,
        intent: str,
        *,
        target_id: str,
        mandate_id: str,
        minimum_lux: float = 60.0,
        maximum_lux: float = 120.0,
        max_power_w: float = 20.0,
        brightness_max: float = 0.7,
        goal_id: str = "homey-lighting-maintain",
    ) -> GoalSpecV2:
        condition = ConditionV1(
            "all",
            children=(
                ConditionV1("gte", path="observation:illuminance_lux", value=minimum_lux, unit="lux"),
                ConditionV1("lte", path="observation:illuminance_lux", value=maximum_lux, unit="lux"),
                ConditionV1("lte", path="observation:power_w", value=max_power_w, unit="W"),
            ),
        )
        effect = DesiredEffectV1(
            id="homey-lighting-band",
            capability_family=LIGHTING,
            entity_selector={"target_ids": [target_id], "entity_type": "homey.zone"},
            condition=condition,
            parameters={
                "minimum_lux": minimum_lux,
                "maximum_lux": maximum_lux,
                "max_power_w": max_power_w,
                "brightness_max": brightness_max,
            },
            description="Keep every observed Homey zone inside one typed lighting band",
        )
        return GoalSpecV2(
            id=goal_id, source_intent=intent, mode=GoalModeV2.MAINTAIN,
            entity_scope={"target_ids": ["*"]}, desired_effects=(effect,),
            preferences={LIGHTING_PREFERENCE: [0.10, brightness_max]},
            budgets={"power_w_per_zone": max_power_w}, mandate_id=mandate_id,
            priority=100,
        )


class HomeyLightingStateStrategyV1:
    id = "homey.enrolled-lighting-state/v1"
    plugin_id = "engine.homey"

    def __init__(self, spec: AutonomyStrategySpecV1):
        self.spec = spec

    def evaluate(self, context: AutonomyContextV1) -> AutonomyDecisionV1:
        enrollment = context.projection.get("enrollment", {})
        world = context.projection.get("world", {})
        if not isinstance(enrollment, dict) or not isinstance(world, dict):
            return AutonomyDecisionV1(
                AutonomyDecisionKindV1.DEFER, rationale="bounded projection is malformed"
            )
        limits = enrollment.get("limits", {})
        desired = limits.get("desired_on") if isinstance(limits, dict) else None
        if not isinstance(desired, bool):
            return AutonomyDecisionV1(
                AutonomyDecisionKindV1.DEFER,
                rationale="enrollment must contain boolean desired_on",
            )
        entity_ids = tuple(str(item) for item in enrollment.get("entity_ids", ()))
        observations = world.get("observations", ())
        for entity_id in entity_ids:
            observed = next(
                (
                    item for item in observations
                    if isinstance(item, dict)
                    and item.get("entity_id") == entity_id
                    and item.get("property") == "lighting.any_on"
                ),
                None,
            )
            if observed is None or not isinstance(observed.get("value"), bool):
                return AutonomyDecisionV1(
                    AutonomyDecisionKindV1.DEFER,
                    rationale="fresh zone lighting state is unavailable",
                )
            if observed["value"] == desired:
                continue
            target_revisions = world.get("target_revisions", {})
            if not isinstance(target_revisions, dict) or len(target_revisions) != 1:
                return AutonomyDecisionV1(
                    AutonomyDecisionKindV1.DEFER,
                    rationale="exact Homey target boundary is unavailable",
                )
            target_id = next(iter(target_revisions))
            candidate = GoalCandidateV1(
                id="goal-candidate:" + uuid4().hex,
                plugin_id=self.plugin_id,
                template_id="homey.lighting-zone-state/v1",
                target_id=str(target_id),
                entity_ids=(entity_id,),
                parameters={"on": desired},
                based_on_snapshot_id=context.current_snapshot_id,
                based_on_world_revision=context.current_world_revision,
                proposed_by=self.id,
                rationale="fresh lighting state differs from enrolled desired_on",
                evidence_ids=(str(observed.get("id", "")),),
            )
            return AutonomyDecisionV1(
                AutonomyDecisionKindV1.PROPOSE_GOAL_CANDIDATE,
                goal_candidate=candidate,
                rationale=candidate.rationale,
                evidence_ids=candidate.evidence_ids,
            )
        return AutonomyDecisionV1(
            AutonomyDecisionKindV1.NOOP,
            rationale="all enrolled zones already match desired_on",
        )


class HomeyGoalTemplateCompilerV1:
    id = "homey-goal-template-compiler"
    plugin_id = "engine.homey"
    supported_templates = ("homey.lighting-zone-state/v1",)

    def compile(
        self,
        template: GoalTemplateSpecV1,
        candidate: GoalCandidateV1,
        context: AutonomyContextV1,
    ) -> GoalSpecV2:
        del context
        desired = bool(candidate.parameters["on"])
        digest = artifact_sha256(
            {
                "template": template.id,
                "target": candidate.target_id,
                "entities": candidate.entity_ids,
                "on": desired,
            }
        )[:24]
        effect = DesiredEffectV1(
            id="lighting-zone-state",
            capability_family=LIGHTING_ZONE_STATE,
            entity_selector={"entity_ids": list(candidate.entity_ids)},
            condition=ConditionV1(
                "eq", path="observation:lighting.any_on", value=desired
            ),
            parameters={"on": desired},
            description="Maintain an exact enrolled zone lighting state",
        )
        return GoalSpecV2(
            id="goal:autonomy:" + digest,
            source_intent="Typed Homey lighting-zone-state template",
            mode=GoalModeV2.MAINTAIN,
            entity_scope={"target_ids": [candidate.target_id]},
            desired_effects=(effect,),
            priority=60,
        )


@dataclass(frozen=True)
class HomeyPluginV2:
    manifest: PluginManifestV2
    providers: tuple[Any, ...]
    controllers: tuple[Any, ...]
    executors: tuple[Any, ...]
    oracles: tuple[Any, ...]
    specialists: tuple[Any, ...]
    experience_providers: tuple[Any, ...] = ()
    routine_compilers: tuple[Any, ...] = ()
    autonomy_strategies: tuple[Any, ...] = ()
    goal_template_compilers: tuple[Any, ...] = ()


class HomeyExperienceProviderV1:
    id = "homey-behavior"
    plugin_id = "engine.homey"

    def __init__(self, store: HomeOpsStore, provider: HomeyWorldProvider):
        self.store = store
        self.provider = provider
        self.target_id = provider.target_id

    def read(self, after_cursor: str | None, limit: int) -> BehaviorBatchV1:
        cursor = int(after_cursor or 0)
        rows = self.store.preferences_after(cursor, limit + 1)
        selected = rows[:limit]
        signals: list[BehaviorSignalV1] = []
        latest = self.store.latest_snapshot()
        devices = {
            str(item.get("alias")): item
            for item in (latest.state.get("devices", ()) if latest else ())
        }
        latest_world = self.provider.latest_observation
        for row in selected:
            if row["grade"] != "INFERRED" or row["source"] != "unattributed_control_change_detected":
                continue
            origin = str(row["context"].get("origin", "unknown")).casefold()
            if origin in {"flow", "automation", "homey-flow", "homey-automation"}:
                continue
            changes = row["context"].get("changes", ())
            if not isinstance(changes, list):
                continue
            for index, change in enumerate(changes):
                if not isinstance(change, dict):
                    continue
                alias = str(change.get("alias", ""))
                device = devices.get(alias)
                if device is None:
                    continue
                zone_alias = device.get("zone_alias")
                if not isinstance(zone_alias, str):
                    continue
                zone_id = f"homey:{self.target_id}:zone:{zone_alias}"
                capability_id = str(change.get("capability_id", ""))
                capability = next(
                    (
                        item for item in device.get("capabilities", ())
                        if item.get("id") == capability_id
                    ),
                    None,
                )
                semantic = (
                    capability.get("semantic") if capability is not None else None
                )
                provenance = {
                    "plugin_evidence_id": row["id"],
                    "source": row["source"],
                    "origin": origin,
                    "origin_evidence": "INFERRED" if origin == "unknown" else "OBSERVED",
                    "engine_dispatch_excluded": True,
                    "known_automation_excluded": True,
                    "local_date": _datetime(str(row["created_at"])).date().isoformat(),
                }
                if (
                    device.get("kind") == "light"
                    and capability is not None
                    and capability.get("semantic") == "brightness"
                ):
                    old_band = _brightness_band(change.get("previous"))
                    new_band = _brightness_band(change.get("observed"))
                    if old_band is None or new_band is None:
                        continue
                    signals.append(
                        BehaviorSignalV1(
                            id=f"homey-behavior:{row['id']}:{index}:brightness",
                            plugin_id=self.plugin_id,
                            target_id=self.target_id,
                            entity_id=zone_id,
                            capability_family=LIGHTING,
                            preference_id=LIGHTING_PREFERENCE,
                            old_value=old_band,
                            new_value=new_band,
                            context={"zone_alias": zone_alias, "kind": "lighting"},
                            observed_at=str(row["created_at"]),
                            provenance=provenance,
                            evidence_grade=EvidenceGrade.INFERRED,
                        )
                    )
                    continue
                is_onoff = capability_id == "onoff" or semantic == "on"
                if not is_onoff or type(change.get("observed")) is not bool:
                    continue
                observed_on = bool(change["observed"])
                stamp = _datetime(str(row["created_at"]))
                minute = (stamp.hour * 60 + stamp.minute) // 15 * 15
                signals.append(
                    BehaviorSignalV1(
                        id=f"homey-behavior:{row['id']}:{index}:external-state",
                        plugin_id=self.plugin_id,
                        target_id=self.target_id,
                        entity_id=zone_id,
                        capability_family=LIGHTING_ZONE_STATE,
                        preference_id=LIGHTING_PREFERENCE,
                        old_value=change.get("previous"),
                        new_value=observed_on,
                        context={"kind": "lighting-external-state", "zone_id": zone_id},
                        observed_at=str(row["created_at"]),
                        provenance=provenance,
                        evidence_grade=EvidenceGrade.INFERRED,
                        pattern_value={"on": observed_on},
                    )
                )
                if device.get("kind") != "light":
                    continue
                if not observed_on:
                    signals.append(
                        _routine_signal(
                            row, index, "daily", self.target_id, zone_id,
                            DAILY_OFF,
                            {"minute_of_day": minute, "on": False},
                            change.get("previous"), False, provenance,
                        )
                    )
                if latest_world is None:
                    continue
                presence = _target_value(latest_world, zone_id, "presence")
                lux = _target_value(latest_world, zone_id, "illuminance_lux")
                inactive_since = _target_value(
                    latest_world, zone_id, "presence.inactive_since"
                )
                if observed_on and presence is True and isinstance(lux, (int, float)) and not isinstance(lux, bool):
                    maximum_lux = max(5, min(100, int(ceil(float(lux) / 5.0) * 5)))
                    signals.append(
                        _routine_signal(
                            row, index, "dark", self.target_id, zone_id,
                            PRESENCE_DARK_ON,
                            {"maximum_lux": maximum_lux, "on": True},
                            change.get("previous"), True, provenance,
                        )
                    )
                if not observed_on and isinstance(inactive_since, str):
                    inactive = max(
                        0.0,
                        (
                            _datetime(str(row["created_at"]))
                            - _datetime(inactive_since)
                        ).total_seconds(),
                    )
                    minimum_inactive = max(
                        300, min(86400, int(inactive // 300 * 300))
                    )
                    signals.append(
                        _routine_signal(
                            row, index, "absent", self.target_id, zone_id,
                            PRESENCE_ABSENT_OFF,
                            {"minimum_inactive_seconds": minimum_inactive, "on": False},
                            change.get("previous"), False, provenance,
                        )
                    )
        next_cursor = str(selected[-1]["sequence"]) if selected else str(cursor)
        return BehaviorBatchV1(next_cursor, tuple(signals), len(rows) > limit)


class LazyHomeyPluginV2:
    """Manifest-first entrypoint whose runtime resources initialize on use."""

    def __init__(self, manifest: PluginManifestV2):
        self.manifest = manifest
        self._plugin: HomeyPluginV2 | None = None

    def _load(self) -> HomeyPluginV2:
        if self._plugin is not None:
            return self._plugin
        config = load_config()
        store = HomeOpsStore(config.plugin_database)
        try:
            plugin = create_plugin_v2(config, store)
        except Exception:
            store.close()
            raise
        self._plugin = plugin
        return plugin

    @property
    def providers(self) -> tuple[Any, ...]:
        return self._load().providers

    @property
    def controllers(self) -> tuple[Any, ...]:
        return self._load().controllers

    @property
    def executors(self) -> tuple[Any, ...]:
        return self._load().executors

    @property
    def oracles(self) -> tuple[Any, ...]:
        return self._load().oracles

    @property
    def specialists(self) -> tuple[Any, ...]:
        return self._load().specialists

    @property
    def experience_providers(self) -> tuple[Any, ...]:
        return self._load().experience_providers

    @property
    def routine_compilers(self) -> tuple[Any, ...]:
        return self._load().routine_compilers

    @property
    def autonomy_strategies(self) -> tuple[Any, ...]:
        return self._load().autonomy_strategies

    @property
    def goal_template_compilers(self) -> tuple[Any, ...]:
        return self._load().goal_template_compilers


def create_plugin_v2(
    config: HomeyConfig,
    store: HomeOpsStore,
    *,
    transport: HomeyTransport | None = None,
    event_source: EventSource | None = None,
) -> HomeyPluginV2:
    manifest = _static_manifest()
    target = _build_target_v2(
        config, store, transport=transport, event_source=event_source
    )
    provider = HomeyWorldProvider(
        target,
        manifest,
        poll_interval_seconds=config.poll_interval_seconds,
        freshness_seconds=config.max_snapshot_age_seconds,
    )
    strategy_spec = next(
        item for item in manifest.autonomy_strategies
        if item.id == HomeyLightingStateStrategyV1.id
    )
    return HomeyPluginV2(
        manifest=manifest,
        providers=(provider,),
        controllers=(HomeyDomainController(),),
        executors=(HomeyExecutorV2(target),),
        oracles=(HomeyEffectOracleV2(),),
        specialists=(HomeyDomainSpecialistV2(),),
        experience_providers=(HomeyExperienceProviderV1(store, provider),),
        routine_compilers=(HomeyRoutineCompilerV1(target),),
        autonomy_strategies=(HomeyLightingStateStrategyV1(strategy_spec),),
        goal_template_compilers=(HomeyGoalTemplateCompilerV1(),),
    )


def load_plugin_v2() -> LazyHomeyPluginV2:
    # Static manifest inspection and factory invocation are intentionally inert.
    return LazyHomeyPluginV2(_static_manifest())


def _build_target_v2(
    config: HomeyConfig,
    store: HomeOpsStore,
    *,
    transport: HomeyTransport | None,
    event_source: EventSource | None,
) -> HomeyTarget:
    if transport is not None:
        actual_transport = transport
    elif config.auth_mode == "cli":
        actual_transport = CLIHomeyTransport(timeout_seconds=config.timeout_seconds)
    else:
        actual_transport = HTTPHomeyTransport(
            config.address, config.token, config.timeout_seconds
        )
    actual_events = event_source
    if actual_events is None:
        actual_events = (
            SocketIOEventSource(
                config.address,
                config.token,
                config.homey_id or "",
                timeout_seconds=config.timeout_seconds,
            )
            if config.events and config.homey_id
            else NullEventSource()
        )
    return HomeyTarget(
        config,
        store,
        actual_transport,
        event_source=actual_events,
    )


def _add_zone_aggregates(
    output: list[ObservationV1], zone_id: str, devices: list[dict[str, Any]],
    revision: int, observed_at: str, source: str,
    *, inactive_since: datetime | None, continuous: bool,
) -> datetime | None:
    values: dict[str, list[Any]] = {}
    for device in devices:
        for capability in device.get("capabilities", ()):
            if capability.get("evidence") == "OBSERVED":
                semantic = str(capability.get("semantic"))
                values.setdefault(semantic, []).append(
                    _quantize_sensor_value(semantic, capability.get("value"))
                )
    aggregates: dict[str, tuple[Any, str | None]] = {}
    numeric_lux = _numbers(values.get("illuminance_lux", ()))
    numeric_power = _numbers(values.get("power_w", ()))
    presence = [item for item in values.get("presence", ()) if type(item) is bool]
    light_on = [
        capability.get("value")
        for device in devices
        if device.get("kind") == "light"
        for capability in device.get("capabilities", ())
        if capability.get("semantic") == "on"
        and capability.get("evidence") == "OBSERVED"
        and type(capability.get("value")) is bool
    ]
    if numeric_lux:
        aggregates["illuminance_lux"] = (sum(numeric_lux) / len(numeric_lux), "lux")
    if numeric_power:
        aggregates["power_w"] = (sum(numeric_power), "W")
    if presence:
        aggregates["presence"] = (any(presence), None)
    if light_on:
        aggregates["lighting.any_on"] = (any(light_on), None)
    boundary = _datetime(observed_at)
    for property_name, (value, unit) in aggregates.items():
        output.append(
            ObservationV1(
                id=f"{zone_id}:{property_name}:r{revision}", entity_id=zone_id,
                property=property_name, value=value, unit=unit, source=source,
                observed_at=observed_at,
                evidence_grade=EvidenceGrade.DERIVED,
                quality=1.0, coverage="all_observed_zone_devices",
            )
        )
    if presence and any(presence):
        output.append(
            ObservationV1(
                id=f"{zone_id}:presence.inactive_since:r{revision}",
                entity_id=zone_id,
                property="presence.inactive_since",
                value=None,
                unit=None,
                source=source,
                observed_at=observed_at,
                evidence_grade=EvidenceGrade.DERIVED,
                quality=1.0,
                coverage="presence_currently_active",
            )
        )
        return None
    if presence and continuous and inactive_since is None:
        inactive_since = _native_inactive_since(devices, boundary)
    if presence and continuous and inactive_since is not None:
        output.append(
            ObservationV1(
                id=f"{zone_id}:presence.inactive_since:r{revision}",
                entity_id=zone_id,
                property="presence.inactive_since",
                value=inactive_since.isoformat(),
                unit=None,
                source=source,
                observed_at=observed_at,
                evidence_grade=EvidenceGrade.DERIVED,
                quality=1.0,
                coverage="continuous_fresh_homey_observations",
            )
        )
        return inactive_since
    output.append(
        ObservationV1(
            id=f"{zone_id}:presence.inactive_since:r{revision}",
            entity_id=zone_id,
            property="presence.inactive_since",
            value=None,
            unit=None,
            source=source,
            observed_at=observed_at,
            evidence_grade=EvidenceGrade.UNKNOWN,
            coverage=(
                "fresh_sequence_not_established" if presence
                else "presence_not_observed"
            ),
        )
    )
    if not presence:
        return None
    if not continuous:
        return boundary
    return _native_inactive_since(devices, boundary)


def _restamp_observation(
    observation: TargetObservationV2, revision: int
) -> TargetObservationV2:
    return replace(
        observation,
        revision=revision,
        observations=tuple(
            replace(item, id=f"{item.entity_id}:{item.property}:r{revision}")
            for item in observation.observations
        ),
    )


def _preserve_observation_timestamps(
    current: TargetObservationV2,
    previous: TargetObservationV2,
    *,
    preserve_presence: bool,
) -> TargetObservationV2:
    previous_by_key = {
        (item.entity_id, item.property): item for item in previous.observations
    }
    observations = []
    for item in current.observations:
        prior = previous_by_key.get((item.entity_id, item.property))
        if (
            prior is not None
            and (item.property != "presence" or preserve_presence)
            and _observation_semantics(prior) == _observation_semantics(item)
        ):
            item = replace(item, observed_at=prior.observed_at)
        observations.append(item)
    return replace(current, observations=tuple(observations))


def _preserve_persisted_presence_timestamps(
    current: TargetObservationV2, presence_state: dict[str, Any]
) -> TargetObservationV2:
    stored = presence_state.get("observations", {})
    if not isinstance(stored, dict):
        return current
    observations = []
    for item in current.observations:
        prior = stored.get(item.entity_id) if item.property == "presence" else None
        if (
            isinstance(prior, dict)
            and prior.get("semantics") == _observation_semantics(item)
            and isinstance(prior.get("observed_at"), str)
        ):
            item = replace(item, observed_at=str(prior["observed_at"]))
        observations.append(item)
    return replace(current, observations=tuple(observations))


def _observation_semantics(observation: ObservationV1) -> dict[str, Any]:
    return {
        "value": observation.value,
        "source": observation.source,
        "evidence_grade": observation.evidence_grade.value,
        "quality": observation.quality,
        "coverage": observation.coverage,
        "unit": observation.unit,
        "artifact_identity": observation.artifact_identity,
    }


def _provider_presence_state(
    observation: TargetObservationV2,
    inactive_since: dict[str, datetime],
) -> dict[str, Any]:
    return {
        "inactive_since": {
            key: value.isoformat() for key, value in inactive_since.items()
        },
        "observations": {
            item.entity_id: {
                "observed_at": item.observed_at,
                "semantics": _observation_semantics(item),
            }
            for item in observation.observations
            if item.property == "presence"
        },
    }


def _persisted_inactive_since(
    presence_state: dict[str, Any],
) -> dict[str, datetime]:
    stored = presence_state.get("inactive_since", {})
    if not isinstance(stored, dict):
        raise ValueError("persisted inactive-since state must be an object")
    return {
        str(key): _datetime(str(value))
        for key, value in stored.items()
        if isinstance(value, str)
    }


def _is_continuous_observation(
    previous: datetime | None, current: datetime, freshness_seconds: float
) -> bool:
    if previous is None:
        return False
    elapsed = (current - previous).total_seconds()
    return 0 <= elapsed <= freshness_seconds


def _native_inactive_since(
    devices: list[dict[str, Any]], boundary: datetime
) -> datetime:
    candidates = []
    for device in devices:
        for capability in device.get("capabilities", ()):
            if (
                capability.get("semantic") == "presence"
                and capability.get("evidence") == "OBSERVED"
                and capability.get("value") is False
                and isinstance(capability.get("observed_at"), str)
            ):
                try:
                    candidates.append(_datetime(str(capability["observed_at"])))
                except ValueError:
                    continue
    if not candidates:
        return boundary
    return min(max(candidates), boundary)


def _quantize_sensor_value(semantic: str, value: Any) -> Any:
    step = {
        "power_w": Decimal("1"),
        "illuminance_lux": Decimal("5"),
        "temperature_c": Decimal("0.1"),
        "battery": Decimal("1"),
        "battery_percent": Decimal("1"),
    }.get(semantic)
    if step is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    number = Decimal(str(value))
    if not number.is_finite():
        return value
    rounding = {
        "illuminance_lux": ROUND_FLOOR,
        "power_w": ROUND_CEILING,
    }.get(semantic, ROUND_HALF_UP)
    multiple = (number / step).to_integral_value(rounding=rounding)
    return float(multiple * step)


def _numbers(values: Any) -> list[float]:
    return [float(item) for item in values if isinstance(item, (int, float)) and not isinstance(item, bool)]


def _value(snapshot: WorldSnapshotV2, entity_id: str, property_name: str) -> Any:
    item = next(
        (item for item in snapshot.observations if item.entity_id == entity_id and item.property == property_name),
        None,
    )
    return item.value if item else None


def _value_and_id(snapshot: WorldSnapshotV2, entity_id: str, property_name: str) -> tuple[Any, str | None]:
    item = next(
        (item for item in snapshot.observations if item.entity_id == entity_id and item.property == property_name),
        None,
    )
    return (item.value, item.id) if item else (None, None)


def _number(value: Any, default: float) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _brightness_band(value: Any) -> list[float] | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    bounded = min(1.0, max(0.0, float(value)))
    lower = int((bounded + 1e-8) / 0.05) * 0.05
    lower = round(max(0.0, lower), 2)
    upper = round(min(1.0, lower + 0.05), 2)
    return [lower, upper]


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)) and not isinstance(right, bool):
        return abs(float(left) - float(right)) <= 1e-6
    return left == right


def _select(snapshot: WorldSnapshotV2, selector: dict[str, Any]) -> tuple[EntityV1, ...]:
    ids = {str(item) for item in selector.get("entity_ids", ())}
    targets = {str(item) for item in selector.get("target_ids", ())}
    entity_type = selector.get("entity_type")
    attributes = selector.get("attributes", {})
    return tuple(
        item for item in snapshot.entities
        if (not ids or item.id in ids)
        and (not targets or item.target_id in targets)
        and (entity_type is None or item.entity_type == entity_type)
        and all(item.attributes.get(key) == value for key, value in attributes.items())
    )


def _effect_true(effect: Any, snapshot: WorldSnapshotV2, entity_id: str) -> bool:
    if effect.capability_family == LIGHTING:
        lux = _value(snapshot, entity_id, "illuminance_lux")
        power = _value(snapshot, entity_id, "power_w")
        return (
            isinstance(lux, (int, float)) and not isinstance(lux, bool)
            and isinstance(power, (int, float)) and not isinstance(power, bool)
            and float(effect.parameters["minimum_lux"]) <= float(lux)
            <= float(effect.parameters["maximum_lux"])
            and float(power) <= float(effect.parameters["max_power_w"])
        )
    if effect.capability_family == LIGHTING_ZONE_STATE:
        return _value(snapshot, entity_id, "lighting.any_on") is effect.parameters.get("on")
    property_name, expected = {
        SWITCH: ("on", effect.parameters.get("on")),
        COVER: ("cover_position", effect.parameters.get("position")),
        CLIMATE: ("thermostat_target_c", effect.parameters.get("temperature_c")),
    }[effect.capability_family]
    return _same(_value(snapshot, entity_id, property_name), expected)


def _routine_signal(
    row: dict[str, Any],
    index: int,
    suffix: str,
    target_id: str,
    zone_id: str,
    template_id: str,
    pattern_value: dict[str, Any],
    old_value: Any,
    new_value: Any,
    provenance: dict[str, Any],
) -> BehaviorSignalV1:
    return BehaviorSignalV1(
        id=f"homey-behavior:{row['id']}:{index}:routine:{suffix}",
        plugin_id="engine.homey",
        target_id=target_id,
        entity_id=zone_id,
        capability_family=(
            LIGHTING if template_id == PRESENCE_DARK_ON else LIGHTING_ZONE_STATE
        ),
        preference_id=LIGHTING_PREFERENCE,
        old_value=old_value,
        new_value=new_value,
        context={"kind": "lighting-routine", "zone_id": zone_id},
        observed_at=str(row["created_at"]),
        provenance=provenance,
        evidence_grade=EvidenceGrade.INFERRED,
        routine_template_id=template_id,
        pattern_value=pattern_value,
    )


def _target_value(
    snapshot: TargetObservationV2, entity_id: str, property_name: str
) -> Any:
    item = next(
        (
            item for item in snapshot.observations
            if item.entity_id == entity_id and item.property == property_name
            and item.evidence_grade not in {
                EvidenceGrade.UNKNOWN,
                EvidenceGrade.STALE,
                EvidenceGrade.CONFLICTING,
            }
        ),
        None,
    )
    return item.value if item is not None else None


def _minute_window_guard(
    minute: int, selector: dict[str, Any]
) -> ScopedConditionV1:
    low = minute - 15
    high = minute + 15
    if low >= 0 and high < 1440:
        return ScopedConditionV1(
            "all",
            children=(
                ScopedConditionV1(
                    "gte", selector, "observation:time.minute_of_day", low, "minute"
                ),
                ScopedConditionV1(
                    "lte", selector, "observation:time.minute_of_day", high, "minute"
                ),
            ),
        )
    ranges: list[ScopedConditionV1] = []
    if low < 0:
        ranges.extend((
            ScopedConditionV1(
                "gte", selector, "observation:time.minute_of_day", 1440 + low,
                "minute",
            ),
            ScopedConditionV1(
                "lte", selector, "observation:time.minute_of_day", high, "minute"
            ),
        ))
    else:
        ranges.extend((
            ScopedConditionV1(
                "gte", selector, "observation:time.minute_of_day", low, "minute"
            ),
            ScopedConditionV1(
                "lte", selector, "observation:time.minute_of_day", high - 1440,
                "minute",
            ),
        ))
    return ScopedConditionV1("any", children=tuple(ranges))


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
