from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import jsonschema
from engine_sdk import (
    AutonomyProfileV1,
    GoalSpecV2,
    RiskClass,
    StandingMandateV1,
    canonical_data,
)

from engine import (
    DeterministicExecutiveBrainV2,
    ModelExecutiveBrainV2,
    NaturalIntentCompilerV2,
    PluginRegistryV2,
    WorldHeartV2,
    WorldStore,
)
from engine.learning_v2 import BoundedPreferenceLearner

from .discovery import load_registry
from .lease import RuntimeLease
from .models import OpenAICompatibleV2Model


@dataclass(frozen=True)
class RuntimeConfig:
    store_path: Path = Path(".engine/engine.sqlite3")
    model_base_url: str | None = None
    model_api_key: str | None = None
    model_id: str | None = None
    model_provider_id: str = "openai-compatible"

    @classmethod
    def from_environment(cls) -> RuntimeConfig:
        local_base = os.environ.get("ENGINE_LOCAL_MODEL_BASE_URL")
        local_model = os.environ.get("ENGINE_LOCAL_MODEL_ID")
        meta_base = os.environ.get("META_MODEL_API_BASE_URL")
        meta_key = os.environ.get("META_MODEL_API_KEY")
        meta_model = os.environ.get("META_MODEL_ID")
        selected_base = (
            os.environ.get("ENGINE_MODEL_BASE_URL") or local_base or meta_base
        )
        using_local = bool(local_base or local_model) or bool(
            selected_base and _is_loopback(selected_base)
        )
        using_meta = bool(meta_base or meta_key or meta_model) and not using_local
        return cls(
            store_path=Path(
                os.environ.get("ENGINE_DATABASE", ".engine/engine.sqlite3")
            ),
            model_base_url=selected_base,
            model_api_key=os.environ.get("ENGINE_MODEL_API_KEY") or meta_key,
            model_id=(
                os.environ.get("ENGINE_MODEL_ID") or local_model or meta_model
            ),
            model_provider_id=os.environ.get(
                "ENGINE_MODEL_PROVIDER",
                (
                    "local-llama.cpp"
                    if using_local
                    else "meta-model-api"
                    if using_meta
                    else "openai-compatible"
                ),
            ),
        )


