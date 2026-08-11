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
    AutonomyEnrollmentV2,
    AutonomyModeV1,
    CognitionRouteV1,
    GoalSpecV2,
    PrivacyClass,
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
from engine.autonomy_v3 import enrollment_resource_keys
from engine.learning_v2 import BoundedPreferenceLearner

from .discovery import load_registry
from .lease import RuntimeLease, lease_status
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
        self.store.close()

    def observe(self) -> Any:
        return self.heart.observe_connected_world(refresh_targets=None)

    def store_status(self) -> Any:
        return self.store.retention_status()

    def store_prune(self, *, vacuum: bool = False) -> Any:
        boundary = datetime.now(UTC)
        pins = self.store.retention_pinned_snapshot_ids()
        summary = self.store.prune(boundary, pinned_snapshot_ids=pins)
        if vacuum:
            self.store.vacuum()
        return summary

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
            "store_bytes": self.store.database_size_bytes(),
            "lease": lease_status(self.config.store_path),
            "last_heartbeat": self.store.latest_event_payload("runtime_heartbeat"),
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
            "autonomy": self.autonomy_status(),
            "brain": self.heart.brain.id,
        }

    def autonomy_mode(self, mode: str) -> dict[str, Any]:
        return canonical_data(
            self.store.set_autonomy_mode(
                AutonomyModeV1(mode),
                changed_at=datetime.now(UTC).isoformat(),
                changed_by="local-owner-cli",
            )
        )

    def autonomy_status(self) -> dict[str, Any]:
        mode = self.store.autonomy_mode()
        return {
            "mode": canonical_data(mode),
            "enrollments": [
                canonical_data(item) for item in self.store.autonomy_enrollments()
            ],
            "proposals": [
                _binding_data(item) for item in self.store.autonomy_bindings()
            ],
            "evaluations": len(self.store.autonomy_evaluations()),
            "dispatch_attempts": [
                canonical_data(item) for item in self.store.dispatch_attempts()
            ],
            "legacy_profiles": [
                canonical_data(item) for item in self.store.autonomy_profiles()
            ],
        }

    def autonomy_strategies(self) -> tuple[Any, ...]:
        return tuple(
            item
            for manifest in self.registry.manifests
            for item in manifest.autonomy_strategies
        )

    def autonomy_strategy_inspect(self, strategy_id: str) -> Any:
        strategy = next(
            (item for item in self.autonomy_strategies() if item.id == strategy_id),
            None,
        )
        if strategy is None:
            raise KeyError(strategy_id)
        return canonical_data(strategy)

    def autonomy_enroll(
        self,
        *,
        plugin_id: str,
        strategy_id: str,
        target_ids: tuple[str, ...],
        entity_ids: tuple[str, ...],
        capability_families: tuple[str, ...],
        goal_template_ids: tuple[str, ...] = (),
        context_plugin_ids: tuple[str, ...] = (),
        privacy_grants: tuple[str, ...] = (),
        cognition_route: str | None = None,
        risk_ceiling: str = "low",
        limits: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        expires_hours: float = 24.0,
        control_existing_goals: bool = False,
        instantiate_goal_templates: bool = False,
        promote_proven_routines: bool = False,
    ) -> AutonomyEnrollmentV2:
        if expires_hours <= 0:
            raise ValueError("autonomy enrollment expiry must be positive")
        snapshot = self.observe()
        registered = self.registry.plugin(plugin_id)
        if registered.static_manifest.contract_version != "engine.plugin/v3":
            raise ValueError("generic autonomy enrollment requires engine.plugin/v3")
        strategy = self.registry.autonomy_strategy(plugin_id, strategy_id)
        if strategy is None:
            raise ValueError("unknown autonomy strategy")
        declared_strategy = next(
            (
                item
                for item in registered.static_manifest.autonomy_strategies
                if item.id == strategy_id
            ),
            None,
        )
        if declared_strategy is None or strategy.spec.to_dict() != declared_strategy.to_dict():
            raise ValueError("loaded autonomy strategy differs from its v3 manifest")
        selected_targets = tuple(dict.fromkeys(target_ids))
        selected_entities = tuple(dict.fromkeys(entity_ids))
        selected_families = tuple(dict.fromkeys(capability_families))
        selected_templates = tuple(dict.fromkeys(goal_template_ids))
        selected_contexts = tuple(dict.fromkeys(context_plugin_ids))
        selected_privacy = tuple(PrivacyClass(item) for item in privacy_grants)
        plugin_targets = {
            item.target_id for item in self.registry.providers if item.plugin_id == plugin_id
        }
        if not selected_targets or not set(selected_targets) <= plugin_targets:
            raise ValueError("autonomy targets must be exact and plugin-owned")
        entities = {item.id: item for item in snapshot.entities}
        if not selected_entities or any(
            item not in entities or entities[item].target_id not in selected_targets
            for item in selected_entities
        ):
            raise ValueError("autonomy entities must be freshly observed in target scope")
        if not selected_families or not set(selected_families) <= set(
            strategy.spec.capability_families
        ):
            raise ValueError("autonomy capability scope expands strategy declaration")
        capabilities = tuple(
            self.registry.capability(target_id, family)
            for target_id in selected_targets for family in selected_families
        )
        if any(item is None or item.plugin_id != plugin_id for item in capabilities):
            raise ValueError("autonomy capability must exist on every selected target")
        installed_plugins = {item.id for item in self.registry.manifests}
        if not set(selected_contexts) <= set(strategy.spec.context_plugin_ids):
            raise ValueError("autonomy context expands strategy declaration")
        if not set(selected_contexts) <= installed_plugins:
            raise ValueError("autonomy context plugin is not installed")
        if not set(selected_privacy) <= set(strategy.spec.privacy_classes):
            raise ValueError("autonomy privacy grant expands strategy declaration")
        risk = RiskClass(risk_ceiling)
        if risk not in {RiskClass.READ_ONLY, RiskClass.LOW}:
            raise ValueError("delegated risk cannot exceed low")
        risk_rank = {RiskClass.READ_ONLY: 0, RiskClass.LOW: 1}
        if any(
            item.risk_class not in risk_rank
            or risk_rank[item.risk_class] > risk_rank[risk]
            for item in capabilities
            if item
        ):
            raise ValueError("selected capability exceeds delegated low risk")
        manifest_templates = {
            item.id: item for item in registered.static_manifest.goal_templates
        }
        if not set(selected_templates) <= set(strategy.spec.goal_template_ids):
            raise ValueError("goal template scope expands strategy declaration")
        if not set(selected_templates) <= set(manifest_templates):
            raise ValueError("unknown goal template")
        route = CognitionRouteV1(cognition_route or strategy.spec.cognition_route.value)
        if route is not strategy.spec.cognition_route:
            raise ValueError("enrollment cognition route must match strategy declaration")
        now = datetime.now(UTC)
        enrollment = AutonomyEnrollmentV2(
            id="enrollment:" + uuid4().hex,
            revision=1,
            plugin_id=plugin_id,
            strategy_id=strategy_id,
            goal_template_ids=selected_templates,
            target_ids=selected_targets,
            entity_ids=selected_entities,
            capability_families=selected_families,
            context_plugin_ids=selected_contexts,
            privacy_grants=selected_privacy,
            cognition_route=route,
            risk_ceiling=risk,
            limits=dict(limits or {}),
            budget=dict(budget or {}),
            expires_at=(now + timedelta(hours=expires_hours)).isoformat(),
            manifest_fingerprint=registered.static_manifest.fingerprint,
            strategy_fingerprint=strategy.spec.fingerprint,
            goal_template_fingerprints={
                item: manifest_templates[item].fingerprint for item in selected_templates
            },
            enrolled_at=now.isoformat(),
            enrolled_by="local-owner-cli",
            control_existing_goals=control_existing_goals,
            instantiate_goal_templates=instantiate_goal_templates,
            promote_proven_routines=promote_proven_routines,
        )
        self.store.expire_autonomy_enrollments(boundary=now.isoformat())
        self.store.save_autonomy_enrollment(
            enrollment,
            resource_keys=enrollment_resource_keys(self.registry, enrollment),
        )
        return enrollment

    def autonomy_enrollment_inspect(self, enrollment_id: str) -> Any:
        return canonical_data(self.store.get_autonomy_enrollment(enrollment_id))

    def autonomy_enrollment_disable(self, enrollment_id: str) -> AutonomyEnrollmentV2:
        return self.store.disable_autonomy_enrollment(
            enrollment_id, revoked_at=datetime.now(UTC).isoformat()
        )

    def autonomy_proposals(self) -> tuple[dict[str, Any], ...]:
        return tuple(_binding_data(item) for item in self.store.autonomy_bindings())

    def autonomy_proposal_inspect(self, evaluation_id: str) -> dict[str, Any]:
        return _binding_data(self.store.get_autonomy_binding(evaluation_id))

    def autonomy_proposal_approve(self, evaluation_id: str) -> Any:
        return self.heart.autonomy.evaluate_for_approval(evaluation_id)

    def autonomy_proposal_reject(self, evaluation_id: str, *, reason: str) -> Any:
        return _binding_data(self.heart.autonomy.reject(evaluation_id, reason=reason))

    def yolo_alias_enable(self) -> dict[str, Any]:
        return self.autonomy_mode(AutonomyModeV1.DELEGATED.value)

    def yolo_alias_disable(self) -> dict[str, Any]:
        return self.autonomy_mode(AutonomyModeV1.PAUSED.value)

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
        lease = RuntimeLease(self.config.store_path, on_lost=on_lost)
        self.heart.set_dispatch_guard(lease.assert_current)
        return lease

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


def _binding_data(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": value["status"].value,
        "proposal_id": value["proposal_id"],
        "decision": canonical_data(value["decision"]),
        "binding": canonical_data(value["binding"]),
        "reason": value["reason"],
        "created_at": value["created_at"],
        "updated_at": value["updated_at"],
    }
