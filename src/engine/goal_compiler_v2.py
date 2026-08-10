from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from engine_sdk import (
    ConditionV1,
    DesiredEffectV1,
    GoalModeV2,
    GoalSpecV2,
    PluginManifestV2,
    WorldSnapshotV2,
    artifact_sha256,
)


class StructuredGoalModel(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def model_id(self) -> str: ...

    def compile(self, context: dict[str, object]) -> dict[str, object]: ...


class NaturalIntentCompilerV2:
    """Compiles intent to data; it cannot create or enlarge a mandate."""

    def __init__(self, model: StructuredGoalModel):
        self.model = model

    def compile(
        self,
        intent: str,
        snapshot: WorldSnapshotV2,
        manifests: tuple[PluginManifestV2, ...],
        *,
        mandate_id: str,
        goal_id: str | None = None,
        required_target_id: str | None = None,
        required_entity_id: str | None = None,
        required_capability_family: str | None = None,
    ) -> GoalSpecV2:
        available_families = sorted(
            {item.family for manifest in manifests for item in manifest.capabilities if not item.opaque}
        )
        context: dict[str, object] = {
            "contract": "engine.goal-compiler/v2",
            "source_intent": intent,
            "world": {
                "snapshot_id": snapshot.id,
                "revision": snapshot.revision,
                "entities": [item.to_dict() for item in snapshot.entities],
                "relations": [item.to_dict() for item in snapshot.relations],
                "coverage": snapshot.coverage,
            },
            "available_capability_families": available_families,
            "rules": {
                "output_is_untrusted": True,
                "mandate_is_external": mandate_id,
                "python_or_vendor_workflows_forbidden": True,
            },
        }
        selection = (
            required_target_id,
            required_entity_id,
            required_capability_family,
        )
        if any(selection):
            if not all(selection):
                raise ValueError("required goal selection must be complete")
            selected_capability = next(
                (
                    capability
                    for manifest in manifests
                    for capability in manifest.capabilities
                    if capability.family == required_capability_family
                ),
                None,
            )
            if selected_capability is None or selected_capability.opaque:
                raise ValueError("required capability family is not available")
            context["required_selection"] = {
                "target_id": required_target_id,
                "entity_id": required_entity_id,
                "capability_family": required_capability_family,
                "capability_description": selected_capability.description,
                "effect_schema": selected_capability.effect_schema,
                "effect_measurements": list(selected_capability.effect_measurements),
                "measurement_units": {
                    observation.property: observation.unit
                    for observation in snapshot.observations
                    if observation.entity_id == required_entity_id
                    and observation.property in selected_capability.effect_measurements
                    and observation.unit is not None
                },
            }
        context["input_sha256"] = artifact_sha256(context)
        raw = self.model.compile(context)
        if not isinstance(raw, dict):
            raise TypeError("goal model output must be an object")
        effects = tuple(
            DesiredEffectV1.from_dict(item)
            for item in _list_of_objects(raw, "desired_effects")
        )
        unknown = sorted({item.capability_family for item in effects} - set(available_families))
        if unknown:
            raise ValueError(f"goal proposes unknown capability families: {unknown}")
        return GoalSpecV2(
            id=goal_id or "goal:" + uuid4().hex,
            source_intent=intent,
            mode=GoalModeV2(str(raw.get("mode", "maintain"))),
            entity_scope=_object(raw, "entity_scope"),
            desired_effects=effects,
            constraints=tuple(
                ConditionV1.from_dict(item)
                for item in _list_of_objects(raw, "constraints", required=False)
            ),
            budgets=_object(raw, "budgets", required=False),
            stop_conditions=tuple(
                ConditionV1.from_dict(item)
                for item in _list_of_objects(raw, "stop_conditions", required=False)
            ),
            mandate_id=mandate_id,
            priority=int(raw.get("priority", 0)),
        )


def _object(
    value: dict[str, Any], key: str, *, required: bool = True
) -> dict[str, Any]:
    raw = value.get(key)
    if raw is None and not required:
        return {}
    if not isinstance(raw, dict):
        raise TypeError(f"{key} must be an object")
    return dict(raw)


def _list_of_objects(
    value: dict[str, Any], key: str, *, required: bool = True
) -> list[dict[str, Any]]:
    raw = value.get(key)
    if raw is None and not required:
        return []
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise ValueError(f"{key} must be a list of objects")
    return [dict(item) for item in raw]
