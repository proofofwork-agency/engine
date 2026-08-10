from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from .catalog import CapabilityValidationError, Catalog, CatalogError
from .interfaces import ExecutiveBrain, SpecialistBrain, TargetAdapter
from .models import (
    BrainContext,
    BrainDecision,
    BrainRequest,
    BrainResult,
    DecisionKind,
    Goal,
    GoalMode,
    InvocationReceipt,
    InvocationMode,
    InvocationState,
    JsonObject,
    SpecialistAdvice,
    ToolCall,
    ToolResult,
    WorldSnapshot,
)
from .store import EngineStore


class AdapterContractError(ValueError):
    """An adapter returned a value that cannot enter Engine's durable log."""


@dataclass(frozen=True)
class RunResult:
    goal: Goal
    cycles_executed: int
    final_snapshot: WorldSnapshot | None


class Heart:
    """The persistent, target-agnostic heartbeat of Engine.

    Heart owns the loop, goal continuity, context construction, brain invocation,
    world-tool invocation, observations, and experience. Brains choose; Heart
    keeps the living process coherent across model calls and process restarts.
    """

    suspended_statuses = frozenset(
        {"monitoring", "waiting", "uncertain", "degraded"}
    )
    uncertainty_memory_key = "oracle_uncertainty"

    def __init__(
        self,
        store: EngineStore,
        executive: ExecutiveBrain,
        catalog: Catalog,
        experience_window: int = 30,
        capability_limit: int = 32,
        require_specialist_first: bool = False,
    ):
        self.store = store
        self.executive = executive
        self.catalog = catalog
        self.experience_window = experience_window
        self.capability_limit = capability_limit
        self.require_specialist_first = require_specialist_first
        self._sync_catalog()

    def register_goal(self, goal: Goal) -> Goal:
        if not self.store.has_goal(goal.id):
            self.store.create_goal(goal)
        return self.store.get_goal(goal.id)

    def pulse(
        self,
        step_limit: int | None = None,
    ) -> RunResult | None:
        """Advance the highest-priority live goal without a human step."""
        goals = self.store.live_goals()
        if not goals:
            return None
        return self.run(goals[0].id, step_limit=step_limit)

    def run(
        self,
        goal_id: str,
        step_limit: int | None = None,
    ) -> RunResult:
        goal = self.store.get_goal(goal_id)
        self._sync_catalog()
        target = self.catalog.target(goal.target_id)
        if target.manifest.id != goal.target_id:
            raise ValueError(
                f"goal target {goal.target_id} does not match adapter {target.manifest.id}"
            )
        cycles_executed = 0
        final_snapshot = self.store.latest_snapshot(goal_id)

        if goal.status in self.suspended_statuses:
            goal, final_snapshot = self._refresh_suspended_goal(
                goal, target, final_snapshot
            )
            if goal.status != "active":
                return RunResult(
                    goal=goal,
                    cycles_executed=0,
                    final_snapshot=final_snapshot,
                )

        while goal.status == "active":
            self._sync_catalog()
            budget_cycle = (
                goal.intervention_cycle
                if goal.mode is GoalMode.MAINTAIN
                else goal.cycle
            )
            if budget_cycle >= goal.max_cycles:
                event_kind = (
                    "intervention_budget_exhausted"
                    if goal.mode is GoalMode.MAINTAIN
                    else "budget_exhausted"
                )
                self.store.append_event(
                    goal.id,
                    goal.cycle,
                    event_kind,
                    "heart",
                    {
                        "max_cycles": goal.max_cycles,
                        "intervention_cycle": goal.intervention_cycle,
                    },
                )
                goal = self.store.set_goal_status(
                    goal.id,
                    (
                        "degraded"
                        if goal.mode is GoalMode.MAINTAIN
                        else "budget_exhausted"
                    ),
                )
                break
            if step_limit is not None and cycles_executed >= step_limit:
                break

            snapshot = self._observe(target, previous=final_snapshot)
            final_snapshot = snapshot
            self._record_observation(goal, snapshot)
            oracle = self._oracle_result(goal, target, snapshot)
            if oracle is True:
                goal = self._settle_goal(
                    goal, snapshot, "oracle satisfied before cognition"
                )
                break
            if oracle is None:
                goal = self._enter_oracle_uncertainty(
                    goal,
                    snapshot,
                    resume_status="active",
                    wake_pending=True,
                )
                break

            context = self._build_context(goal, snapshot, target)
            executive_request, _, decision = self._invoke_executive(context)
            self.store.append_event(
                goal.id,
                goal.cycle,
                "executive_decision",
                self.executive.manifest.qualified_id,
                {
                    "brain_request_id": executive_request.id,
                    "decision": decision.to_dict(),
                },
            )

            rejection = self._decision_rejection(decision, context)
            if rejection is not None:
                self.store.append_event(
                    goal.id,
                    goal.cycle,
                    "decision_rejected",
                    "heart",
                    {
                        "brain_request_id": executive_request.id,
                        "reason": rejection,
                        "decision": decision.to_dict(),
                        "cognitive_phase": context.cognitive_phase,
                    },
                )
                cycles_executed += 1
                goal = self.store.advance_cycle(goal.id)
                continue

            terminal = self._apply_decision(
                goal,
                snapshot,
                decision,
                executive_request.id,
                context,
                target,
            )
            cycles_executed += 1
            if terminal is not None:
                goal, final_snapshot = terminal
                break
            goal = self.store.advance_cycle(goal.id)

        return RunResult(goal=goal, cycles_executed=cycles_executed, final_snapshot=final_snapshot)

    def _refresh_suspended_goal(
        self,
        goal: Goal,
        target: TargetAdapter,
        previous: WorldSnapshot | None,
    ) -> tuple[Goal, WorldSnapshot]:
        """Observe a quiet goal and wake cognition only for meaningful change."""
        snapshot = self._observe(target, previous=previous)
        observed_changed = previous is None or (
            snapshot.revision != previous.revision or snapshot.state != previous.state
        )
        relevant_changed = previous is None or self._goal_relevant_change(
            goal, target, previous, snapshot
        )
        if observed_changed:
            self._record_observation(goal, snapshot)
            if not relevant_changed:
                self.store.append_event(
                    goal.id,
                    goal.cycle,
                    "goal_change_ignored",
                    "heart",
                    {
                        "reason": "adapter marked snapshot change goal-irrelevant",
                        "revision": snapshot.revision,
                    },
                )

        resume_status = goal.status
        wake_pending = relevant_changed
        uncertainty = self.store.load_memory(goal.id).get(
            self.uncertainty_memory_key
        )
        if goal.status == "uncertain" and isinstance(uncertainty, dict):
            candidate = str(uncertainty.get("resume_status", "active"))
            if candidate in {"active", "monitoring", "waiting", "degraded"}:
                resume_status = candidate
            else:
                resume_status = "active"
            wake_pending = bool(uncertainty.get("wake_pending")) or relevant_changed

        oracle = self._oracle_result(goal, target, snapshot)
        if oracle is None:
            return (
                self._enter_oracle_uncertainty(
                    goal,
                    snapshot,
                    resume_status=resume_status,
                    wake_pending=wake_pending,
                ),
                snapshot,
            )
        self.store.delete_memory(goal.id, self.uncertainty_memory_key)
        if oracle:
            if goal.mode is GoalMode.MAINTAIN:
                if observed_changed or goal.status != "monitoring":
                    goal = self._settle_goal(
                        goal, snapshot, "maintained state observed"
                    )
                return goal, snapshot
            goal = self._complete(goal, snapshot, "waiting goal became satisfied")
            return goal, snapshot

        should_wake = (
            resume_status in {"active", "monitoring"}
            or relevant_changed
            or wake_pending
        )
        if not should_wake:
            if goal.status == "uncertain":
                goal = self.store.set_goal_status(goal.id, resume_status)
            return goal, snapshot

        self.store.delete_memory(goal.id, "specialist_results")
        event_kind = (
            "goal_drifted" if resume_status == "monitoring" else "goal_woken"
        )
        self.store.append_event(
            goal.id,
            goal.cycle,
            event_kind,
            "heart",
            {
                "previous_status": resume_status,
                "revision": snapshot.revision,
            },
        )
        return (
            self.store.transition_goal(
                goal.id,
                "active",
                reset_intervention=resume_status != "active",
            ),
            snapshot,
        )

    def _enter_oracle_uncertainty(
        self,
        goal: Goal,
        snapshot: WorldSnapshot,
        *,
        resume_status: str,
        wake_pending: bool,
    ) -> Goal:
        existing = self.store.load_memory(goal.id).get(self.uncertainty_memory_key)
        if isinstance(existing, dict):
            resume_status = str(existing.get("resume_status", resume_status))
            wake_pending = bool(existing.get("wake_pending")) or wake_pending
        self.store.set_memory(
            goal.id,
            self.uncertainty_memory_key,
            {
                "resume_status": resume_status,
                "wake_pending": wake_pending,
                "snapshot_revision": snapshot.revision,
            },
        )
        if goal.status != "uncertain":
            self.store.append_event(
                goal.id,
                goal.cycle,
                "goal_uncertain",
                "heart",
                {
                    "reason": "target oracle unavailable",
                    "resume_status": resume_status,
                    "snapshot_revision": snapshot.revision,
                },
            )
            return self.store.set_goal_status(goal.id, "uncertain")
        return goal

    def _goal_relevant_change(
        self,
        goal: Goal,
        target: TargetAdapter,
        previous: WorldSnapshot,
        current: WorldSnapshot,
    ) -> bool:
        relevance = getattr(target, "goal_relevant_change", None)
        if not callable(relevance):
            return previous.state != current.state
        try:
            result = relevance(goal, previous, current)
            if type(result) is not bool:
                raise AdapterContractError(
                    "goal_relevant_change must return an exact bool"
                )
            return result
        except Exception as error:
            self.store.append_event(
                goal.id,
                goal.cycle,
                "change_relevance_error",
                target.manifest.id,
                {"error": f"{type(error).__name__}: {error}"},
            )
            return True

    def _build_context(
        self, goal: Goal, snapshot: WorldSnapshot, target: TargetAdapter
    ) -> BrainContext:
        universe = self.catalog.capabilities(target.manifest.id)
        terms = tuple(
            token.strip(".,:;!?()[]{}").casefold()
            for token in goal.instruction.split()
            if len(token.strip(".,:;!?()[]{}")) >= 3
        )
        search = self.catalog.search(
            target.manifest.id, terms, limit=self.capability_limit
        )
        selected_ids = {item.capability_id for item in search.selections}
        selection_strategy = "lexical"
        if not search.retrieval_sufficient:
            specialist_supported = {
                capability_id
                for specialist in self.catalog.specialists.values()
                for capability_id in specialist.manifest.supported_capabilities
            }.intersection(item.id for item in universe)
            if specialist_supported and len(specialist_supported) <= self.capability_limit:
                selected_ids = specialist_supported
                selection_strategy = "specialist-affinity-fallback"
        self.store.append_event(
            goal.id,
            goal.cycle,
            "catalog_selection",
            "engine.catalog.lexical/v1",
            {
                "catalog_generation": self.catalog.generation,
                "catalog_fingerprint": self.catalog.fingerprint(),
                "candidate_universe": [item.id for item in universe],
                "shortlist": [item.to_dict() for item in search.selections],
                "limit": self.capability_limit,
                "selection_strategy": selection_strategy,
                "selection_complete": search.complete,
                "omitted_count": search.omitted_count,
                "max_score": search.max_score,
                "retrieval_sufficient": (
                    search.retrieval_sufficient
                    or selection_strategy == "specialist-affinity-fallback"
                ),
            },
        )
        memory = self.store.load_memory(goal.id)
        pending = tuple(
            item
            for item in memory.get("specialist_results", [])
            if isinstance(item, dict)
            and item.get("snapshot_revision") == snapshot.revision
        )
        cognitive_phase = "advice_ready" if pending else "needs_specialist"
        return BrainContext(
            goal=goal,
            snapshot=snapshot,
            capabilities=tuple(item for item in universe if item.id in selected_ids),
            specialists=tuple(
                specialist.manifest
                for _, specialist in sorted(self.catalog.specialists.items())
                if set(specialist.manifest.supported_capabilities).intersection(
                    item.id for item in universe
                )
            ),
            recent_experience=self.store.recent_events(
                goal.id, limit=self.experience_window
            ),
            working_memory=memory,
            specialist_performance=self.store.brain_performance(
                target.manifest.plugin_id
            ),
            catalog_generation=self.catalog.generation,
            catalog_fingerprint=self.catalog.fingerprint(),
            cognitive_phase=cognitive_phase,
            pending_advice=pending,
        )

    def _apply_decision(
        self,
        goal: Goal,
        snapshot: WorldSnapshot,
        decision: BrainDecision,
        decision_request_id: str,
        context: BrainContext,
        target: TargetAdapter,
    ) -> tuple[Goal, WorldSnapshot] | None:
        if decision.kind is DecisionKind.CONSULT_BRAIN:
            try:
                specialist = self.catalog.specialist(decision.name or "")
            except CatalogError:
                self.store.append_event(
                    goal.id,
                    goal.cycle,
                    "brain_error",
                    "heart",
                    {"error": "unknown specialist", "name": decision.name},
                )
                return None
            specialist_context = replace(
                context, specialist_query=dict(decision.arguments)
            )
            request, result, advice = self._invoke_specialist(
                specialist, specialist_context, parent_request_id=decision_request_id
            )
            values = self._specialist_results(goal.id)
            query_sha256 = self._hash(dict(decision.arguments))
            value = {
                "brain_request_id": request.id,
                "specialist": specialist.manifest.qualified_id,
                "snapshot_revision": snapshot.revision,
                "advice": advice.to_dict(),
                "latency_ms": result.latency_ms,
                "query_sha256": query_sha256,
            }
            values = [
                item
                for item in values
                if not (
                    item.get("specialist") == specialist.manifest.qualified_id
                    and item.get("snapshot_revision") == snapshot.revision
                    and item.get("query_sha256") == query_sha256
                )
            ]
            values.append(value)
            self.store.set_memory(goal.id, "specialist_results", values)
            self.store.record_brain_consult(
                specialist.manifest.qualified_id,
                target.manifest.plugin_id,
                result.latency_ms,
            )
            self.store.append_event(
                goal.id,
                goal.cycle,
                "specialist_result",
                specialist.manifest.qualified_id,
                value,
            )
            if advice.suggested_action is None and not advice.complete:
                self._record_brain_outcome(
                    goal,
                    target,
                    specialist.manifest.qualified_id,
                    "*",
                    effectful=False,
                    reason="specialist returned no actionable or complete result",
                    brain_request_id=request.id,
                    invocation_id=None,
                )
            return None

        if decision.kind is DecisionKind.USE_TOOL:
            selected_advice = self._selected_advice(goal.id, decision.based_on)
            if any(item["snapshot_revision"] != snapshot.revision for item in selected_advice):
                self.store.delete_memory(goal.id, "specialist_results")
                self.store.append_event(
                    goal.id,
                    goal.cycle,
                    "stale_advice_rejected",
                    "heart",
                    {
                        "based_on": list(decision.based_on),
                        "snapshot_revision": snapshot.revision,
                    },
                )
                return None

            call = ToolCall(
                decision.name or "", decision.arguments, target_id=target.manifest.id
            )
            invocation_id = uuid.uuid4().hex
            requested_at = datetime.now(UTC).isoformat()
            requested = InvocationReceipt(
                id=invocation_id,
                goal_id=goal.id,
                target_id=target.manifest.id,
                capability_id=call.capability_id,
                state=InvocationState.REQUESTED,
                requested_at=requested_at,
                snapshot_revision=snapshot.revision,
                decision_request_id=decision_request_id,
                based_on=decision.based_on,
            )
            self.store.append_event(
                goal.id,
                goal.cycle,
                "invocation",
                "heart",
                requested.to_dict(),
            )
            try:
                capability = self.catalog.validate_call(target.manifest.id, call)
            except (CatalogError, CapabilityValidationError) as error:
                result = ToolResult(False, False, error=str(error))
                self._record_terminal_invocation(requested, goal, result)
                self._record_tool_result(
                    goal, target, call, result, snapshot, None, invocation_id
                )
                self._apply_advice_outcomes(
                    goal,
                    target,
                    selected_advice,
                    call.capability_id,
                    effectful=False,
                    reason="capability input rejected before dispatch",
                    invocation_id=invocation_id,
                )
                self.store.delete_memory(goal.id, "specialist_results")
                return None

            invocation_mode = getattr(
                capability.invocation_mode, "value", capability.invocation_mode
            )
            if invocation_mode != InvocationMode.IMMEDIATE.value:
                result = ToolResult(
                    False,
                    False,
                    error=(
                        f"NOT_SUPPORTED: invocation mode "
                        f"{capability.invocation_mode.value} requires a task/stream provider"
                    ),
                )
                self._record_terminal_invocation(requested, goal, result)
                self._record_tool_result(
                    goal, target, call, result, snapshot, None, invocation_id
                )
                self._apply_advice_outcomes(
                    goal,
                    target,
                    selected_advice,
                    call.capability_id,
                    effectful=False,
                    reason="non-immediate invocation unsupported by prototype heart",
                    invocation_id=invocation_id,
                )
                self.store.delete_memory(goal.id, "specialist_results")
                return None

            terminal_state: InvocationState | None = None
            post_snapshot: WorldSnapshot | None = None
            try:
                raw_result = target.execute(call)
                result = self._validate_tool_result(raw_result)
                try:
                    post_snapshot = self._observe(target, previous=snapshot)
                except Exception as observation_error:
                    result = ToolResult(
                        False,
                        result.changed,
                        output=result.output,
                        error=(
                            "UNKNOWN: post-observation failed after dispatch: "
                            f"{type(observation_error).__name__}: {observation_error}"
                        ),
                        partial=result.changed,
                    )
                    terminal_state = InvocationState.UNKNOWN
            except Exception as execution_error:
                try:
                    post_snapshot = self._observe(target, previous=snapshot)
                except Exception:
                    post_snapshot = None
                observed_change = bool(
                    post_snapshot is not None
                    and (
                        post_snapshot.revision != snapshot.revision
                        or post_snapshot.state != snapshot.state
                    )
                )
                result = ToolResult(
                    False,
                    observed_change,
                    error=(
                        "UNKNOWN: adapter dispatch/result contract failed; effect is "
                        f"not acknowledged: {type(execution_error).__name__}: "
                        f"{execution_error}"
                    ),
                    partial=observed_change,
                )
                terminal_state = InvocationState.UNKNOWN

            if post_snapshot is not None:
                self._record_observation(goal, post_snapshot)
            if result.succeeded:
                try:
                    self.catalog.validate_output(
                        target.manifest.id, call.capability_id, result.output
                    )
                except CapabilityValidationError as error:
                    result = ToolResult(
                        False,
                        result.changed,
                        output=result.output,
                        error=f"adapter output schema violation: {error}",
                        partial=result.changed,
                    )
            self._record_terminal_invocation(
                requested, goal, result, state=terminal_state
            )
            self._record_tool_result(
                goal,
                target,
                call,
                result,
                snapshot,
                post_snapshot,
                invocation_id,
            )
            effectful = result.changed or bool(
                post_snapshot is not None
                and post_snapshot.revision != snapshot.revision
            )
            self._apply_advice_outcomes(
                goal,
                target,
                selected_advice,
                call.capability_id,
                effectful=effectful,
                reason=(
                    "observed world effect"
                    if effectful
                    else "no observed world effect"
                ),
                invocation_id=invocation_id,
            )
            self.store.delete_memory(goal.id, "specialist_results")
            if post_snapshot is not None:
                oracle = self._oracle_result(goal, target, post_snapshot)
                if oracle is True:
                    settled = self._settle_goal(
                        goal, post_snapshot, "post-state oracle satisfied"
                    )
                    return settled, post_snapshot
                if oracle is None:
                    uncertain = self._enter_oracle_uncertainty(
                        goal,
                        post_snapshot,
                        resume_status="active",
                        wake_pending=True,
                    )
                    return uncertain, post_snapshot
            return None

        if decision.kind is DecisionKind.COMPLETE:
            oracle = self._oracle_result(goal, target, snapshot)
            if oracle is True:
                settled = self._settle_goal(
                    goal, snapshot, "brain requested verified completion"
                )
                return settled, snapshot
            self.store.delete_memory(goal.id, "specialist_results")
            self.store.append_event(
                goal.id,
                goal.cycle,
                "completion_rejected",
                "heart",
                {
                    "reason": (
                        "target oracle is unavailable"
                        if oracle is None
                        else "target oracle is not satisfied"
                    )
                },
            )
            if oracle is None:
                uncertain = self._enter_oracle_uncertainty(
                    goal,
                    snapshot,
                    resume_status="active",
                    wake_pending=True,
                )
                return uncertain, snapshot
            return None

        if decision.kind is DecisionKind.WAIT:
            self.store.append_event(
                goal.id,
                goal.cycle,
                "wait",
                "heart",
                {
                    "reason": decision.rationale,
                    "snapshot_revision": snapshot.revision,
                },
            )
            self.store.delete_memory(goal.id, "specialist_results")
            waiting = self.store.advance_cycle(goal.id)
            waiting = self.store.set_goal_status(waiting.id, "waiting")
            return waiting, snapshot

        self.store.append_event(
            goal.id,
            goal.cycle,
            "goal_abandoned",
            self.executive.manifest.qualified_id,
            {"reason": decision.rationale},
        )
        abandoned = self.store.set_goal_status(goal.id, "abandoned")
        return abandoned, snapshot

    def _record_observation(self, goal: Goal, snapshot: WorldSnapshot) -> None:
        self.store.save_snapshot(goal.id, goal.cycle, snapshot)
        self.store.append_event(
            goal.id,
            goal.cycle,
            "observation",
            snapshot.target_id,
            snapshot.to_dict(),
        )

    def _complete(self, goal: Goal, snapshot: WorldSnapshot, reason: str) -> Goal:
        self.store.append_event(
            goal.id,
            goal.cycle,
            "goal_completed",
            "heart",
            {"reason": reason, "revision": snapshot.revision},
        )
        self.store.delete_memory(goal.id, "specialist_results")
        self.store.delete_memory(goal.id, self.uncertainty_memory_key)
        return self.store.set_goal_status(goal.id, "completed")

    def _settle_goal(self, goal: Goal, snapshot: WorldSnapshot, reason: str) -> Goal:
        if goal.mode is GoalMode.ACHIEVE:
            return self._complete(goal, snapshot, reason)
        self.store.append_event(
            goal.id,
            goal.cycle,
            "goal_monitoring",
            "heart",
            {"reason": reason, "revision": snapshot.revision},
        )
        self.store.delete_memory(goal.id, "specialist_results")
        self.store.delete_memory(goal.id, self.uncertainty_memory_key)
        return self.store.transition_goal(
            goal.id, "monitoring", reset_intervention=True
        )

    def _invoke_executive(
        self, context: BrainContext
    ) -> tuple[BrainRequest, BrainResult, BrainDecision]:
        request = self._brain_request(
            context,
            self.executive.manifest.qualified_id,
            "select next cognitive operator",
        )
        started = time.perf_counter()
        try:
            decision = self.executive.decide(context)
            if not isinstance(decision, BrainDecision):
                decision = BrainDecision.from_dict(decision.to_dict())
        except Exception as error:
            self._brain_result(
                request,
                status="failed",
                output={"error": f"{type(error).__name__}: {error}"},
                started=started,
                usage=dict(getattr(self.executive, "last_usage", {})),
            )
            raise
        result = self._brain_result(
            request,
            status="succeeded",
            output=decision.to_dict(),
            started=started,
            usage=dict(getattr(self.executive, "last_usage", {})),
        )
        return request, result, decision

    def _invoke_specialist(
        self,
        specialist: SpecialistBrain,
        context: BrainContext,
        parent_request_id: str,
    ) -> tuple[BrainRequest, BrainResult, SpecialistAdvice]:
        request = self._brain_request(
            context,
            specialist.manifest.qualified_id,
            "resolve bounded cognitive impasse",
            parent_request_id=parent_request_id,
        )
        started = time.perf_counter()
        try:
            advice = specialist.advise(context)
            if not isinstance(advice, SpecialistAdvice):
                advice = SpecialistAdvice.from_dict(advice.to_dict())
        except Exception as error:
            self._brain_result(
                request,
                status="failed",
                output={"error": f"{type(error).__name__}: {error}"},
                started=started,
            )
            raise
        result = self._brain_result(
            request, status="succeeded", output=advice.to_dict(), started=started
        )
        return request, result, advice

    def _brain_request(
        self,
        context: BrainContext,
        brain_id: str,
        purpose: str,
        parent_request_id: str | None = None,
    ) -> BrainRequest:
        payload = context.to_payload()
        input_hash = self._hash(payload)
        request = BrainRequest(
            id=uuid.uuid4().hex,
            goal_id=context.goal.id,
            brain_id=brain_id,
            brain_version=self._brain_version(brain_id),
            purpose=purpose,
            snapshot_revision=context.snapshot.revision,
            input_sha256=input_hash,
            input_projection=payload,
            parent_request_id=parent_request_id,
        )
        self.store.append_event(
            context.goal.id,
            context.goal.cycle,
            "brain_request",
            "heart",
            request.to_dict(),
        )
        return request

    def _brain_result(
        self,
        request: BrainRequest,
        status: str,
        output: JsonObject,
        started: float,
        usage: JsonObject | None = None,
    ) -> BrainResult:
        result = BrainResult(
            request_id=request.id,
            brain_id=request.brain_id,
            status=status,
            output_sha256=self._hash(output),
            latency_ms=(time.perf_counter() - started) * 1000,
            output=output,
            usage=usage or {},
        )
        goal = self.store.get_goal(request.goal_id)
        self.store.append_event(
            request.goal_id,
            goal.cycle,
            "brain_result",
            request.brain_id,
            result.to_dict(),
        )
        return result

    def _specialist_results(self, goal_id: str) -> list[JsonObject]:
        raw = self.store.load_memory(goal_id).get("specialist_results", [])
        return list(raw) if isinstance(raw, list) else []

    def _selected_advice(
        self, goal_id: str, result_ids: tuple[str, ...]
    ) -> list[JsonObject]:
        wanted = set(result_ids)
        return [
            item
            for item in self._specialist_results(goal_id)
            if item.get("brain_request_id") in wanted
        ]

    def _apply_advice_outcomes(
        self,
        goal: Goal,
        target: TargetAdapter,
        advice: list[JsonObject],
        capability_id: str,
        effectful: bool,
        reason: str,
        invocation_id: str,
    ) -> None:
        for item in advice:
            self._record_brain_outcome(
                goal,
                target,
                str(item["specialist"]),
                capability_id,
                effectful,
                reason,
                brain_request_id=str(item["brain_request_id"]),
                invocation_id=invocation_id,
            )

    def _record_brain_outcome(
        self,
        goal: Goal,
        target: TargetAdapter,
        brain_id: str,
        capability_id: str,
        effectful: bool,
        reason: str,
        brain_request_id: str,
        invocation_id: str | None,
    ) -> None:
        self.store.record_brain_outcome(
            brain_id, target.manifest.plugin_id, capability_id, effectful
        )
        self.store.append_event(
            goal.id,
            goal.cycle,
            "brain_outcome",
            "heart",
            {
                "brain_id": brain_id,
                "target_profile": target.manifest.plugin_id,
                "capability_id": capability_id,
                "effectful": effectful,
                "reason": reason,
                "brain_request_id": brain_request_id,
                "invocation_id": invocation_id,
            },
        )

    def _record_terminal_invocation(
        self,
        requested: InvocationReceipt,
        goal: Goal,
        result: ToolResult,
        state: InvocationState | None = None,
    ) -> None:
        receipt = InvocationReceipt(
            id=requested.id,
            goal_id=requested.goal_id,
            target_id=requested.target_id,
            capability_id=requested.capability_id,
            state=state
            or (
                InvocationState.SUCCEEDED
                if result.succeeded
                else InvocationState.PARTIAL
                if result.partial
                else InvocationState.FAILED
            ),
            requested_at=requested.requested_at,
            snapshot_revision=requested.snapshot_revision,
            decision_request_id=requested.decision_request_id,
            based_on=requested.based_on,
            result=result,
        )
        self.store.append_event(
            goal.id, goal.cycle, "invocation", requested.target_id, receipt.to_dict()
        )

    def _record_tool_result(
        self,
        goal: Goal,
        target: TargetAdapter,
        call: ToolCall,
        result: ToolResult,
        pre_snapshot: WorldSnapshot,
        post_snapshot: WorldSnapshot | None,
        invocation_id: str,
    ) -> None:
        self.store.append_event(
            goal.id,
            goal.cycle,
            "tool_result",
            target.manifest.id,
            {
                "call": call.to_dict(),
                "invocation_id": invocation_id,
                "result": result.to_dict(),
                "pre_revision": pre_snapshot.revision,
                "post_revision": (
                    post_snapshot.revision if post_snapshot is not None else None
                ),
            },
        )

    @staticmethod
    def _hash(value: JsonObject) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _sync_catalog(self) -> None:
        self.catalog.refresh()
        self.store.note_catalog(self.catalog.fingerprint(), self.catalog.snapshot())

    def _oracle_satisfied(
        self, goal: Goal, target: TargetAdapter, snapshot: WorldSnapshot
    ) -> bool:
        return self._oracle_result(goal, target, snapshot) is True

    def _oracle_result(
        self, goal: Goal, target: TargetAdapter, snapshot: WorldSnapshot
    ) -> bool | None:
        """Return target truth, preserving unavailable/invalid evidence as UNKNOWN."""
        try:
            result = target.goal_satisfied(goal, snapshot)
        except Exception as error:
            self.store.append_event(
                goal.id,
                goal.cycle,
                "oracle_error",
                target.manifest.id,
                {
                    "error": f"{type(error).__name__}: {error}",
                    "snapshot_revision": snapshot.revision,
                },
            )
            return None
        if type(result) is not bool:
            self.store.append_event(
                goal.id,
                goal.cycle,
                "oracle_contract_error",
                target.manifest.id,
                {
                    "error": "goal_satisfied must return an exact bool",
                    "returned_type": type(result).__name__,
                    "snapshot_revision": snapshot.revision,
                },
            )
            return None
        return result

    @staticmethod
    def _validate_tool_result(result: object) -> ToolResult:
        if not isinstance(result, ToolResult):
            try:
                result = ToolResult(
                    succeeded=getattr(result, "succeeded"),
                    changed=getattr(result, "changed"),
                    output=getattr(result, "output"),
                    error=getattr(result, "error"),
                    partial=getattr(result, "partial"),
                )
            except (AttributeError, TypeError) as exc:
                raise AdapterContractError(
                    f"execute must return the ToolResult contract, got {type(result).__name__}"
                ) from exc
        if type(result.succeeded) is not bool or type(result.changed) is not bool:
            raise AdapterContractError("ToolResult status fields must be exact booleans")
        if type(result.partial) is not bool:
            raise AdapterContractError("ToolResult.partial must be an exact boolean")
        if not isinstance(result.output, dict):
            raise AdapterContractError("ToolResult.output must be a JSON object")
        if result.error is not None and not isinstance(result.error, str):
            raise AdapterContractError("ToolResult.error must be a string or null")
        if result.succeeded and (result.error is not None or result.partial):
            raise AdapterContractError(
                "a successful ToolResult cannot contain an error or be partial"
            )
        if result.partial and (result.succeeded or not result.changed):
            raise AdapterContractError(
                "a partial ToolResult must be unsuccessful and report a change"
            )
        if not result.succeeded and result.changed and not result.partial:
            raise AdapterContractError(
                "an unsuccessful changed ToolResult must be marked partial"
            )
        try:
            json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise AdapterContractError(
                f"ToolResult must be JSON-serializable: {error}"
            ) from error
        return result

    @staticmethod
    def _observe(
        target: TargetAdapter, previous: WorldSnapshot | None = None
    ) -> WorldSnapshot:
        snapshot = target.observe()
        if snapshot.target_id != target.manifest.id:
            raise ValueError(
                f"adapter {target.manifest.id} observed target {snapshot.target_id}"
            )
        if snapshot.revision < 0:
            raise ValueError("snapshot revision cannot be negative")
        if previous is not None and snapshot.revision < previous.revision:
            raise ValueError(
                f"snapshot revision regressed from {previous.revision} "
                f"to {snapshot.revision}"
            )
        if (
            previous is not None
            and snapshot.revision == previous.revision
            and snapshot.state != previous.state
        ):
            raise ValueError(
                f"snapshot state changed without revision advance at "
                f"{snapshot.revision}"
            )
        return snapshot

    def _brain_version(self, brain_id: str) -> str:
        if brain_id == self.executive.manifest.qualified_id:
            return self.executive.manifest.version
        return self.catalog.specialist(brain_id).manifest.version

    def _decision_rejection(
        self, decision: BrainDecision, context: BrainContext
    ) -> str | None:
        fresh_ids = {
            str(item.get("brain_request_id")) for item in context.pending_advice
        }
        consulted = {
            str(item.get("specialist")) for item in context.pending_advice
        }
        specialist_ids = {
            specialist.qualified_id for specialist in context.specialists
        }
        capability_ids = {capability.id for capability in context.capabilities}

        if decision.kind is DecisionKind.CONSULT_BRAIN:
            if decision.based_on:
                return "consult_brain cannot cite specialist advice"
            if decision.name not in specialist_ids:
                return "consult_brain selected an unavailable specialist"
            if decision.name in consulted:
                return "same specialist already produced advice for this snapshot"
            return None

        if decision.kind is DecisionKind.USE_TOOL:
            if decision.name not in capability_ids:
                return "use_tool selected a capability outside the projected catalog"
            cited = set(decision.based_on)
            if cited and not cited.issubset(fresh_ids):
                return "use_tool cited missing or stale specialist advice"
            if context.cognitive_phase == "advice_ready" and not cited:
                return "advice_ready use_tool must cite the advice it consumes"
            if (
                self.require_specialist_first
                and context.cognitive_phase == "needs_specialist"
                and specialist_ids
            ):
                return "this cognition condition requires specialist consultation first"
            return None

        if decision.based_on and not set(decision.based_on).issubset(fresh_ids):
            return "terminal decision cited missing or stale advice"
        return None
