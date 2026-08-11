from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import jsonschema
from engine_sdk import (
    AutonomyBindingStatusV1,
    AutonomyBindingV1,
    AutonomyContextV1,
    AutonomyDecisionKindV1,
    AutonomyDecisionV1,
    AutonomyEnrollmentV2,
    AutonomyEvaluationV1,
    AutonomyModeV1,
    BrainDecisionV2,
    CognitionRouteV1,
    DecisionKindV2,
    GoalCandidateV1,
    GoalSpecV2,
    ProposedActionV1,
    RiskClass,
    SpecialistAdviceV1,
    StandingMandateV1,
    WorldSnapshotV2,
    artifact_sha256,
)


class AutonomyRuntimeV3:
    """Heart-owned scheduler for proposal-only plugin autonomy strategies."""

    def __init__(
        self,
        store: Any,
        registry: Any,
        heart: Any,
        *,
        clock: Any | None = None,
        max_entities: int = 64,
        max_observations: int = 128,
    ) -> None:
        self.store = store
        self.registry = registry
        self.heart = heart
        self._clock = clock or (lambda: datetime.now(UTC))
        self.max_entities = max_entities
        self.max_observations = max_observations

    def evaluate_cycle(
        self,
        previous: WorldSnapshotV2 | None,
        current: WorldSnapshotV2,
    ) -> set[str]:
        """Evaluate each enrollment once; return goals already handled this cycle."""
        self.store.expire_autonomy_enrollments(boundary=self._clock().isoformat())
        mode_state = self.store.autonomy_mode()
        if mode_state["mode"] is AutonomyModeV1.PAUSED:
            return set()
        stable_world = (
            previous is not None
            and _world_semantic_fingerprint(previous)
            == _world_semantic_fingerprint(current)
        )
        handled: set[str] = set()
        for enrollment in self.store.autonomy_enrollments(enabled_only=True):
            if self._enrollment_has_reserved_resource(enrollment):
                continue
            prior = self.store.autonomy_evaluations(enrollment.id)
            if (
                stable_world
                and prior
                and prior[-1].enrollment_revision == enrollment.revision
                and prior[-1].mode_epoch == int(mode_state["epoch"])
            ):
                continue
            try:
                goal_id = self._evaluate_enrollment(
                    enrollment, previous, current, mode_state=mode_state
                )
                if goal_id is not None:
                    handled.add(goal_id)
                    current = self.store.latest_world_snapshot() or current
            except Exception as exc:  # noqa: BLE001 - one plugin failure must not stop the Heart cycle
                self.store.append_event(
                    None,
                    "autonomy_evaluation_failed",
                    "heart.autonomy/v3",
                    {
                        "enrollment_id": enrollment.id,
                        "revision": enrollment.revision,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
        return handled

    def _enrollment_has_reserved_resource(
        self, enrollment: AutonomyEnrollmentV2
    ) -> bool:
        reserved = {
            (item.target_id, item.entity_id, item.conflict_domain)
            for item in self.store.dispatch_attempts(open_only=True)
        }
        return bool(set(enrollment_resource_keys(self.registry, enrollment)) & reserved)

    def evaluate_for_approval(self, evaluation_id: str) -> Any:
        pending = self.store.get_autonomy_binding(evaluation_id)
        if pending["status"] is not AutonomyBindingStatusV1.PENDING_APPROVAL:
            raise ValueError("autonomy proposal is not pending approval")
        original = self.store.get_autonomy_evaluation(evaluation_id)
        enrollment = self.store.get_autonomy_enrollment(original.enrollment_id)
        mode_state = self.store.autonomy_mode()
        if mode_state["mode"] is not AutonomyModeV1.SUPERVISED:
            raise PermissionError("approval requires current SUPERVISED mode")
        previous = self.store.latest_world_snapshot()
        current = self.heart.observe_connected_world(refresh_targets=None)
        reevaluated = self._evaluate(
            enrollment, previous, current, mode_state=mode_state
        )
        if not _same_operational_decision(original.decision, reevaluated.decision):
            self.store.set_autonomy_binding_status(
                evaluation_id,
                AutonomyBindingStatusV1.SUPERSEDED,
                reason="fresh strategy evaluation changed the operational proposal",
            )
            self._materialize(
                enrollment,
                reevaluated,
                current,
                status=AutonomyBindingStatusV1.PENDING_APPROVAL,
            )
            raise ValueError(
                "proposal changed after fresh observation; review the latest proposal"
            )
        self.store.set_autonomy_binding_status(
            evaluation_id,
            AutonomyBindingStatusV1.SUPERSEDED,
            reason=f"revalidated as {reevaluated.id}",
        )
        return self._materialize(
            enrollment,
            reevaluated,
            current,
            status=AutonomyBindingStatusV1.APPROVED,
        )

    def reject(self, evaluation_id: str, *, reason: str) -> dict[str, Any]:
        pending = self.store.get_autonomy_binding(evaluation_id)
        if pending["status"] is not AutonomyBindingStatusV1.PENDING_APPROVAL:
            raise ValueError("only a pending supervised proposal can be rejected")
        return self.store.set_autonomy_binding_status(
            evaluation_id, AutonomyBindingStatusV1.REJECTED, reason=reason
        )

    def _evaluate_enrollment(
        self,
        enrollment: AutonomyEnrollmentV2,
        previous: WorldSnapshotV2 | None,
        current: WorldSnapshotV2,
        *,
        mode_state: dict[str, Any],
    ) -> str | None:
        evaluation = self._evaluate(
            enrollment, previous, current, mode_state=mode_state
        )
        status = {
            AutonomyModeV1.OBSERVE: AutonomyBindingStatusV1.SHADOW,
            AutonomyModeV1.SUPERVISED: AutonomyBindingStatusV1.PENDING_APPROVAL,
            AutonomyModeV1.DELEGATED: AutonomyBindingStatusV1.APPROVED,
        }[mode_state["mode"]]
        return self._materialize(enrollment, evaluation, current, status=status)

    def _evaluate(
        self,
        enrollment: AutonomyEnrollmentV2,
        previous: WorldSnapshotV2 | None,
        current: WorldSnapshotV2,
        *,
        mode_state: dict[str, Any],
    ) -> AutonomyEvaluationV1:
        strategy = self.registry.autonomy_strategy(
            enrollment.plugin_id, enrollment.strategy_id
        )
        if strategy is None:
            raise ValueError("enrolled autonomy strategy is unavailable")
        self._validate_enrollment(enrollment, strategy, current)
        context = self._context(enrollment, previous, current, mode_state)
        missing_privacy = set(strategy.spec.privacy_classes) - set(
            enrollment.privacy_grants
        )
        cognition_calls = 0
        if missing_privacy:
            decision = AutonomyDecisionV1(
                AutonomyDecisionKindV1.DEFER,
                rationale="required privacy grants are missing",
            )
        else:
            try:
                decision = strategy.evaluate(context)
                if not isinstance(decision, AutonomyDecisionV1):
                    raise TypeError("strategy returned another decision contract")
            except Exception as exc:  # noqa: BLE001 - untrusted strategy output becomes a durable defer
                decision = AutonomyDecisionV1(
                    AutonomyDecisionKindV1.DEFER,
                    rationale=f"strategy failed: {type(exc).__name__}: {exc}",
                )
        if decision.kind in {
            AutonomyDecisionKindV1.REQUEST_EXECUTIVE,
            AutonomyDecisionKindV1.REQUEST_SPECIALIST,
        }:
            decision, cognition_calls = self._route_cognition(
                enrollment, context, decision, current
            )
        latest = self.store.latest_world_snapshot()
        if latest is None or latest.id != current.id:
            decision = AutonomyDecisionV1(
                AutonomyDecisionKindV1.DEFER,
                rationale="world context became stale during evaluation",
            )
        evaluation = AutonomyEvaluationV1(
            id="autonomy-evaluation:" + uuid4().hex,
            enrollment_id=enrollment.id,
            enrollment_revision=enrollment.revision,
            strategy_id=enrollment.strategy_id,
            mode=mode_state["mode"],
            mode_epoch=int(mode_state["epoch"]),
            context=context,
            decision=decision,
            strategy_fingerprint=strategy.spec.fingerprint,
            manifest_fingerprint=self.registry.manifest_fingerprint(
                enrollment.plugin_id
            ),
            cognition_calls=cognition_calls,
        )
        self.store.save_autonomy_evaluation(evaluation)
        return evaluation

    def _route_cognition(
        self,
        enrollment: AutonomyEnrollmentV2,
        context: AutonomyContextV1,
        decision: AutonomyDecisionV1,
        snapshot: WorldSnapshotV2,
    ) -> tuple[AutonomyDecisionV1, int]:
        request = decision.cognition_request
        assert request is not None
        allowed = {
            CognitionRouteV1.EXECUTIVE: {CognitionRouteV1.EXECUTIVE},
            CognitionRouteV1.SPECIALIST: {CognitionRouteV1.SPECIALIST},
            CognitionRouteV1.HYBRID: {
                CognitionRouteV1.EXECUTIVE,
                CognitionRouteV1.SPECIALIST,
            },
            CognitionRouteV1.DETERMINISTIC: set(),
        }[enrollment.cognition_route]
        if request.route not in allowed:
            return (
                AutonomyDecisionV1(
                    AutonomyDecisionKindV1.DEFER,
                    rationale="cognition request is outside the enrolled route",
                ),
                0,
            )
        strategy = self.registry.autonomy_strategy(
            enrollment.plugin_id, enrollment.strategy_id
        )
        if (
            request.route is CognitionRouteV1.SPECIALIST
            and (
                strategy is None
                or request.specialist_id != strategy.spec.specialist_id
            )
        ):
            return (
                AutonomyDecisionV1(
                    AutonomyDecisionKindV1.DEFER,
                    rationale="specialist differs from the static strategy declaration",
                ),
                0,
            )
        try:
            goal = self.store.get_goal(request.goal_id)
            if request.route is CognitionRouteV1.EXECUTIVE:
                raw = self.heart.brain.decide(goal, dict(context.projection))
                if not isinstance(raw, BrainDecisionV2):
                    raise TypeError("executive returned another decision contract")
                if raw.kind is DecisionKindV2.PROPOSE_EFFECT and raw.proposed_action:
                    routed = AutonomyDecisionV1(
                        AutonomyDecisionKindV1.PROPOSE_EFFECT,
                        proposed_action=raw.proposed_action,
                        rationale=raw.rationale,
                    )
                else:
                    routed = AutonomyDecisionV1(
                        AutonomyDecisionKindV1.DEFER,
                        rationale="executive did not return a direct effect proposal",
                    )
                brain_id = self.heart.brain.id
                purpose = "autonomy_executive"
            else:
                specialist = next(
                    (
                        item for item in self.registry.specialists()
                        if item.id == request.specialist_id
                    ),
                    None,
                )
                if specialist is None or not hasattr(specialist, "advise_autonomy"):
                    raise LookupError("v3 bounded specialist is unavailable")
                raw = specialist.advise_autonomy(context, request)
                if isinstance(raw, AutonomyDecisionV1):
                    routed = raw
                elif isinstance(raw, SpecialistAdviceV1) and raw.supported and raw.proposed_action:
                    routed = AutonomyDecisionV1(
                        AutonomyDecisionKindV1.PROPOSE_EFFECT,
                        proposed_action=raw.proposed_action,
                        rationale=raw.summary,
                    )
                else:
                    routed = AutonomyDecisionV1(
                        AutonomyDecisionKindV1.DEFER,
                        rationale="specialist did not return a supported proposal",
                    )
                brain_id = specialist.id
                purpose = "autonomy_specialist"
            self.store.record_brain_call(
                goal.id,
                brain_id,
                purpose,
                snapshot.id,
                context.projection_sha256,
                output=routed.to_dict(),
            )
            return routed, 1
        except Exception as exc:  # noqa: BLE001 - cognition/provider failure is a typed defer
            return (
                AutonomyDecisionV1(
                    AutonomyDecisionKindV1.DEFER,
                    rationale=f"cognition failed: {type(exc).__name__}: {exc}",
                ),
                1,
            )

    def _materialize(
        self,
        enrollment: AutonomyEnrollmentV2,
        evaluation: AutonomyEvaluationV1,
        snapshot: WorldSnapshotV2,
        *,
        status: AutonomyBindingStatusV1,
    ) -> str | None:
        decision = evaluation.decision
        binding = AutonomyBindingV1(
            enrollment_id=enrollment.id,
            enrollment_revision=enrollment.revision,
            evaluation_id=evaluation.id,
            mode=evaluation.mode,
            mode_epoch=evaluation.mode_epoch,
            manifest_fingerprint=evaluation.manifest_fingerprint,
            strategy_fingerprint=evaluation.strategy_fingerprint,
            context_fingerprint=evaluation.context.projection_sha256,
        )
        if decision.kind not in {
            AutonomyDecisionKindV1.PROPOSE_EFFECT,
            AutonomyDecisionKindV1.PROPOSE_GOAL_CANDIDATE,
        }:
            self.store.save_autonomy_binding(
                binding,
                decision,
                status=AutonomyBindingStatusV1.DEFERRED,
                reason=decision.rationale or decision.kind.value,
            )
            return None
        proposal_id = (
            decision.proposed_action.id if decision.proposed_action is not None else None
        )
        self.store.save_autonomy_binding(
            binding, decision, status=status, proposal_id=proposal_id
        )
        if status in {
            AutonomyBindingStatusV1.SHADOW,
            AutonomyBindingStatusV1.PENDING_APPROVAL,
        }:
            if decision.proposed_action is not None:
                shadow = replace(decision.proposed_action, autonomy_binding=binding)
                self.store.save_proposal(shadow)
            return None
        try:
            if decision.kind is AutonomyDecisionKindV1.PROPOSE_EFFECT:
                assert decision.proposed_action is not None
                if not enrollment.control_existing_goals:
                    self.store.set_autonomy_binding_status(
                        evaluation.id,
                        AutonomyBindingStatusV1.DEFERRED,
                        reason="enrollment cannot control existing goals",
                    )
                    return None
                proposal = replace(decision.proposed_action, autonomy_binding=binding)
                self._validate_proposal(enrollment, proposal, snapshot)
                self.heart.run_autonomy_proposal(
                    proposal.goal_id, proposal, binding, snapshot
                )
                return proposal.goal_id
            assert decision.goal_candidate is not None
            if not enrollment.instantiate_goal_templates:
                self.store.set_autonomy_binding_status(
                    evaluation.id,
                    AutonomyBindingStatusV1.DEFERRED,
                    reason="enrollment cannot instantiate goal templates",
                )
                return None
            goal, proposal = self._compile_goal_candidate(
                enrollment, decision.goal_candidate, evaluation.context, binding, snapshot
            )
            self.store.set_autonomy_binding_proposal(evaluation.id, proposal.id)
            self.heart.run_autonomy_proposal(goal.id, proposal, binding, snapshot)
            return goal.id
        except Exception as exc:
            self.store.set_autonomy_binding_status(
                evaluation.id,
                AutonomyBindingStatusV1.DEFERRED,
                reason=f"fresh materialization failed: {type(exc).__name__}: {exc}",
            )
            raise

    def _compile_goal_candidate(
        self,
        enrollment: AutonomyEnrollmentV2,
        candidate: GoalCandidateV1,
        context: AutonomyContextV1,
        binding: AutonomyBindingV1,
        snapshot: WorldSnapshotV2,
    ) -> tuple[GoalSpecV2, ProposedActionV1]:
        if candidate.plugin_id != enrollment.plugin_id:
            raise PermissionError("cross-plugin goal candidates are forbidden")
        if candidate.template_id not in enrollment.goal_template_ids:
            raise PermissionError("goal candidate references an unenrolled template")
        if candidate.target_id not in enrollment.target_ids or not set(
            candidate.entity_ids
        ) <= set(enrollment.entity_ids):
            raise PermissionError("goal candidate expands target/entity scope")
        if (
            candidate.based_on_snapshot_id != snapshot.id
            or candidate.based_on_world_revision != snapshot.revision
        ):
            raise ValueError("goal candidate is stale")
        template = self.registry.goal_template(
            enrollment.plugin_id, candidate.template_id
        )
        compiler = self.registry.goal_template_compiler(
            enrollment.plugin_id, candidate.template_id
        )
        if template is None or compiler is None:
            raise LookupError("goal template or compiler is unavailable")
        expected_fingerprint = enrollment.goal_template_fingerprints.get(template.id)
        if expected_fingerprint != template.fingerprint:
            raise PermissionError("goal template fingerprint changed")
        if template.risk_class not in {RiskClass.READ_ONLY, RiskClass.LOW}:
            raise PermissionError("goal template risk exceeds delegated v1")
        jsonschema.validate(candidate.parameters, template.parameter_schema)
        goal = compiler.compile(template, candidate, context)
        if not isinstance(goal, GoalSpecV2):
            raise TypeError("goal template compiler returned another contract")
        jsonschema.validate(goal.to_dict(), template.goal_schema)
        if len(goal.desired_effects) != 1:
            raise ValueError("v1 goal templates must compile exactly one desired effect")
        families = {item.capability_family for item in goal.desired_effects}
        if not families <= set(template.capability_families):
            raise PermissionError("compiled goal expands template capability scope")
        if not families <= set(enrollment.capability_families):
            raise PermissionError("compiled goal expands enrollment capability scope")
        selected_ids = {
            str(item)
            for effect in goal.desired_effects
            for item in effect.entity_selector.get("entity_ids", ())
        }
        if not selected_ids or not selected_ids <= set(enrollment.entity_ids):
            raise PermissionError("compiled goal expands enrollment entity scope")
        existing_goal = self.store.get_goal(goal.id) if self.store.has_goal(goal.id) else None
        if existing_goal is not None:
            if (
                existing_goal.desired_effects != goal.desired_effects
                or existing_goal.entity_scope != goal.entity_scope
                or existing_goal.mandate_id is None
            ):
                raise ValueError("existing autonomy goal differs from compiled template")
            existing_mandate = self.store.get_mandate(existing_goal.mandate_id)
            expected_owner = (
                f"autonomy-enrollment:{enrollment.id}:r{enrollment.revision}"
            )
            if existing_mandate.activated_by != expected_owner:
                raise PermissionError("existing goal belongs to another enrollment revision")
            goal = existing_goal
        else:
            mandate = StandingMandateV1(
                id="mandate:" + uuid4().hex,
                plugin_ids=(enrollment.plugin_id,),
                target_ids=enrollment.target_ids,
                entity_ids=enrollment.entity_ids,
                capability_families=enrollment.capability_families,
                limits=dict(enrollment.limits),
                privacy_permissions=tuple(
                    item.value for item in enrollment.privacy_grants
                ),
                learning_permissions=(
                    ("learning.low-risk",)
                    if enrollment.promote_proven_routines
                    else ()
                ),
                valid_from=self._clock().isoformat(),
                valid_until=enrollment.expires_at,
                manifest_versions={
                    enrollment.plugin_id: self.registry.plugin(
                        enrollment.plugin_id
                    ).static_manifest.version
                },
                activated_by=(
                    f"autonomy-enrollment:{enrollment.id}:r{enrollment.revision}"
                ),
            )
            goal = replace(goal, mandate_id=mandate.id)
            self.store.save_mandate(mandate)
            self.store.create_goal(goal)
        effect = goal.desired_effects[0]
        proposal = ProposedActionV1(
            id="proposal:" + uuid4().hex,
            goal_id=goal.id,
            desired_effect_id=effect.id,
            capability_family=effect.capability_family,
            target_id=candidate.target_id,
            entity_id=candidate.entity_ids[0],
            semantic_parameters=dict(effect.parameters),
            based_on_snapshot_id=snapshot.id,
            based_on_world_revision=snapshot.revision,
            proposed_by=f"goal-template:{template.id}",
            rationale=candidate.rationale or "typed goal template instantiation",
            evidence_ids=candidate.evidence_ids,
            autonomy_binding=binding,
        )
        self._validate_proposal(enrollment, proposal, snapshot)
        return goal, proposal

    def _validate_proposal(
        self,
        enrollment: AutonomyEnrollmentV2,
        proposal: ProposedActionV1,
        snapshot: WorldSnapshotV2,
    ) -> None:
        if proposal.target_id not in enrollment.target_ids:
            raise PermissionError("autonomy proposal expands target scope")
        if proposal.entity_id not in enrollment.entity_ids:
            raise PermissionError("autonomy proposal expands entity scope")
        if proposal.capability_family not in enrollment.capability_families:
            raise PermissionError("autonomy proposal expands capability scope")
        if (
            proposal.based_on_snapshot_id != snapshot.id
            or proposal.based_on_world_revision != snapshot.revision
        ):
            raise ValueError("autonomy proposal is stale")
        capability = self.registry.capability(
            proposal.target_id, proposal.capability_family
        )
        if capability is None or capability.plugin_id != enrollment.plugin_id:
            raise PermissionError("autonomy v1 cannot mutate another plugin")
        if capability.risk_class not in {RiskClass.READ_ONLY, RiskClass.LOW}:
            raise PermissionError("delegated risk cannot exceed low")
        if _risk_rank(capability.risk_class) > _risk_rank(enrollment.risk_ceiling):
            raise PermissionError("proposal risk exceeds enrollment ceiling")
        limit_error = _parameter_limits_error(
            proposal.semantic_parameters, enrollment.limits
        )
        if limit_error is not None:
            raise PermissionError(limit_error)

    def _validate_enrollment(
        self,
        enrollment: AutonomyEnrollmentV2,
        strategy: Any,
        snapshot: WorldSnapshotV2,
    ) -> None:
        now = self._clock()
        if not enrollment.enabled or _datetime(enrollment.expires_at) <= now:
            raise PermissionError("autonomy enrollment is disabled or expired")
        registered = self.registry.plugin(enrollment.plugin_id)
        if registered.static_manifest.contract_version != "engine.plugin/v3":
            raise PermissionError("only v3 plugins can be generically enrolled")
        declared_strategy = next(
            (
                item
                for item in registered.static_manifest.autonomy_strategies
                if item.id == enrollment.strategy_id
            ),
            None,
        )
        if declared_strategy is None or strategy.spec.to_dict() != declared_strategy.to_dict():
            raise PermissionError("loaded autonomy strategy differs from its manifest")
        if registered.static_manifest.fingerprint != enrollment.manifest_fingerprint:
            raise PermissionError("plugin manifest changed after enrollment")
        if strategy.spec.fingerprint != enrollment.strategy_fingerprint:
            raise PermissionError("autonomy strategy changed after enrollment")
        if strategy.spec.cognition_route is not enrollment.cognition_route:
            raise PermissionError("cognition route changed after enrollment")
        if not set(enrollment.capability_families) <= set(
            strategy.spec.capability_families
        ):
            raise PermissionError("enrollment expands strategy capability scope")
        targets = {item.target_id: item.plugin_id for item in self.registry.providers}
        if any(targets.get(item) != enrollment.plugin_id for item in enrollment.target_ids):
            raise PermissionError("enrollment target does not belong to the plugin")
        entities = {item.id: item.target_id for item in snapshot.entities}
        if any(entities.get(item) not in enrollment.target_ids for item in enrollment.entity_ids):
            raise PermissionError("enrollment entity is not freshly observed in target scope")

    def _context(
        self,
        enrollment: AutonomyEnrollmentV2,
        previous: WorldSnapshotV2 | None,
        current: WorldSnapshotV2,
        mode_state: dict[str, Any],
    ) -> AutonomyContextV1:
        allowed_sources = {enrollment.plugin_id, *enrollment.context_plugin_ids}
        exact_ids = set(enrollment.entity_ids)
        entities = tuple(
            item
            for item in current.entities
            if (
                item.id in exact_ids
                or (item.source in allowed_sources and item.source != enrollment.plugin_id)
            )
        )[: self.max_entities]
        entity_ids = {item.id for item in entities}
        relations = tuple(
            item for item in current.relations
            if item.source_entity_id in entity_ids and item.target_entity_id in entity_ids
        )
        observations = tuple(
            item for item in current.observations if item.entity_id in entity_ids
        )[: self.max_observations]
        capabilities = []
        for target_id in enrollment.target_ids:
            for capability in self.registry.capabilities_for_target(target_id):
                if capability.family in enrollment.capability_families:
                    capabilities.append(capability.to_dict())
        projection: dict[str, Any] = {
            "contract": "engine.autonomy-context/v1",
            "enrollment": {
                "id": enrollment.id,
                "revision": enrollment.revision,
                "plugin_id": enrollment.plugin_id,
                "strategy_id": enrollment.strategy_id,
                "target_ids": list(enrollment.target_ids),
                "entity_ids": list(enrollment.entity_ids),
                "capability_families": list(enrollment.capability_families),
                "goal_template_ids": list(enrollment.goal_template_ids),
                "limits": enrollment.limits,
                "budget": enrollment.budget,
                "privileges": {
                    "control_existing_goals": enrollment.control_existing_goals,
                    "instantiate_goal_templates": enrollment.instantiate_goal_templates,
                    "promote_proven_routines": enrollment.promote_proven_routines,
                },
            },
            "world": {
                "snapshot_id": current.id,
                "revision": current.revision,
                "observed_at": current.observed_at,
                "target_revisions": {
                    key: value for key, value in current.target_revisions.items()
                    if key in enrollment.target_ids
                },
                "entities": [item.to_dict() for item in entities],
                "relations": [item.to_dict() for item in relations],
                "observations": [item.to_dict() for item in observations],
                "coverage": {
                    "entities": len(entities),
                    "observations": len(observations),
                    "truncated_entities": len(entities) == self.max_entities,
                    "truncated_observations": len(observations) == self.max_observations,
                },
            },
            "capabilities": capabilities,
            "specialists": [
                {"id": item.id, "supported_families": list(item.supported_families)}
                for item in self.registry.specialists()
                if item.id == self.registry.autonomy_strategy(
                    enrollment.plugin_id, enrollment.strategy_id
                ).spec.specialist_id
            ],
        }
        fingerprint = artifact_sha256(projection)
        return AutonomyContextV1(
            enrollment_id=enrollment.id,
            enrollment_revision=enrollment.revision,
            mode=mode_state["mode"],
            mode_epoch=int(mode_state["epoch"]),
            previous_snapshot_id=previous.id if previous is not None else None,
            current_snapshot_id=current.id,
            current_world_revision=current.revision,
            projection=projection,
            projection_sha256=fingerprint,
        )


def enrollment_resource_keys(
    registry: Any, enrollment: AutonomyEnrollmentV2
) -> tuple[tuple[str, str, str], ...]:
    """Resolve generic resource identities without plugin/target branches."""
    result: set[tuple[str, str, str]] = set()
    for target_id in enrollment.target_ids:
        for family in enrollment.capability_families:
            capability = registry.capability(target_id, family)
            if capability is None or capability.plugin_id != enrollment.plugin_id:
                raise ValueError("enrollment references an unknown plugin-owned capability")
            if not capability.conflict_domain:
                raise ValueError("enrolled capability lacks conflict_domain")
            for entity_id in enrollment.entity_ids:
                result.add((target_id, entity_id, capability.conflict_domain))
    return tuple(sorted(result))


def _same_operational_decision(
    left: AutonomyDecisionV1, right: AutonomyDecisionV1
) -> bool:
    if left.kind is not right.kind:
        return False
    if left.proposed_action and right.proposed_action:
        fields = (
            "goal_id", "desired_effect_id", "capability_family", "target_id",
            "entity_id", "semantic_parameters",
        )
        return all(getattr(left.proposed_action, item) == getattr(right.proposed_action, item) for item in fields)
    if left.goal_candidate and right.goal_candidate:
        fields = ("plugin_id", "template_id", "target_id", "entity_ids", "parameters")
        return all(getattr(left.goal_candidate, item) == getattr(right.goal_candidate, item) for item in fields)
    return left.kind in {AutonomyDecisionKindV1.NOOP, AutonomyDecisionKindV1.DEFER}


def _world_semantic_fingerprint(snapshot: WorldSnapshotV2) -> str:
    return artifact_sha256(
        {
            "entities": [item.to_dict() for item in snapshot.entities],
            "relations": [
                {
                    "id": item.id,
                    "relation_type": item.relation_type,
                    "source_entity_id": item.source_entity_id,
                    "target_entity_id": item.target_entity_id,
                    "source": item.source,
                    "evidence_grade": item.evidence_grade.value,
                    "confidence": item.confidence,
                    "attributes": item.attributes,
                }
                for item in snapshot.relations
            ],
            "observations": [
                {
                    "entity_id": item.entity_id,
                    "property": item.property,
                    "value": item.value,
                    "source": item.source,
                    "evidence_grade": item.evidence_grade.value,
                    "quality": item.quality,
                    "coverage": item.coverage,
                    "unit": item.unit,
                    "artifact_identity": item.artifact_identity,
                }
                for item in snapshot.observations
            ],
        }
    )


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _risk_rank(value: RiskClass) -> int:
    return {
        RiskClass.READ_ONLY: 0,
        RiskClass.LOW: 1,
        RiskClass.MEDIUM: 2,
        RiskClass.HIGH: 3,
    }[value]


def _parameter_limits_error(
    parameters: dict[str, Any], enrollment_limits: dict[str, Any]
) -> str | None:
    raw = enrollment_limits.get("parameters", {})
    if not isinstance(raw, dict):
        return "enrollment parameter limits must be an object"
    for name, limits in raw.items():
        if name not in parameters or not isinstance(limits, dict):
            continue
        value = parameters[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if limits.get("min") is not None and value < limits["min"]:
            return f"parameter {name} is below autonomy enrollment minimum"
        if limits.get("max") is not None and value > limits["max"]:
            return f"parameter {name} exceeds autonomy enrollment maximum"
    return None
