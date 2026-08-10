from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping
from uuid import uuid4

import jsonschema
from engine_sdk import (
    AutonomyProfileV1,
    BehaviorSignalV1,
    EvidenceGrade,
    GoalSpecV2,
    RiskClass,
    RoutineCandidateStatus,
    RoutineCandidateV1,
    RoutineShadowEventV1,
    RoutineSpecV1,
    RoutineStatus,
    StandingMandateV1,
    WorldSnapshotV2,
    artifact_sha256,
    canonical_json,
)

from .conditions_v2 import ConditionResult, evaluate_effects, evaluate_scoped_condition
from .world_store import WorldStore


@dataclass(frozen=True)
class RoutineEvaluationV1:
    routine_id: str
    goal_id: str
    status: RoutineStatus
    allowed: bool
    reason: str
    evidence_ids: tuple[str, ...] = ()
    occurrence_key: str | None = None


class RoutineRuntimeV1:
    """Plugin-neutral deterministic guard, conflict and occurrence gate."""

    def __init__(self, store: WorldStore, registry: Any, *, clock: Any) -> None:
        self.store = store
        self.registry = registry
        self._clock = clock

    def evaluate(
        self,
        snapshot: WorldSnapshotV2,
        *,
        previous: WorldSnapshotV2 | None = None,
    ) -> dict[str, RoutineEvaluationV1]:
        now = _as_utc(self._clock())
        values: dict[str, RoutineEvaluationV1] = {}
        routines = self.store.routines(
            statuses=(
                RoutineStatus.ACTIVE.value,
                RoutineStatus.DORMANT.value,
                RoutineStatus.GUARD_UNCERTAIN.value,
                RoutineStatus.CONFLICTED.value,
                RoutineStatus.SUSPENDED.value,
            )
        )
        by_id = {item.id: item for item in routines}
        true_guards: list[RoutineSpecV1] = []
        guard_results: dict[str, ConditionResult] = {}
        occurrence_keys: dict[str, str | None] = {}
        for routine in routines:
            authority_error = self._authority_error(routine, snapshot, now)
            if authority_error is not None:
                values[routine.goal_id] = RoutineEvaluationV1(
                    routine.id, routine.goal_id, RoutineStatus.SUSPENDED,
                    False, authority_error,
                )
                continue
            if routine.override_until is not None and now < _datetime(routine.override_until):
                values[routine.goal_id] = RoutineEvaluationV1(
                    routine.id, routine.goal_id, RoutineStatus.DORMANT,
                    False, "external override owns the actuator until cooldown ends",
                )
                continue
            if routine.active_occurrence_key is not None:
                result = ConditionResult(
                    True,
                    EvidenceGrade.DERIVED,
                    (),
                    "previously triggered occurrence remains active until observed effect",
                )
                guard_results[routine.id] = result
                occurrence_keys[routine.id] = routine.active_occurrence_key
                rate_error = self._rate_error(routine, now)
                if rate_error is not None:
                    values[routine.goal_id] = RoutineEvaluationV1(
                        routine.id, routine.goal_id, RoutineStatus.SUSPENDED,
                        False, rate_error, (), routine.active_occurrence_key,
                    )
                else:
                    true_guards.append(routine)
                continue
            result = evaluate_scoped_condition(
                routine.activation_guard,
                snapshot,
                previous=previous,
                now=now,
            )
            guard_results[routine.id] = result
            if result.value is not True or result.grade in {
                EvidenceGrade.UNKNOWN,
                EvidenceGrade.STALE,
                EvidenceGrade.CONFLICTING,
            }:
                if result.value is False and result.grade not in {
                    EvidenceGrade.UNKNOWN,
                    EvidenceGrade.STALE,
                    EvidenceGrade.CONFLICTING,
                }:
                    values[routine.goal_id] = RoutineEvaluationV1(
                        routine.id, routine.goal_id, RoutineStatus.DORMANT,
                        False, "activation guard is false", result.evidence_ids,
                    )
                    continue
                values[routine.goal_id] = RoutineEvaluationV1(
                    routine.id, routine.goal_id, RoutineStatus.GUARD_UNCERTAIN,
                    False, f"activation guard is uncertain: {result.reason}",
                    result.evidence_ids,
                )
                continue
            occurrence_key = _occurrence_key(routine, snapshot, now)
            occurrence_keys[routine.id] = occurrence_key
            if occurrence_key is not None and self.store.occurrence_exists(
                routine.id, occurrence_key
            ):
                values[routine.goal_id] = RoutineEvaluationV1(
                    routine.id, routine.goal_id, RoutineStatus.DORMANT,
                    False, "durable recurrence occurrence already handled",
                    result.evidence_ids, occurrence_key,
                )
                continue
            if routine.last_triggered_at is not None and (
                now - _datetime(routine.last_triggered_at)
            ).total_seconds() < routine.cooldown_seconds:
                values[routine.goal_id] = RoutineEvaluationV1(
                    routine.id, routine.goal_id, RoutineStatus.DORMANT,
                    False, "routine cooldown is active", result.evidence_ids,
                    occurrence_key,
                )
                continue
            rate_error = self._rate_error(routine, now)
            if rate_error is not None:
                values[routine.goal_id] = RoutineEvaluationV1(
                    routine.id, routine.goal_id, RoutineStatus.SUSPENDED,
                    False, rate_error, result.evidence_ids, occurrence_key,
                )
                continue
            true_guards.append(routine)

        blocked = self._conflicts(true_guards)
        for routine in true_guards:
            result = guard_results[routine.id]
            reason = blocked.get(routine.id)
            if reason is not None:
                values[routine.goal_id] = RoutineEvaluationV1(
                    routine.id, routine.goal_id, RoutineStatus.CONFLICTED,
                    False, reason, result.evidence_ids,
                    occurrence_keys.get(routine.id),
                )
            else:
                values[routine.goal_id] = RoutineEvaluationV1(
                    routine.id, routine.goal_id, RoutineStatus.ACTIVE,
                    True, "activation guard is true and authority is valid",
                    result.evidence_ids, occurrence_keys.get(routine.id),
                )

        for goal_id, evaluation in values.items():
            routine = by_id[evaluation.routine_id]
            updated = replace(
                routine,
                status=evaluation.status,
                status_reason=evaluation.reason,
            )
            if updated != routine:
                self.store.save_routine(updated)
        return values

    def note_result(
        self,
        evaluation: RoutineEvaluationV1,
        *,
        status: str,
        snapshot_id: str,
        request_id: str | None,
        entity_id: str | None,
    ) -> None:
        if not evaluation.allowed:
            return
        now = _as_utc(self._clock())
        handled = request_id is not None or status in {"monitoring", "completed"}
        if not handled:
            return
        routine = self.store.get_routine(evaluation.routine_id)
        stable = status in {"monitoring", "completed"}
        active_key = evaluation.occurrence_key or routine.active_occurrence_key
        if request_id is not None and active_key is None:
            active_key = "activation:" + now.isoformat()
        self.store.save_routine(
            replace(
                routine,
                last_triggered_at=now.isoformat(),
                active_occurrence_key=None if stable else active_key,
            )
        )
        if stable and active_key is not None and active_key.startswith("local-date:"):
            self.store.record_occurrence(
                routine.id,
                active_key,
                now.isoformat(),
                {"status": status, "snapshot_id": snapshot_id, "request_id": request_id},
            )
        if request_id is not None:
            self.store.record_routine_action(
                routine.id,
                entity_id or routine.entity_ids[0],
                request_id,
                now.isoformat(),
                {"status": status, "snapshot_id": snapshot_id},
            )

    def _authority_error(
        self, routine: RoutineSpecV1, snapshot: WorldSnapshotV2, now: datetime
    ) -> str | None:
        try:
            registered = self.registry.plugin(routine.plugin_id)
        except KeyError:
            return "routine plugin is not installed"
        if routine.manifest_fingerprint != registered.static_manifest.fingerprint:
            return "plugin manifest changed after routine compilation"
        template = self.registry.routine_template(
            routine.plugin_id, routine.template_id
        )
        if template is None:
            return "routine template is no longer declared"
        capability = self.registry.capability(
            routine.target_id, template.capability_family
        )
        if capability is None or capability.opaque:
            return "routine capability is unavailable or observe-only"
        observed_ids = {item.id for item in snapshot.entities}
        if not set(routine.entity_ids) <= observed_ids:
            return "an enrolled routine entity disappeared"
        if routine.profile_id is None:
            return None
        profile = next(
            (
                item for item in self.store.autonomy_profiles(enabled_only=True)
                if item.id == routine.profile_id
            ),
            None,
        )
        if profile is None:
            return "autonomy profile is disabled or revoked"
        error = _profile_scope_error(profile, routine, template, capability)
        if error is not None:
            return error
        compiler = self.registry.routine_compiler(
            routine.plugin_id, routine.template_id
        )
        validate = getattr(compiler, "validate_profile", None)
        if validate is not None:
            errors = tuple(str(item) for item in validate(profile, routine, snapshot))
            if errors:
                return "; ".join(errors)
        goal = self.store.get_goal(routine.goal_id)
        if goal.mandate_id is None:
            return "routine goal has no derived submandate"
        try:
            mandate = self.store.get_mandate(goal.mandate_id)
        except KeyError:
            return "routine submandate is missing"
        if mandate.revoked:
            return "routine submandate is revoked"
        if _datetime(mandate.valid_until) <= now + timedelta(hours=12):
            self.store.save_mandate(
                replace(
                    mandate,
                    valid_from=now.isoformat(),
                    valid_until=(now + timedelta(hours=24)).isoformat(),
                )
            )
        return None

    def _rate_error(self, routine: RoutineSpecV1, now: datetime) -> str | None:
        if routine.profile_id is None:
            return None
        profile = next(
            (item for item in self.store.autonomy_profiles(enabled_only=True) if item.id == routine.profile_id),
            None,
        )
        if profile is None:
            return "autonomy profile is unavailable"
        since = (now - timedelta(hours=1)).isoformat()
        per_zone = int(profile.limits.get("max_actions_per_zone_per_hour", 6))
        total = int(profile.limits.get("max_actions_total_per_hour", 30))
        if self.store.routine_action_count(since=since) >= total:
            return "autonomy total hourly action limit reached"
        if any(
            self.store.routine_action_count(since=since, entity_id=item) >= per_zone
            for item in routine.entity_ids
        ):
            return "autonomy zone hourly action limit reached"
        return None

    @staticmethod
    def _conflicts(routines: list[RoutineSpecV1]) -> dict[str, str]:
        blocked: dict[str, str] = {}
        groups: dict[tuple[str, tuple[str, ...]], list[RoutineSpecV1]] = {}
        for routine in routines:
            if not routine.conflict_key:
                continue
            groups.setdefault(
                (routine.conflict_key, tuple(sorted(routine.entity_ids))), []
            ).append(routine)
        for values in groups.values():
            states = {canonical_json(item.desired_state) for item in values}
            if len(states) <= 1:
                continue
            highest = max(item.priority for item in values)
            winners = [item for item in values if item.priority == highest]
            if len(winners) > 1:
                for item in values:
                    blocked[item.id] = "equal-priority routines request conflicting effects"
                continue
            winner = winners[0]
            for item in values:
                if item.id != winner.id:
                    blocked[item.id] = f"higher-priority routine {winner.id} wins deterministically"
        return blocked


