from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jsonschema
from engine_sdk import (
    BehaviorBatchV1,
    BrainDecisionV2,
    DecisionKindV2,
    EffectDeltaV1,
    EvidenceGrade,
    ExecutionReceiptV2,
    ExecutionStateV2,
    GoalModeV2,
    GoalSpecV2,
    PolicyOutcome,
    ProposedActionV1,
    SpecialistAdviceV1,
    WorldSnapshotV2,
    artifact_sha256,
)

from .conditions_v2 import (
    ConditionResult,
    evaluate_condition,
    evaluate_effects,
    select_entities,
)
from .context_v2 import BoundedContextProjector
from .learning_v2 import BoundedPreferenceLearner
from .plugins_v2 import PluginRegistryV2
from .policy_v2 import MandatePolicyV1
from .routines_v1 import RoutineLearnerV1, RoutineRuntimeV1
from .world_store import WorldStore


@dataclass(frozen=True)
class WorldPassV2:
    goal_id: str
    status: str
    snapshot_id: str
    brain_called: bool
    specialist_called: bool
    proposal_id: str | None = None
    request_id: str | None = None
    policy_outcome: PolicyOutcome | None = None
    receipt_id: str | None = None
    effect_id: str | None = None
    effect_achieved: bool | None = None
    reason: str = ""


class DeterministicExecutiveBrainV2:
    """Provider-free baseline sharing the exact same untrusted decision seam."""

    id = "engine.brain.deterministic-goal/v2"

    def __init__(self) -> None:
        self.calls = 0

    def decide(
        self, goal: GoalSpecV2, context_projection: dict[str, object]
    ) -> BrainDecisionV2:
        self.calls += 1
        raw_results = context_projection.get("effect_results", {})
        if not isinstance(raw_results, dict):
            return BrainDecisionV2(DecisionKindV2.WAIT, rationale="effect results unavailable")
        effect = next(
            (
                item for item in goal.desired_effects
                if isinstance(raw_results.get(item.id), dict)
                and raw_results[item.id].get("value") is False
            ),
            None,
        )
        if effect is None:
            return BrainDecisionV2(DecisionKindV2.WAIT, rationale="no observed violation")
        specialists = context_projection.get("specialists", ())
        if isinstance(specialists, (tuple, list)):
            specialist = next(
                (
                    item for item in specialists
                    if isinstance(item, dict)
                    and effect.capability_family in item.get("supported_families", ())
                ),
                None,
            )
            if specialist is not None:
                return BrainDecisionV2(
                    DecisionKindV2.CONSULT_SPECIALIST,
                    specialist_id=str(specialist["id"]),
                    query={"effect_id": effect.id},
                    rationale="A typed domain specialist covers the violated effect",
                )
        world = context_projection.get("world", {})
        if not isinstance(world, dict):
            return BrainDecisionV2(DecisionKindV2.WAIT, rationale="world projection unavailable")
        entities = world.get("entities", ())
        entity = _projected_entity(effect.entity_selector, entities)
        if entity is None:
            return BrainDecisionV2(DecisionKindV2.QUERY_WORLD, query={"effect_id": effect.id}, rationale="No scoped entity is observed")
        result = raw_results[effect.id]
        proposal = ProposedActionV1(
            id="proposal:" + uuid4().hex,
            goal_id=goal.id,
            desired_effect_id=effect.id,
            capability_family=effect.capability_family,
            target_id=str(entity["target_id"]),
            entity_id=str(entity["id"]),
            semantic_parameters=dict(effect.parameters),
            based_on_snapshot_id=str(world["snapshot_id"]),
            based_on_world_revision=int(world["revision"]),
            proposed_by=self.id,
            rationale="Deterministic baseline selected the first observed violated effect",
            evidence_ids=tuple(str(item) for item in result.get("evidence_ids", ())),
        )
        return BrainDecisionV2(DecisionKindV2.PROPOSE_EFFECT, proposed_action=proposal)