class EngineApplication:
    def __init__(
        self,
        config: RuntimeConfig,
        *,
        registry: PluginRegistryV2 | None = None,
        model: Any | None = None,
    ) -> None:
        self.config = config
        self.registry = registry or load_registry()
        self.store = WorldStore(config.store_path)
        self.model = model or self._configured_model()
        brain = (
            ModelExecutiveBrainV2(self.model)
            if self.model is not None
            else DeterministicExecutiveBrainV2()
        )
        self.learner = BoundedPreferenceLearner(self.store)
        self.heart = WorldHeartV2(
            self.store,
            self.registry,
            brain,
            learner=self.learner,
        )

    def close(self) -> None:
        try:
            self.heart.notify_lifecycle_observers()
        finally:
            self.store.close()

    def observe(self) -> Any:
        return self.heart.observe_connected_world(refresh_targets=None)

    def setup(
        self,
        *,
        plugin_id: str,
        target_id: str,
        entity_id: str,
        capability_family: str,
        preference_id: str,
        intent: str,
        activate: bool,
    ) -> dict[str, Any]:
        snapshot = self.observe()
        registered = self.registry.plugin(plugin_id)
        if target_id not in {item.target_id for item in self.registry.providers}:
            raise ValueError(f"unknown target: {target_id}")
        entity = next((item for item in snapshot.entities if item.id == entity_id), None)
        if entity is None or entity.target_id != target_id:
            raise ValueError("entity is not observed under the selected target")
        capability = self.registry.capability(target_id, capability_family)
        if capability is None or capability.plugin_id != plugin_id or capability.opaque:
            raise ValueError("unknown or observe-only capability family")
        preference = self.registry.preference(plugin_id, preference_id)
        if preference is None or preference.capability_family != capability_family:
            raise ValueError("unknown or mismatched preference")
        if self.model is None:
            raise RuntimeError(
                "engine setup requires a configured structured text model "
                "(ENGINE_MODEL_BASE_URL and ENGINE_MODEL_ID; remote providers "
                "also require ENGINE_MODEL_API_KEY)"
            )
        mandate_id = "mandate:" + uuid4().hex
        goal = NaturalIntentCompilerV2(self.model).compile(
            intent,
            snapshot,
            self.registry.manifests,
            mandate_id=mandate_id,
            required_target_id=target_id,
            required_entity_id=entity_id,
            required_capability_family=capability_family,
        )
        if any(
            item.capability_family != capability_family
            for item in goal.desired_effects
        ):
            raise ValueError("model output escaped the selected capability family")
        selectors = tuple(
            item.entity_selector for item in goal.desired_effects
        )
        if any(
            entity_id not in set(selector.get("entity_ids", ()))
            for selector in selectors
        ):
            raise ValueError("model output escaped the selected entity")
        initial_preference = _schema_seed(preference.value_schema)
        goal = replace(goal, preferences={preference_id: initial_preference})
        now = datetime.now(UTC)
        mandate = StandingMandateV1(
            id=mandate_id,
            plugin_ids=(plugin_id,),
            target_ids=(target_id,),
            entity_ids=(entity_id,),
            capability_families=(capability_family,),
            limits=dict(capability.limits),
            privacy_permissions=(capability.privacy_class.value,),
            learning_permissions=("learning.low-risk",),
            valid_from=now.isoformat(),
            valid_until=(now + timedelta(days=365)).isoformat(),
            manifest_versions={plugin_id: registered.static_manifest.version},
            activated_by="local-owner-cli",
        )
        preview = {
            "snapshot": canonical_data(snapshot),
            "goal": canonical_data(goal),
            "mandate": canonical_data(mandate),
            "activated": activate,
        }
        if activate:
            self.store.save_mandate(mandate)
            self.store.create_goal(goal)
        return preview

    def status(self) -> dict[str, Any]:
        snapshot = self.store.latest_world_snapshot()
        return {
            "store": str(self.config.store_path),
            "plugins": [item.id for item in self.registry.manifests],
            "targets": [item.target_id for item in self.registry.providers],
            "plugin_failures": self.registry.discovery_failures,
            "snapshot": canonical_data(snapshot) if snapshot else None,
            "goals": [canonical_data(item) for item in self.store.live_goals()],
            "learning": [
                canonical_data(item) for item in self.store.learning_candidates()
            ],
            "routines": [canonical_data(item) for item in self.store.routines()],
            "routine_candidates": [
                canonical_data(item) for item in self.store.routine_candidates()
            ],
            "autonomy_profiles": [
                canonical_data(item) for item in self.store.autonomy_profiles()
            ],
            "brain": self.heart.brain.id,
        }

    def yolo_enable(
        self,
        *,
        plugin_id: str = "engine.homey",
        target_id: str | None = None,
        entity_ids: tuple[str, ...] = (),
        maximum_brightness: float = 0.70,
        maximum_power_w: float = 20.0,
    ) -> AutonomyProfileV1:
        if plugin_id != "engine.homey":
            raise PermissionError("the first autonomy profile supports engine.homey only")
        snapshot = self.observe()
        registered = self.registry.plugin(plugin_id)
        providers = tuple(
            item for item in self.registry.providers if item.plugin_id == plugin_id
        )
        if target_id is None:
            if len(providers) != 1:
                raise ValueError("--target is required when a plugin has multiple targets")
            target_id = providers[0].target_id
        if target_id not in {item.target_id for item in providers}:
            raise ValueError("selected target does not belong to the Homey plugin")
        allowed_templates = {
            "lighting.daily-off/v1",
            "lighting.presence-dark-on/v1",
            "lighting.presence-absent-off/v1",
        }
        declared = {item.id for item in registered.static_manifest.routine_templates}
        if not allowed_templates <= declared:
            raise RuntimeError("installed Homey manifest lacks the fixed lighting templates")
        selected = tuple(dict.fromkeys(entity_ids))
        if not selected:
            controllable_zones = {
                str(item.attributes["zone_entity_id"])
                for item in snapshot.entities
                if item.target_id == target_id
                and item.entity_type == "homey.device"
                and item.attributes.get("kind") == "light"
                and item.attributes.get("control_allowed") is True
                and isinstance(item.attributes.get("zone_entity_id"), str)
            }
            if len(controllable_zones) != 1:
                raise ValueError(
                    "select exact --entity zone ids; implicit enrollment is allowed only for one configured zone"
                )
            selected = tuple(sorted(controllable_zones))
        observed = {
            item.id for item in snapshot.entities
            if item.target_id == target_id and item.entity_type == "homey.zone"
        }
        if not set(selected) <= observed:
            raise ValueError("autonomy entity selection contains an unobserved Homey zone")
        if any("*" in item or "?" in item or "[" in item for item in selected):
            raise ValueError("autonomy entity selection must be exact")
        if not 0 < maximum_brightness <= 1:
            raise ValueError("maximum brightness must be in (0,1]")
        if not 0 < maximum_power_w <= 20:
            raise ValueError("maximum power cannot exceed 20 W")
        if self.store.active_autonomy_profile(plugin_id, target_id) is not None:
            raise ValueError("an autonomy profile is already active for this target")
        now = datetime.now(UTC)
        profile = AutonomyProfileV1(
            id="autonomy:" + uuid4().hex,
            plugin_id=plugin_id,
            target_id=target_id,
            entity_ids=tuple(sorted(selected)),
            routine_template_ids=tuple(sorted(allowed_templates)),
            capability_families=(
                "homey.lighting.zone",
                "homey.lighting.zone-state",
            ),
            risk_ceiling=RiskClass.LOW,
            manifest_fingerprint=registered.static_manifest.fingerprint,
            limits={
                "maximum_brightness": maximum_brightness,
                "maximum_power_w": maximum_power_w,
                "minimum_cooldown_seconds": 300,
                "max_actions_per_zone_per_hour": 6,
                "max_actions_total_per_hour": 30,
                "parameters": {
                    "brightness": {"max": maximum_brightness},
                },
            },
            activated_at=now.isoformat(),
            activated_by="local-owner-cli",
        )
        self.store.save_autonomy_profile(profile)
        return profile

    def yolo_status(self) -> tuple[AutonomyProfileV1, ...]:
        return self.store.autonomy_profiles()

    def yolo_disable(self, *, profile_id: str | None = None) -> tuple[AutonomyProfileV1, ...]:
        active = self.store.autonomy_profiles(enabled_only=True)
        if profile_id is not None:
            active = tuple(item for item in active if item.id == profile_id)
            if not active:
                raise KeyError(profile_id)
        now = datetime.now(UTC).isoformat()
        return tuple(
            self.store.disable_autonomy_profile(item.id, revoked_at=now)
            for item in active
        )

    def routines_list(self) -> dict[str, Any]:
        return {
            "routines": [canonical_data(item) for item in self.store.routines()],
            "candidates": [
                canonical_data(item) for item in self.store.routine_candidates()
            ],
        }

    def routine_inspect(self, routine_or_candidate_id: str) -> dict[str, Any]:
        try:
            return {
                "kind": "routine",
                "value": canonical_data(self.store.get_routine(routine_or_candidate_id)),
            }
        except KeyError:
            return {
                "kind": "candidate",
                "value": canonical_data(
                    self.store.get_routine_candidate(routine_or_candidate_id)
                ),
                "shadow_events": [
                    canonical_data(item)
                    for item in self.store.shadow_events(routine_or_candidate_id)
                ],
            }

    def routine_approve(self, candidate_id: str) -> Any:
        candidate = self.store.get_routine_candidate(candidate_id)
        if candidate.status.value != "ready_for_approval":
            raise ValueError("routine has not passed real shadow approval gates")
        return self.heart.routine_learner.promote(
            candidate_id,
            profile=None,
            activated_by="local-owner-routine-approval",
        )

    def routine_reject(self, candidate_id: str) -> Any:
        return self.heart.routine_learner.reject(candidate_id)

    def routine_rollback(self, routine_id: str) -> None:
        self.heart.routine_learner.rollback(
            routine_id, reason="local owner requested exact rollback"
        )

    def correct(
        self, *, goal_id: str, preference_id: str, value: Any
    ) -> GoalSpecV2:
        goal = self.store.get_goal(goal_id)
        if preference_id not in goal.preferences:
            raise ValueError("goal does not declare that preference")
        spec = next(
            (
                preference
                for manifest in self.registry.manifests
                for preference in manifest.preference_specs
                if preference.id == preference_id
            ),
            None,
        )
        if spec is None:
            raise ValueError("preference is no longer declared by an installed plugin")
        jsonschema.validate(value, spec.value_schema)
        return self.learner.record_explicit_correction(
            goal,
            field_path=preference_id,
            old_value=goal.preferences[preference_id],
            new_value=value,
            context={"source": "engine learning correct"},
            observed_at=datetime.now(UTC).isoformat(),
        )

    def rollback(self, *, candidate_id: str) -> GoalSpecV2:
        candidate = self.store.get_learning_candidate(candidate_id)
        goal = self.store.get_goal(candidate.goal_id)
        rolled_back = self.learner.rollback(goal, candidate)
        if rolled_back is None:
            raise ValueError("candidate is not safely rollbackable")
        return rolled_back

    def lease(self, *, on_lost: Any | None = None) -> RuntimeLease:
        return RuntimeLease(self.config.store_path, on_lost=on_lost)

    def _configured_model(self) -> OpenAICompatibleV2Model | None:
        configured = (
            self.config.model_base_url,
            self.config.model_api_key,
            self.config.model_id,
        )
        if not any(configured):
            return None
        if not self.config.model_base_url or not self.config.model_id:
            raise RuntimeError("model configuration requires both base URL and model id")
        if not self.config.model_api_key and not _is_loopback(
            self.config.model_base_url
        ):
            raise RuntimeError("remote model providers require an API key")
        return OpenAICompatibleV2Model(
            base_url=self.config.model_base_url,
            api_key=self.config.model_api_key,
            model_id=self.config.model_id,
            provider_id=self.config.model_provider_id,
        )


def _is_loopback(base_url: str) -> bool:
    hostname = urlparse(base_url).hostname
    if hostname == "localhost":
        return True
    if hostname is None:
        return False
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def _schema_seed(schema: dict[str, Any]) -> Any:
    if "default" in schema:
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    if isinstance(schema.get("enum"), list) and schema["enum"]:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "array":
        count = int(schema.get("minItems", 1))
        return [_schema_seed(dict(schema.get("items", {}))) for _ in range(count)]
    if kind in {"number", "integer"}:
        value = schema.get("minimum", 0)
        return int(value) if kind == "integer" else float(value)
    if kind == "boolean":
        return False
    if kind == "string":
        return ""
    if kind == "object":
        properties = schema.get("properties", {})
        return {
            key: _schema_seed(dict(properties[key]))
            for key in schema.get("required", ())
            if key in properties
        }
    return None