class RoutineLearnerV1:
    """Deterministic evidence -> real shadow -> approval/YOLO promotion route."""

    def __init__(
        self,
        store: WorldStore,
        registry: Any,
        *,
        clock: Any,
        minimum_examples: int = 5,
        minimum_days: int = 3,
        consistency: float = 0.80,
    ) -> None:
        self.store = store
        self.registry = registry
        self._clock = clock
        self.minimum_examples = minimum_examples
        self.minimum_days = minimum_days
        self.consistency = consistency

    def ingest_signal(
        self, signal: BehaviorSignalV1, snapshot: WorldSnapshotV2
    ) -> RoutineCandidateV1 | None:
        self._apply_external_override(signal)
        if signal.routine_template_id is None:
            return None
        template = self.registry.routine_template(
            signal.plugin_id, signal.routine_template_id
        )
        compiler = self.registry.routine_compiler(
            signal.plugin_id, signal.routine_template_id
        )
        if template is None or compiler is None:
            return None
        try:
            jsonschema.validate(signal.pattern_value, template.pattern_schema)
        except Exception:
            return None
        existing = next(
            (
                item for item in self.store.routine_candidates(
                    template_id=signal.routine_template_id
                )
                if item.target_id == signal.target_id
                and item.entity_ids == (signal.entity_id,)
                and item.status not in {
                    RoutineCandidateStatus.REJECTED,
                    RoutineCandidateStatus.ROLLED_BACK,
                }
            ),
            None,
        )
        if existing is not None:
            if (
                bool(signal.provenance.get("explicit_conflict"))
                and existing.status
                in {
                    RoutineCandidateStatus.CANDIDATE,
                    RoutineCandidateStatus.SHADOW,
                    RoutineCandidateStatus.READY_FOR_APPROVAL,
                }
            ):
                rejected = replace(
                    existing, status=RoutineCandidateStatus.REJECTED
                )
                self.store.save_routine_candidate(rejected)
                return rejected
            return existing
        evidence = tuple(
            item for item in self.store.behavior_signals(
                routine_template_id=signal.routine_template_id
            )
            if item.plugin_id == signal.plugin_id
            and item.target_id == signal.target_id
            and item.entity_id == signal.entity_id
            and item.evidence_grade in {EvidenceGrade.OBSERVED, EvidenceGrade.INFERRED}
        )
        if len(evidence) < self.minimum_examples:
            return None
        if any(bool(item.provenance.get("explicit_conflict")) for item in evidence):
            return None
        days = {_local_day(item) for item in evidence}
        if len(days) < self.minimum_days:
            return None
        value_counts = Counter(canonical_json(item.pattern_value) for item in evidence)
        selected_value, selected_count = value_counts.most_common(1)[0]
        value_consistency = selected_count / len(evidence)
        context_counts = Counter(canonical_json(item.context) for item in evidence)
        context_value, context_count = context_counts.most_common(1)[0]
        context_consistency = context_count / len(evidence)
        overall = min(value_consistency, context_consistency)
        if overall < self.consistency:
            return None
        selected = next(
            item.pattern_value
            for item in evidence
            if canonical_json(item.pattern_value) == selected_value
        )
        context = next(
            dict(item.context)
            for item in evidence
            if canonical_json(item.context) == context_value
        )
        descriptor = {
            "id": "routine-candidate:" + artifact_sha256({
                "template_id": template.id,
                "target_id": signal.target_id,
                "entity_id": signal.entity_id,
                "pattern_value": selected,
            }),
            "template_id": template.id,
            "plugin_id": signal.plugin_id,
            "target_id": signal.target_id,
            "entity_ids": (signal.entity_id,),
            "pattern_value": selected,
            "context": context,
            "evidence_ids": tuple(item.id for item in evidence),
        }
        routine, goal = compiler.compile(template, descriptor)
        self._validate_compilation(template, descriptor, routine, goal)
        registered = self.registry.plugin(signal.plugin_id)
        capability = self.registry.capability(
            signal.target_id, template.capability_family
        )
        if capability is None or capability.opaque:
            return None
        if signal.entity_id not in {
            item.id for item in snapshot.entities
            if item.target_id == signal.target_id
        }:
            return None
        try:
            for effect in goal.desired_effects:
                jsonschema.validate(effect.parameters, capability.effect_schema)
        except Exception:
            return None
        started = max(_datetime(item.observed_at) for item in evidence)
        routine = replace(
            routine,
            status=RoutineStatus.SHADOW,
            manifest_fingerprint=registered.static_manifest.fingerprint,
        )
        profile = self.store.active_autonomy_profile(
            signal.plugin_id, signal.target_id
        )
        if profile is not None:
            if _profile_scope_error(profile, routine, template, capability) is not None:
                return None
            validate = getattr(compiler, "validate_profile", None)
            if validate is not None and tuple(validate(profile, routine, snapshot)):
                return None
        candidate = RoutineCandidateV1(
            id=str(descriptor["id"]),
            template_id=template.id,
            plugin_id=signal.plugin_id,
            target_id=signal.target_id,
            entity_ids=(signal.entity_id,),
            pattern_value=selected,
            context=context,
            evidence_ids=tuple(item.id for item in evidence),
            example_count=len(evidence),
            local_days=tuple(sorted(str(item) for item in days)),
            consistency=overall,
            status=RoutineCandidateStatus.SHADOW,
            routine=routine,
            goal=goal,
            shadow_started_at=started.isoformat(),
            shadow_ends_at=(started + timedelta(days=template.shadow_days)).isoformat(),
            rollback_patch={
                "routine_status": RoutineStatus.ROLLED_BACK.value,
                "goal_status": "abandoned",
                "revoke_mandate": True,
            },
        )
        self.store.save_routine_candidate(candidate)
        return candidate

    def advance(self, snapshot: WorldSnapshotV2) -> None:
        now = _as_utc(self._clock())
        for candidate in self.store.routine_candidates(
            statuses=(RoutineCandidateStatus.SHADOW.value,)
        ):
            template = self.registry.routine_template(
                candidate.plugin_id, candidate.template_id
            )
            if template is None:
                continue
            events = list(self.store.shadow_events(candidate.id))
            effects = evaluate_effects(candidate.goal, snapshot)
            effects_true = bool(effects) and all(item.value is True for item in effects.values())
            evidence_ids = tuple(
                dict.fromkeys(
                    value for item in effects.values() for value in item.evidence_ids
                )
            )
            for event in events:
                if event.agreement is not None:
                    continue
                if effects_true and now <= _datetime(event.window_ends_at):
                    self.store.save_shadow_event(
                        replace(
                            event,
                            agreement=True,
                            desired_effect_observed_at=now.isoformat(),
                            evidence_ids=evidence_ids,
                        )
                    )
                elif now > _datetime(event.window_ends_at):
                    self.store.save_shadow_event(replace(event, agreement=False))

            guard = evaluate_scoped_condition(
                candidate.routine.activation_guard,
                snapshot,
                now=now,
            )
            if guard.value is True and not effects_true:
                key = _shadow_opportunity_key(candidate.routine, snapshot, now)
                if not any(item.opportunity_key == key for item in events):
                    event = RoutineShadowEventV1(
                        id="shadow-event:" + artifact_sha256({
                            "candidate_id": candidate.id, "key": key
                        }),
                        candidate_id=candidate.id,
                        opportunity_key=key,
                        triggered_at=now.isoformat(),
                        window_ends_at=(
                            now + timedelta(seconds=template.trigger_window_seconds)
                        ).isoformat(),
                        evidence_ids=guard.evidence_ids,
                    )
                    self.store.save_shadow_event(event)

            if candidate.shadow_ends_at is None or now < _datetime(candidate.shadow_ends_at):
                continue
            outcomes = self.store.shadow_events(candidate.id)
            closed = tuple(item for item in outcomes if item.agreement is not None)
            if len(closed) < template.minimum_shadow_opportunities:
                continue
            agreement = sum(item.agreement is True for item in closed) / len(closed)
            if agreement < template.minimum_shadow_agreement:
                self.store.save_routine_candidate(
                    replace(candidate, status=RoutineCandidateStatus.REJECTED)
                )
                continue
            profile = self.store.active_autonomy_profile(
                candidate.plugin_id, candidate.target_id
            )
            if profile is None:
                self.store.save_routine_candidate(
                    replace(
                        candidate,
                        status=RoutineCandidateStatus.READY_FOR_APPROVAL,
                        routine=replace(
                            candidate.routine,
                            status=RoutineStatus.READY_FOR_APPROVAL,
                        ),
                    )
                )
            else:
                self.promote(candidate.id, profile=profile, activated_by="yolo-profile")

    def promote(
        self,
        candidate_id: str,
        *,
        profile: AutonomyProfileV1 | None,
        activated_by: str,
    ) -> RoutineSpecV1:
        candidate = self.store.get_routine_candidate(candidate_id)
        allowed = {
            RoutineCandidateStatus.READY_FOR_APPROVAL,
            RoutineCandidateStatus.SHADOW,
        }
        if candidate.status not in allowed:
            raise ValueError("routine candidate is not promotable")
        template = self.registry.routine_template(
            candidate.plugin_id, candidate.template_id
        )
        if template is None:
            raise ValueError("routine template is no longer installed")
        now = _as_utc(self._clock())
        if candidate.status is RoutineCandidateStatus.SHADOW:
            shadow_error = self._shadow_gate_error(candidate, template, now)
            if shadow_error is not None:
                raise PermissionError(shadow_error)
            if profile is None:
                raise PermissionError(
                    "normal-mode promotion requires ready_for_approval"
                )
        capability = self.registry.capability(
            candidate.target_id, template.capability_family
        )
        if capability is None or capability.opaque:
            raise ValueError("routine capability is unavailable")
        routine = candidate.routine
        if profile is not None:
            error = _profile_scope_error(profile, routine, template, capability)
            if error is not None:
                raise PermissionError(error)
            compiler = self.registry.routine_compiler(
                candidate.plugin_id, candidate.template_id
            )
            validate = getattr(compiler, "validate_profile", None)
            snapshot = self.store.latest_world_snapshot()
            if validate is not None and snapshot is not None:
                errors = tuple(str(item) for item in validate(profile, routine, snapshot))
                if errors:
                    raise PermissionError("; ".join(errors))
        mandate_id = "mandate:routine:" + routine.id
        mandate = StandingMandateV1(
            id=mandate_id,
            plugin_ids=(candidate.plugin_id,),
            target_ids=(candidate.target_id,),
            entity_ids=candidate.entity_ids,
            capability_families=tuple(
                sorted({item.capability_family for item in candidate.goal.desired_effects})
            ),
            limits=(dict(profile.limits) if profile is not None else dict(capability.limits)),
            privacy_permissions=(capability.privacy_class.value,),
            learning_permissions=("learning.low-risk",),
            valid_from=now.isoformat(),
            valid_until=(
                now + (timedelta(hours=24) if profile is not None else timedelta(days=365))
            ).isoformat(),
            manifest_versions={
                candidate.plugin_id: self.registry.plugin(
                    candidate.plugin_id
                ).static_manifest.version
            },
            activated_by=activated_by,
        )
        routine = replace(
            routine,
            status=RoutineStatus.ACTIVE,
            profile_id=profile.id if profile is not None else None,
            status_reason="promoted inside exact owner authority",
        )
        goal = replace(candidate.goal, mandate_id=mandate.id, status="active")
        promoted = replace(
            candidate,
            status=RoutineCandidateStatus.PROMOTED,
            routine=routine,
            goal=goal,
        )
        self.store.activate_routine(promoted, routine, goal, mandate)
        return routine

    def _shadow_gate_error(
        self,
        candidate: RoutineCandidateV1,
        template: Any,
        now: datetime,
    ) -> str | None:
        if (
            candidate.shadow_ends_at is None
            or now < _datetime(candidate.shadow_ends_at)
        ):
            return "routine shadow window is not complete"
        outcomes = self.store.shadow_events(candidate.id)
        closed = tuple(item for item in outcomes if item.agreement is not None)
        if len(closed) < template.minimum_shadow_opportunities:
            return "routine shadow lacks real trigger opportunities"
        agreement = sum(item.agreement is True for item in closed) / len(closed)
        if agreement < template.minimum_shadow_agreement:
            return "routine shadow agreement is below the promotion threshold"
        return None

    def reject(self, candidate_id: str) -> RoutineCandidateV1:
        candidate = self.store.get_routine_candidate(candidate_id)
        rejected = replace(candidate, status=RoutineCandidateStatus.REJECTED)
        self.store.save_routine_candidate(rejected)
        return rejected

    def rollback(self, routine_id: str, *, reason: str) -> None:
        routine = self.store.get_routine(routine_id)
        candidate = next(
            (
                item for item in self.store.routine_candidates()
                if item.routine.id == routine.id
            ),
            None,
        )
        goal = self.store.get_goal(routine.goal_id)
        mandate = (
            self.store.get_mandate(goal.mandate_id)
            if goal.mandate_id is not None else None
        )
        self.store.rollback_active_routine(
            routine, candidate, mandate, reason=reason
        )

    def _apply_external_override(self, signal: BehaviorSignalV1) -> None:
        if not isinstance(signal.pattern_value, Mapping) or "on" not in signal.pattern_value:
            return
        observed = signal.pattern_value.get("on")
        if type(observed) is not bool:
            return
        now = _datetime(signal.observed_at)
        for routine in self.store.routines(
            statuses=(
                RoutineStatus.ACTIVE.value,
                RoutineStatus.DORMANT.value,
                RoutineStatus.GUARD_UNCERTAIN.value,
                RoutineStatus.CONFLICTED.value,
                RoutineStatus.SUSPENDED.value,
            )
        ):
            if signal.entity_id not in routine.entity_ids:
                continue
            desired = routine.desired_state.get("on")
            if type(desired) is not bool or observed == desired:
                continue
            recent = tuple(
                item for item in routine.conflict_timestamps
                if now - _datetime(item) <= timedelta(days=7)
            ) + (now.isoformat(),)
            updated = replace(
                routine,
                override_until=(now + timedelta(hours=2)).isoformat(),
                conflict_timestamps=recent,
                status_reason="external opposite change temporarily owns actuator",
            )
            explicit = bool(signal.provenance.get("explicit_conflict"))
            if explicit or len(recent) >= 3:
                self.rollback(
                    routine.id,
                    reason=(
                        "explicit owner correction"
                        if explicit else "three contradictory external changes in seven days"
                    ),
                )
            else:
                self.store.save_routine(updated)

    @staticmethod
    def _validate_compilation(
        template: Any,
        descriptor: Mapping[str, Any],
        routine: RoutineSpecV1,
        goal: GoalSpecV2,
    ) -> None:
        if routine.template_id != template.id or routine.plugin_id != template.plugin_id:
            raise ValueError("routine compiler changed template/plugin identity")
        if routine.target_id != descriptor["target_id"]:
            raise ValueError("routine compiler changed target identity")
        if routine.entity_ids != tuple(descriptor["entity_ids"]):
            raise ValueError("routine compiler changed entity scope")
        if routine.goal_id != goal.id:
            raise ValueError("routine compiler returned an unrelated goal")
        if goal.mandate_id is not None:
            raise ValueError("routine compiler cannot mint a mandate")
        if any(
            item.capability_family != template.capability_family
            for item in goal.desired_effects
        ):
            raise ValueError("routine compiler escaped the template capability family")