class WorldHeartV2:
    """Living multi-target cycle; cognition is invoked only on meaningful change."""

    def __init__(
        self,
        store: WorldStore,
        registry: PluginRegistryV2,
        brain: Any,
        *,
        projector: BoundedContextProjector | None = None,
        policy: MandatePolicyV1 | None = None,
        clock: Any | None = None,
        learner: BoundedPreferenceLearner | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.brain = brain
        self.projector = projector or BoundedContextProjector()
        self.policy = policy or MandatePolicyV1()
        self._clock = clock or (lambda: datetime.now(UTC))
        self.learner = learner or BoundedPreferenceLearner(store)
        self.routine_runtime = RoutineRuntimeV1(
            store, registry, clock=self._clock
        )
        self.routine_learner = RoutineLearnerV1(
            store, registry, clock=self._clock
        )

    def run_once(
        self,
        goal_id: str,
        *,
        refresh_targets: set[str] | None = None,
        snapshot: WorldSnapshotV2 | None = None,
        previous_snapshot: WorldSnapshotV2 | None = None,
    ) -> WorldPassV2:
        supplied = snapshot is not None
        previous = (
            previous_snapshot if supplied else self.store.latest_world_snapshot()
        )
        goal = self.store.get_goal(goal_id)
        if snapshot is None:
            snapshot = self.observe_world(goal, refresh_targets=refresh_targets)
        evaluations = self.routine_runtime.evaluate(
            snapshot, previous=previous
        )
        evaluation = evaluations.get(goal_id)
        if evaluation is not None and not evaluation.allowed:
            self.store.append_event(
                goal_id,
                "routine_gate",
                "engine.routines/v1",
                {
                    "routine_id": evaluation.routine_id,
                    "status": evaluation.status.value,
                    "reason": evaluation.reason,
                    "evidence_ids": list(evaluation.evidence_ids),
                },
            )
            return WorldPassV2(
                goal_id,
                evaluation.status.value,
                snapshot.id,
                False,
                False,
                reason=evaluation.reason,
            )
        result = self._run_goal_once(
            goal_id,
            refresh_targets=refresh_targets,
            snapshot=snapshot,
            previous_snapshot=previous,
        )
        if evaluation is not None:
            self.routine_runtime.note_result(
                evaluation,
                status=result.status,
                snapshot_id=result.snapshot_id,
                request_id=result.request_id,
                entity_id=self.store.get_routine(evaluation.routine_id).entity_ids[0],
            )
        return result

    def _run_goal_once(
        self,
        goal_id: str,
        *,
        refresh_targets: set[str] | None = None,
        snapshot: WorldSnapshotV2 | None = None,
        previous_snapshot: WorldSnapshotV2 | None = None,
    ) -> WorldPassV2:
        goal = self.store.get_goal(goal_id)
        supplied_snapshot = snapshot is not None
        previous = (
            previous_snapshot
            if supplied_snapshot
            else self.store.latest_world_snapshot()
        )
        if snapshot is None:
            snapshot = self.observe_world(goal, refresh_targets=refresh_targets)
        stop = self._stop_condition(goal, snapshot, previous)
        if stop is True:
            self.store.set_goal_status(goal.id, "abandoned")
            return WorldPassV2(goal.id, "abandoned", snapshot.id, False, False, reason="typed stop condition reached")
        results = evaluate_effects(goal, snapshot, previous=previous)
        pending_task = self.store.pending_task(goal.id)
        if pending_task is not None:
            return self._resume_task(goal, pending_task, snapshot)
        if _all_true(results):
            status = "completed" if goal.mode is GoalModeV2.ACHIEVE else "monitoring"
            self.store.set_goal_status(goal.id, status)
            self.store.append_event(goal.id, "stable", "heart.v2", {
                "snapshot_id": snapshot.id,
                "effect_results": _results_payload(results),
                "brain_calls": 0,
            })
            return WorldPassV2(goal.id, status, snapshot.id, False, False, reason="all desired effects are observed")
        if (
            not supplied_snapshot
            and refresh_targets is not None
            and set(refresh_targets)
            != {item.target_id for item in self.registry.providers}
        ):
            # A cheap per-target poll found drift. Re-observe the whole relevant
            # boundary before cognition or mutation so reused targets cannot be stale.
            previous = snapshot
            snapshot = self.observe_world(goal, refresh_targets=None)
            results = evaluate_effects(goal, snapshot, previous=previous)
            if _all_true(results):
                status = "completed" if goal.mode is GoalModeV2.ACHIEVE else "monitoring"
                self.store.set_goal_status(goal.id, status)
                return WorldPassV2(goal.id, status, snapshot.id, False, False, reason="full refresh found stable state")
        if any(item.value is None for item in results.values()):
            self.store.set_goal_status(goal.id, "uncertain")
            self.store.append_event(goal.id, "evidence_unknown", "heart.v2", {
                "snapshot_id": snapshot.id,
                "effect_results": _results_payload(results),
            })
            return WorldPassV2(goal.id, "uncertain", snapshot.id, False, False, reason="required effect evidence is unknown")

        violated = next(effect for effect in goal.desired_effects if results[effect.id].value is False)
        selected = select_entities(snapshot, violated.entity_selector)
        target_id = selected[0].target_id if selected else ""
        plugin_id = self.registry.plugin_for_target(target_id).static_manifest.id if target_id else ""
        cache_key = self._plan_cache_key(goal, violated.id, selected)
        mandate = self._mandate(goal)
        cached = None
        cache_allowed = len(selected) == 1
        if cache_allowed and plugin_id and mandate is not None:
            cached = self.store.load_plan(
                cache_key, self.registry.manifest_fingerprint(plugin_id), mandate.id
            )
        brain_called = False
        specialist_called = False
        if cached is not None:
            proposal = ProposedActionV1(
                id="proposal:" + uuid4().hex,
                goal_id=goal.id,
                desired_effect_id=str(cached["desired_effect_id"]),
                capability_family=str(cached["capability_family"]),
                target_id=str(cached["target_id"]),
                entity_id=str(cached["entity_id"]),
                semantic_parameters=dict(cached["semantic_parameters"]),
                based_on_snapshot_id=snapshot.id,
                based_on_world_revision=snapshot.revision,
                proposed_by="engine.plan-cache/v2",
                rationale="Reuse of an observed successful typed plan",
                evidence_ids=results[violated.id].evidence_ids,
            )
        else:
            projection = self._projection(goal, snapshot, results)
            started = time.perf_counter()
            decision = self.brain.decide(goal, projection)
            elapsed = (time.perf_counter() - started) * 1000
            brain_called = True
            self.store.record_brain_call(
                goal.id, self.brain.id, "executive", snapshot.id,
                str(projection["projection_sha256"]), output=decision.to_dict(),
                latency_ms=elapsed,
            )
            proposal, specialist_called = self._proposal_from_decision(
                decision, goal, snapshot, projection
            )
            if proposal is None:
                status = "waiting" if decision.kind is not DecisionKindV2.ABANDON else "abandoned"
                self.store.set_goal_status(goal.id, status)
                return WorldPassV2(
                    goal.id, status, snapshot.id, brain_called, specialist_called,
                    reason=decision.rationale or decision.kind.value,
                )

        self.store.save_proposal(proposal)
        invalid = self._proposal_error(proposal, goal, snapshot)
        if invalid is not None:
            self.store.append_event(goal.id, "proposal_rejected", "heart.v2", {
                "proposal_id": proposal.id, "reason": invalid,
            })
            self.store.set_goal_status(goal.id, "waiting")
            return WorldPassV2(
                goal.id, "waiting", snapshot.id, brain_called, specialist_called,
                proposal_id=proposal.id, reason=invalid,
            )
        capability = self.registry.capability(proposal.target_id, proposal.capability_family)
        if capability is None or capability.opaque:
            reason = "capability family is unknown or observe-only"
            self.store.append_event(goal.id, "proposal_rejected", "heart.v2", {"proposal_id": proposal.id, "reason": reason})
            return WorldPassV2(goal.id, "waiting", snapshot.id, brain_called, specialist_called, proposal_id=proposal.id, reason=reason)
        try:
            jsonschema.validate(proposal.semantic_parameters, capability.effect_schema)
            controller = self.registry.controller(capability.plugin_id, capability.family)
            request = controller.concretize(proposal, snapshot, capability)
            self._validate_request(request, proposal, capability, snapshot)
        except Exception as exc:
            reason = f"request validation failed: {type(exc).__name__}: {exc}"
            self.store.append_event(goal.id, "request_rejected", "heart.v2", {"proposal_id": proposal.id, "reason": reason})
            self.store.set_goal_status(goal.id, "waiting")
            return WorldPassV2(goal.id, "waiting", snapshot.id, brain_called, specialist_called, proposal_id=proposal.id, reason=reason)
        self.store.save_request(request)
        registered = self.registry.plugin_for_target(request.target_id)
        decision = self.policy.evaluate(
            request, capability, mandate,
            manifest_version=registered.static_manifest.version,
            now=self._clock(),
        )
        self.store.save_policy_decision(decision)
        if decision.outcome is not PolicyOutcome.ALLOW:
            self.store.set_goal_status(goal.id, "waiting")
            return WorldPassV2(
                goal.id, "waiting", snapshot.id, brain_called, specialist_called,
                proposal.id, request.id, decision.outcome,
                reason="; ".join(decision.reasons),
            )
        assert mandate is not None
        authorization = self.policy.authorize(request, decision, mandate)
        self.store.save_authorization(authorization)
        requested_at = self._clock().isoformat()
        try:
            receipt = self.registry.executor(capability.plugin_id).dispatch(request, authorization)
            self._validate_receipt(receipt, request, authorization.id)
        except Exception as exc:
            receipt = ExecutionReceiptV2(
                id="receipt:" + uuid4().hex,
                request_id=request.id,
                authorization_id=authorization.id,
                target_id=request.target_id,
                capability_id=request.capability_id,
                state=ExecutionStateV2.UNKNOWN,
                requested_at=requested_at,
                completed_at=self._clock().isoformat(),
                acknowledged=None,
                error=f"{type(exc).__name__}: {exc}",
                adapter_version=registered.static_manifest.version,
            )
        self.store.save_receipt(receipt)
        post_state = self.observe_world(goal, refresh_targets=None)
        try:
            effect = self.registry.oracle(capability.plugin_id, capability.family).reconcile(
                proposal, snapshot, receipt, post_state
            )
            self._validate_effect(effect, proposal, request.id, receipt.id, snapshot.id, post_state.id)
        except Exception as exc:
            effect = EffectDeltaV1(
                id="effect:" + uuid4().hex,
                goal_id=goal.id, proposal_id=proposal.id, request_id=request.id,
                receipt_id=receipt.id, pre_snapshot_id=snapshot.id,
                post_snapshot_id=post_state.id, evidence_grade=EvidenceGrade.UNKNOWN,
                achieved=None, changes={}, measurement_observation_ids=(),
                reason=f"effect oracle failed: {type(exc).__name__}: {exc}",
                observed_at=post_state.observed_at,
            )
        self.store.save_effect(effect)
        post_results = evaluate_effects(goal, post_state, previous=snapshot)
        if _all_true(post_results):
            status = "completed" if goal.mode is GoalModeV2.ACHIEVE else "monitoring"
        elif any(item.value is None for item in post_results.values()):
            status = "uncertain"
        elif receipt.state in {ExecutionStateV2.ACCEPTED, ExecutionStateV2.RUNNING}:
            status = "waiting"
            self._schedule_task_wake(goal.id, request, receipt)
        else:
            status = "active"
        self.store.set_goal_status(goal.id, status)
        if cache_allowed and effect.achieved is True and mandate is not None:
            self.store.save_plan(
                cache_key, goal.id, capability.plugin_id, capability.family,
                registered.static_manifest.fingerprint, mandate.id,
                {
                    "desired_effect_id": proposal.desired_effect_id,
                    "capability_family": proposal.capability_family,
                    "target_id": proposal.target_id,
                    "entity_id": proposal.entity_id,
                    "semantic_parameters": proposal.semantic_parameters,
                },
                {"effect_id": effect.id, "achieved": True, "post_snapshot_id": post_state.id},
            )
        return WorldPassV2(
            goal.id, status, post_state.id, brain_called, specialist_called,
            proposal.id, request.id, decision.outcome, receipt.id, effect.id,
            effect.achieved, effect.reason,
        )

    def _resume_task(
        self,
        goal: GoalSpecV2,
        pending: dict[str, Any],
        observed_snapshot: WorldSnapshotV2,
    ) -> WorldPassV2:
        proposal: ProposedActionV1 = pending["proposal"]
        request = pending["request"]
        authorization = pending["authorization"]
        previous_receipt: ExecutionReceiptV2 = pending["receipt"]
        handle = previous_receipt.external_handle
        if not handle:
            self.store.set_goal_status(goal.id, "uncertain")
            return WorldPassV2(
                goal.id, "uncertain", observed_snapshot.id, False, False,
                proposal.id, request.id, PolicyOutcome.ALLOW,
                receipt_id=previous_receipt.id,
                reason="nonterminal task receipt has no external handle",
            )
        executor = self.registry.executor(request.plugin_id)
        now = self._clock()
        deadline = _datetime(request.deadline_at)
        try:
            receipt = (
                executor.cancel(handle)
                if now >= deadline
                else executor.poll(handle)
            )
            self._validate_receipt(receipt, request, authorization.id)
        except Exception as exc:
            reason = f"task recovery deferred: {type(exc).__name__}: {exc}"
            self.store.append_event(
                goal.id, "task_poll_failed", request.plugin_id,
                {"request_id": request.id, "reason": reason},
            )
            self.store.set_goal_status(goal.id, "waiting")
            self._schedule_task_wake(goal.id, request, previous_receipt)
            return WorldPassV2(
                goal.id, "waiting", observed_snapshot.id, False, False,
                proposal.id, request.id, PolicyOutcome.ALLOW,
                receipt_id=previous_receipt.id, reason=reason,
            )
        self.store.save_receipt(receipt)
        post_state = self.observe_world(goal, refresh_targets=None)
        capability = self.registry.capability(
            request.target_id, request.capability_family
        )
        if capability is None:
            raise RuntimeError("pending task capability disappeared")
        pre_state = self.store.world_snapshot(proposal.based_on_snapshot_id)
        try:
            effect = self.registry.oracle(
                request.plugin_id, request.capability_family
            ).reconcile(proposal, pre_state, receipt, post_state)
            self._validate_effect(
                effect, proposal, request.id, receipt.id,
                pre_state.id, post_state.id,
            )
        except Exception as exc:
            effect = EffectDeltaV1(
                id="effect:" + uuid4().hex,
                goal_id=goal.id,
                proposal_id=proposal.id,
                request_id=request.id,
                receipt_id=receipt.id,
                pre_snapshot_id=pre_state.id,
                post_snapshot_id=post_state.id,
                evidence_grade=EvidenceGrade.UNKNOWN,
                achieved=None,
                changes={},
                measurement_observation_ids=(),
                reason=f"effect oracle failed during task recovery: {type(exc).__name__}: {exc}",
                observed_at=post_state.observed_at,
            )
        self.store.save_effect(effect)
        results = evaluate_effects(goal, post_state, previous=observed_snapshot)
        if receipt.state in {ExecutionStateV2.ACCEPTED, ExecutionStateV2.RUNNING}:
            status = "waiting"
            self._schedule_task_wake(goal.id, request, receipt)
        elif _all_true(results):
            status = "completed" if goal.mode is GoalModeV2.ACHIEVE else "monitoring"
        elif any(item.value is None for item in results.values()):
            status = "uncertain"
        else:
            status = "active"
        self.store.set_goal_status(goal.id, status)
        mandate = self._mandate(goal)
        if effect.achieved is True and mandate is not None:
            desired_effect = next(
                item for item in goal.desired_effects
                if item.id == proposal.desired_effect_id
            )
            selected = select_entities(pre_state, desired_effect.entity_selector)
            if len(selected) == 1:
                registered = self.registry.plugin_for_target(request.target_id)
                self.store.save_plan(
                    self._plan_cache_key(goal, desired_effect.id, selected),
                    goal.id,
                    capability.plugin_id,
                    capability.family,
                    registered.static_manifest.fingerprint,
                    mandate.id,
                    {
                        "desired_effect_id": proposal.desired_effect_id,
                        "capability_family": proposal.capability_family,
                        "target_id": proposal.target_id,
                        "entity_id": proposal.entity_id,
                        "semantic_parameters": proposal.semantic_parameters,
                    },
                    {
                        "effect_id": effect.id,
                        "achieved": True,
                        "post_snapshot_id": post_state.id,
                    },
                )
        return WorldPassV2(
            goal.id, status, post_state.id, False, False,
            proposal.id, request.id, PolicyOutcome.ALLOW,
            receipt.id, effect.id, effect.achieved, effect.reason,
        )

    def _schedule_task_wake(
        self,
        goal_id: str,
        request: Any,
        receipt: ExecutionReceiptV2,
    ) -> None:
        provider = next(
            item for item in self.registry.providers
            if item.target_id == request.target_id
        )
        now = self._clock()
        deadline = _datetime(request.deadline_at)
        wake_at = min(
            deadline,
            now + timedelta(seconds=max(0.01, provider.poll_interval_seconds)),
        )
        self.store.schedule_wake(
            "wake:" + uuid4().hex,
            wake_at.isoformat(),
            "poll_task",
            goal_id=goal_id,
            target_id=request.target_id,
            payload={"external_handle": receipt.external_handle},
        )

    @staticmethod
    def _plan_cache_key(
        goal: GoalSpecV2,
        effect_id: str,
        selected: tuple[Any, ...],
    ) -> str:
        effect = next(item for item in goal.desired_effects if item.id == effect_id)
        return artifact_sha256({
            "goal_id": goal.id,
            "goal_version": goal.version,
            "effect_id": effect.id,
            "entity_ids": [item.id for item in selected],
            "condition": effect.condition.to_dict(),
        })

    def observe_world(
        self,
        goal: GoalSpecV2,
        *,
        refresh_targets: set[str] | None,
    ) -> WorldSnapshotV2:
        del goal
        return self.observe_connected_world(refresh_targets=refresh_targets)

    def observe_connected_world(
        self, *, refresh_targets: set[str] | None = None
    ) -> WorldSnapshotV2:
        providers = self.registry.providers
        failures: dict[str, str] = {}
        for provider in providers:
            if refresh_targets is not None and provider.target_id not in refresh_targets:
                continue
            try:
                observation = provider.observe()
                if observation.target_id != provider.target_id:
                    raise ValueError("provider returned another target identity")
                self.store.save_target_observation(observation)
            except Exception as exc:
                failures[provider.target_id] = f"{type(exc).__name__}: {exc}"
        entities = []
        relations = []
        observations = []
        target_revisions: dict[str, int] = {}
        coverage: dict[str, Any] = {"targets": {}, "failures": failures}
        boundary = self._clock()
        for provider in providers:
            latest = self.store.latest_target_observation(provider.target_id)
            if latest is None:
                coverage["targets"][provider.target_id] = {"available": None, "reason": failures.get(provider.target_id, "never observed")}
                continue
            target_revisions[provider.target_id] = latest.revision
            failed = provider.target_id in failures
            stale = failed or _age_seconds(latest.observed_at, boundary) > provider.freshness_seconds
            entities.extend(latest.entities)
            relations.extend(latest.relations)
            observations.extend(
                replace(item, evidence_grade=EvidenceGrade.STALE) if stale else item
                for item in latest.observations
            )
            coverage["targets"][provider.target_id] = {
                "available": False if failed else latest.available,
                "revision": latest.revision,
                "stale": stale,
                "coverage": latest.coverage,
            }
        if len({item.id for item in entities}) != len(entities):
            raise ValueError("entity identity collision across target providers")
        revision = self.store.next_world_revision()
        snapshot = WorldSnapshotV2(
            id=f"world:{revision}", revision=revision,
            observed_at=boundary.isoformat(), target_revisions=target_revisions,
            entities=tuple(sorted(entities, key=lambda item: item.id)),
            relations=tuple(sorted(relations, key=lambda item: item.id)),
            observations=tuple(sorted(observations, key=lambda item: item.id)),
            coverage=coverage,
        )
        self.store.save_world_snapshot(snapshot)
        return snapshot

    def run_cycle(
        self,
        *,
        refresh_targets: set[str] | None = None,
    ) -> tuple[WorldPassV2, ...]:
        """Run one plugin-neutral world boundary and every due durable concern."""
        previous = self.store.latest_world_snapshot()
        snapshot = self.observe_connected_world(refresh_targets=refresh_targets)
        self._import_experience(snapshot)
        self._advance_learning(snapshot)
        due_wakes = self.store.due_wakes(self._clock().isoformat())
        passes: list[WorldPassV2] = []
        current_snapshot = self.store.latest_world_snapshot() or snapshot
        for goal in self.store.live_goals():
            try:
                result = self.run_once(
                    goal.id,
                    snapshot=current_snapshot,
                    previous_snapshot=previous,
                )
            except Exception as exc:
                reason = f"isolated goal failure: {type(exc).__name__}: {exc}"
                self.store.append_event(
                    goal.id,
                    "goal_cycle_failed",
                    "heart.v2",
                    {"snapshot_id": current_snapshot.id, "reason": reason},
                )
                self.store.set_goal_status(goal.id, "degraded")
                result = WorldPassV2(
                    goal.id,
                    "degraded",
                    current_snapshot.id,
                    False,
                    False,
                    reason=reason,
                )
            passes.append(result)
            current_snapshot = self.store.latest_world_snapshot() or current_snapshot
            previous = current_snapshot
        self.store.mark_wakes_handled(tuple(str(item["id"]) for item in due_wakes))
        return tuple(passes)

    def _import_experience(self, snapshot: WorldSnapshotV2) -> None:
        for provider in self.registry.experience_providers:
            try:
                self._import_provider_experience(provider, snapshot)
            except Exception as exc:
                self.store.append_event(
                    None,
                    "experience_provider_failed",
                    str(getattr(provider, "plugin_id", "unknown")),
                    {
                        "provider_id": str(getattr(provider, "id", "unknown")),
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )

    def _import_provider_experience(
        self, provider: Any, snapshot: WorldSnapshotV2
    ) -> None:
        cursor = self.store.plugin_cursor(provider.id)
        for _page in range(100):
            batch = provider.read(cursor, 100)
            if not isinstance(batch, BehaviorBatchV1):
                raise TypeError("experience provider returned another batch contract")
            if batch.has_more and batch.cursor == cursor:
                raise ValueError("experience provider did not advance a paged cursor")
            valid_signals = tuple(
                item for item in batch.signals if item.plugin_id == provider.plugin_id
            )
            if len(valid_signals) != len(batch.signals):
                self.store.append_event(
                    None,
                    "behavior_signal_rejected",
                    provider.plugin_id,
                    {"reason": "signal plugin identity mismatch"},
                )
            persisted = self.store.save_behavior_batch(
                provider.id,
                provider.plugin_id,
                BehaviorBatchV1(batch.cursor, valid_signals, batch.has_more),
            )
            for signal in persisted:
                self._link_behavior_signal(signal, snapshot)
            cursor = batch.cursor
            if not batch.has_more:
                return
        raise RuntimeError("experience provider exceeded 100 batches in one cycle")

    def _link_behavior_signal(self, signal: Any, snapshot: WorldSnapshotV2) -> None:
        try:
            candidate = self.routine_learner.ingest_signal(signal, snapshot)
            if signal.routine_template_id is not None:
                self.store.append_event(
                    None,
                    "routine_behavior_signal",
                    signal.plugin_id,
                    {
                        "signal_id": signal.id,
                        "template_id": signal.routine_template_id,
                        "candidate_id": candidate.id if candidate is not None else None,
                    },
                )
        except Exception as exc:
            if signal.routine_template_id is not None:
                self.store.append_event(
                    None,
                    "routine_behavior_signal_rejected",
                    signal.plugin_id,
                    {
                        "signal_id": signal.id,
                        "template_id": signal.routine_template_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
        spec = self.registry.preference(signal.plugin_id, signal.preference_id)
        registered = self.registry.plugin(signal.plugin_id)
        capability_known = any(
            item.family == signal.capability_family
            for item in registered.static_manifest.capabilities
        )
        if spec is None or not capability_known:
            self.store.link_behavior_signal(
                signal.id,
                goal_id=None,
                status="unlinked",
                reason=(
                    "unknown preference"
                    if spec is None else "unknown capability family"
                ),
            )
            return
        try:
            jsonschema.validate(signal.new_value, spec.value_schema)
        except Exception as exc:
            self.store.link_behavior_signal(
                signal.id,
                goal_id=None,
                status="invalid",
                reason=f"preference value schema mismatch: {exc}",
            )
            return
        matched = False
        for goal in self.store.live_goals():
            if signal.preference_id not in goal.preferences:
                continue
            effects = tuple(
                item
                for item in goal.desired_effects
                if item.capability_family == signal.capability_family
                and any(
                    entity.id == signal.entity_id
                    and entity.target_id == signal.target_id
                    for entity in select_entities(snapshot, item.entity_selector)
                )
            )
            if not effects:
                continue
            mandate = self._mandate(goal)
            if mandate is None:
                self.store.link_behavior_signal(
                    signal.id,
                    goal_id=goal.id,
                    status="unlinked",
                    reason="goal has no standing mandate",
                )
                continue
            self.learner.record_signal(goal, signal)
            self.store.link_behavior_signal(
                signal.id,
                goal_id=goal.id,
                status="linked",
                reason="target, entity, capability, selector and preference matched",
            )
            self.learner.candidate_for_preference(
                goal,
                spec,
                mandate,
                target_id=signal.target_id,
                entity_id=signal.entity_id,
            )
            matched = True
        if not matched and not self.store.behavior_signal_links(signal.id):
            self.store.link_behavior_signal(
                signal.id,
                goal_id=None,
                status="unlinked",
                reason="no active GoalSpec matched the signal scope",
            )

    def _advance_learning(self, snapshot: WorldSnapshotV2) -> None:
        self.routine_learner.advance(snapshot)
        for candidate in self.store.learning_candidates(
            statuses=("shadow",)
        ):
            try:
                goal = self.store.get_goal(candidate.goal_id)
                mandate = self._mandate(goal)
                if mandate is None or "learning.low-risk" not in mandate.learning_permissions:
                    continue
                if (
                    candidate.plugin_id is not None
                    and candidate.preference_id is not None
                    and self.registry.preference(
                        candidate.plugin_id, candidate.preference_id
                    )
                    is None
                ):
                    continue
                promoted = self.learner.advance_shadow(
                    goal, candidate, now=self._clock()
                )
                if promoted is not None:
                    self.store.append_event(
                        goal.id,
                        "preference_promoted",
                        "engine.learning/v2",
                        {
                            "candidate_id": candidate.id,
                            "preference_id": candidate.preference_id,
                            "goal_version": promoted.version,
                        },
                    )
            except Exception as exc:
                self.store.append_event(
                    candidate.goal_id,
                    "learning_candidate_failed",
                    "engine.learning/v2",
                    {"candidate_id": candidate.id, "error": str(exc)},
                )

    def run_forever(
        self,
        stop_event: threading.Event,
        *,
        max_passes: int | None = None,
    ) -> int:
        wake = threading.Event()
        subscriptions: list[Any] = []
        event_targets: set[str] = set()
        lock = threading.Lock()
        next_poll = {
            provider.target_id: time.monotonic()
            for provider in self.registry.providers
        }

        def callback(target_id: str) -> Any:
            def mark(*_args: Any, **_kwargs: Any) -> None:
                with lock:
                    event_targets.add(target_id)
                wake.set()
            return mark

        try:
            for provider in self.registry.providers:
                try:
                    unsubscribe = provider.subscribe(callback(provider.target_id))
                except Exception as exc:
                    self.store.append_event(None, "subscription_failed", provider.plugin_id, {"target_id": provider.target_id, "error": str(exc)})
                    continue
                if unsubscribe is not None:
                    subscriptions.append(unsubscribe)
            passes = 0
            while not stop_event.is_set() and (max_passes is None or passes < max_passes):
                now = time.monotonic()
                due = {target_id for target_id, deadline in next_poll.items() if now >= deadline}
                with lock:
                    due.update(event_targets)
                    event_targets.clear()
                next_durable_wake = self.store.next_wake_at()
                scheduled_due = (
                    next_durable_wake is not None
                    and _datetime(next_durable_wake) <= self._clock()
                )
                if due or scheduled_due:
                    self.run_cycle(refresh_targets=due)
                    passes += 1
                    for provider in self.registry.providers:
                        if provider.target_id in due:
                            next_poll[provider.target_id] = now + provider.poll_interval_seconds
                    wake.clear()
                    continue
                timeout = max(0.01, min(next_poll.values(), default=now + 1) - now)
                next_wake = self.store.next_wake_at()
                if next_wake is not None:
                    timeout = min(
                        timeout,
                        max(0.01, (_datetime(next_wake) - self._clock()).total_seconds()),
                    )
                wake.wait(timeout=min(timeout, 1.0))
            return passes
        finally:
            for unsubscribe in reversed(subscriptions):
                try:
                    unsubscribe()
                except Exception:
                    pass

    def _providers_for_goal(self, goal: GoalSpecV2) -> tuple[Any, ...]:
        del goal
        # Heart owns the connected-world boundary. Goal scope constrains effects
        # and brain projection, not which connected facts are durable locally.
        return self.registry.providers

    def _projection(
        self,
        goal: GoalSpecV2,
        snapshot: WorldSnapshotV2,
        results: dict[str, ConditionResult],
    ) -> dict[str, object]:
        capabilities = tuple(
            item.to_dict()
            for provider in self._providers_for_goal(goal)
            for item in self.registry.capabilities_for_target(provider.target_id)
        )
        specialists = tuple({
            "id": item.id,
            "supported_families": list(item.supported_families),
        } for item in self.registry.specialists())
        return self.projector.project(
            goal, snapshot, results,
            capabilities=capabilities, specialists=specialists,
        )

    def _proposal_from_decision(
        self,
        decision: BrainDecisionV2,
        goal: GoalSpecV2,
        snapshot: WorldSnapshotV2,
        projection: dict[str, object],
    ) -> tuple[ProposedActionV1 | None, bool]:
        if decision.kind is DecisionKindV2.PROPOSE_EFFECT:
            return decision.proposed_action, False
        if decision.kind is not DecisionKindV2.CONSULT_SPECIALIST:
            return None, False
        specialist = next(
            (item for item in self.registry.specialists() if item.id == decision.specialist_id),
            None,
        )
        if specialist is None:
            return None, False
        started = time.perf_counter()
        advice: SpecialistAdviceV1 = specialist.advise(goal, snapshot, decision.query)
        elapsed = (time.perf_counter() - started) * 1000
        self.store.record_brain_call(
            goal.id, specialist.id, "specialist", snapshot.id,
            str(projection["projection_sha256"]), output=advice.to_dict(),
            latency_ms=elapsed,
        )
        return advice.proposed_action if advice.supported else None, True

    def _proposal_error(
        self, proposal: ProposedActionV1, goal: GoalSpecV2, snapshot: WorldSnapshotV2
    ) -> str | None:
        if proposal.goal_id != goal.id:
            return "proposal is bound to another goal"
        if proposal.based_on_snapshot_id != snapshot.id or proposal.based_on_world_revision != snapshot.revision:
            return "proposal is stale"
        effect = next((item for item in goal.desired_effects if item.id == proposal.desired_effect_id), None)
        if effect is None:
            return "proposal references an unknown desired effect"
        if proposal.capability_family != effect.capability_family:
            return "proposal changed the declared capability family"
        entities = {item.id: item for item in select_entities(snapshot, effect.entity_selector)}
        entity = entities.get(proposal.entity_id)
        if entity is None or entity.target_id != proposal.target_id:
            return "proposal entity is outside the goal effect scope"
        return None

    def _validate_request(self, request: Any, proposal: ProposedActionV1, capability: Any, snapshot: WorldSnapshotV2) -> None:
        if request.proposal_id != proposal.id or request.goal_id != proposal.goal_id:
            raise ValueError("controller changed proposal/goal identity")
        if request.target_id != proposal.target_id or request.entity_id != proposal.entity_id:
            raise ValueError("controller changed target/entity identity")
        if request.capability_id != capability.id or request.capability_family != capability.family:
            raise ValueError("controller selected another capability")
        if request.snapshot_id != snapshot.id or request.world_revision != snapshot.revision:
            raise ValueError("request is not bound to current world snapshot")
        if request.target_revision != int(snapshot.target_revisions.get(request.target_id, -1)):
            raise ValueError("request target revision is stale")
        jsonschema.validate(request.parameters, capability.input_schema)
        for condition in (*capability.preconditions, *request.preconditions):
            result = evaluate_condition(condition, snapshot, selector={"entity_ids": [request.entity_id]})
            if result.value is not True:
                raise ValueError(f"precondition is not true: {result.reason}")

    @staticmethod
    def _validate_receipt(receipt: ExecutionReceiptV2, request: Any, authorization_id: str) -> None:
        if receipt.request_id != request.id or receipt.authorization_id != authorization_id:
            raise ValueError("executor receipt identity mismatch")
        if receipt.target_id != request.target_id or receipt.capability_id != request.capability_id:
            raise ValueError("executor receipt target/capability mismatch")
        if (
            receipt.state in {ExecutionStateV2.ACCEPTED, ExecutionStateV2.RUNNING}
            and not receipt.external_handle
        ):
            raise ValueError("nonterminal task receipt requires external_handle")

    @staticmethod
    def _validate_effect(
        effect: EffectDeltaV1, proposal: ProposedActionV1, request_id: str,
        receipt_id: str, pre_snapshot_id: str, post_snapshot_id: str,
    ) -> None:
        if (
            effect.proposal_id != proposal.id or effect.goal_id != proposal.goal_id
            or effect.request_id != request_id or effect.receipt_id != receipt_id
            or effect.pre_snapshot_id != pre_snapshot_id
            or effect.post_snapshot_id != post_snapshot_id
        ):
            raise ValueError("effect oracle returned mismatched lifecycle identity")

    def _mandate(self, goal: GoalSpecV2) -> Any | None:
        if goal.mandate_id is None:
            return None
        try:
            return self.store.get_mandate(goal.mandate_id)
        except KeyError:
            return None

    @staticmethod
    def _stop_condition(
        goal: GoalSpecV2,
        snapshot: WorldSnapshotV2,
        previous: WorldSnapshotV2 | None,
    ) -> bool | None:
        if not goal.stop_conditions:
            return False
        results = tuple(
            evaluate_condition(item, snapshot, selector=goal.entity_scope, previous=previous)
            for item in goal.stop_conditions
        )
        if any(item.value is True for item in results):
            return True
        return None if any(item.value is None for item in results) else False


def _all_true(results: dict[str, ConditionResult]) -> bool:
    return bool(results) and all(item.value is True for item in results.values())


def _results_payload(results: dict[str, ConditionResult]) -> dict[str, Any]:
    return {
        key: {
            "value": item.value, "grade": item.grade.value,
            "evidence_ids": list(item.evidence_ids), "reason": item.reason,
        }
        for key, item in results.items()
    }


def _projected_entity(selector: dict[str, Any], entities: object) -> dict[str, Any] | None:
    if not isinstance(entities, (list, tuple)):
        return None
    ids = {str(item) for item in selector.get("entity_ids", ())}
    targets = {str(item) for item in selector.get("target_ids", ())}
    wanted_type = selector.get("entity_type")
    attributes = selector.get("attributes", {})
    for item in entities:
        if not isinstance(item, dict):
            continue
        if ids and item.get("id") not in ids:
            continue
        if targets and item.get("target_id") not in targets:
            continue
        if wanted_type is not None and item.get("entity_type") != wanted_type:
            continue
        raw_attributes = item.get("attributes", {})
        if isinstance(attributes, dict) and any(raw_attributes.get(key) != value for key, value in attributes.items()):
            continue
        return item
    return None


def _age_seconds(value: str, now: datetime) -> float:
    return max(0.0, (now - _datetime(value)).total_seconds())


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