def _profile_scope_error(
    profile: AutonomyProfileV1,
    routine: RoutineSpecV1,
    template: Any,
    capability: Any,
) -> str | None:
    if not profile.enabled:
        return "autonomy profile is disabled"
    if profile.plugin_id != routine.plugin_id or profile.target_id != routine.target_id:
        return "routine plugin/target is outside autonomy profile"
    if profile.manifest_fingerprint != routine.manifest_fingerprint:
        return "autonomy manifest fingerprint changed"
    if routine.template_id not in profile.routine_template_ids:
        return "routine template is outside autonomy profile"
    if template.capability_family not in profile.capability_families:
        return "routine capability is outside autonomy profile"
    if not set(routine.entity_ids) <= set(profile.entity_ids):
        return "routine entity scope expands autonomy profile"
    risk = {
        RiskClass.READ_ONLY: 0,
        RiskClass.LOW: 1,
        RiskClass.MEDIUM: 2,
        RiskClass.HIGH: 3,
    }
    if risk[capability.risk_class] > risk[profile.risk_ceiling]:
        return "routine risk exceeds autonomy ceiling"
    minimum_cooldown = int(profile.limits.get("minimum_cooldown_seconds", 300))
    if routine.cooldown_seconds < minimum_cooldown:
        return "routine cooldown is below autonomy minimum"
    return None


def _occurrence_key(
    routine: RoutineSpecV1, snapshot: WorldSnapshotV2, now: datetime
) -> str | None:
    if routine.recurrence.get("kind") != "daily":
        return None
    local = _local_datetime(snapshot) or now
    return f"local-date:{local.date().isoformat()}"


def _shadow_opportunity_key(
    routine: RoutineSpecV1, snapshot: WorldSnapshotV2, now: datetime
) -> str:
    daily = _occurrence_key(routine, snapshot, now)
    if daily is not None:
        return daily
    bucket = max(300, routine.cooldown_seconds)
    return f"window:{int(now.timestamp()) // bucket}"


def _local_datetime(snapshot: WorldSnapshotV2) -> datetime | None:
    item = next(
        (
            item for item in snapshot.observations
            if item.property == "time.iso8601"
            and item.evidence_grade not in {
                EvidenceGrade.UNKNOWN,
                EvidenceGrade.STALE,
                EvidenceGrade.CONFLICTING,
            }
        ),
        None,
    )
    if item is None or not isinstance(item.value, str):
        return None
    try:
        return datetime.fromisoformat(item.value)
    except ValueError:
        return None


def _local_day(signal: BehaviorSignalV1) -> str:
    value = signal.context.get("local_date") or signal.provenance.get("local_date")
    if isinstance(value, str) and value:
        return value
    return _datetime(signal.observed_at).date().isoformat()


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
