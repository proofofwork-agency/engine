from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from engine_sdk import (
    AutonomyDecisionKindV1,
    AutonomyEvaluationV1,
    AutonomyShadowOutcomeV1,
    ConditionV1,
    DesiredEffectV1,
    GoalModeV2,
    GoalSpecV2,
    WorldSnapshotV2,
    artifact_sha256,
)

from .conditions_v2 import evaluate_effects, select_entities

SHADOW_WINDOW = timedelta(minutes=45)
OPPORTUNITY_BUCKET = timedelta(minutes=30)


class AutonomyShadowScorerV1:
    """Score OBSERVE-mode autonomy proposals against later observations."""

    def __init__(self, store: Any, registry: Any, *, clock: Any | None = None) -> None:
        self.store = store
        self.registry = registry
        self._clock = clock or (lambda: datetime.now(UTC))

    def advance(self, snapshot: WorldSnapshotV2) -> None:
        now = _as_utc(self._clock())
        for outcome in self.store.autonomy_shadow_outcomes(open_only=True):
            closed = self._close(outcome, snapshot, now)
            if closed is not None:
                self.store.save_autonomy_shadow_outcome(closed)
        for evaluation in self.store.autonomy_evaluations():
            if evaluation.context.current_snapshot_id != snapshot.id:
                continue
            self._open_from_evaluation(evaluation, snapshot, now)

    def _open_from_evaluation(
        self,
        evaluation: AutonomyEvaluationV1,
        snapshot: WorldSnapshotV2,
        now: datetime,
    ) -> None:
        decision = evaluation.decision
        if decision.kind not in {
            AutonomyDecisionKindV1.PROPOSE_EFFECT,
            AutonomyDecisionKindV1.PROPOSE_GOAL_CANDIDATE,
        }:
            return
        goal = self._goal_for_evaluation(evaluation)
        if goal is None:
            return
        subjects = _subjects(decision, goal)
        if not subjects:
            return
        for entity_id, parameters in subjects:
            key = shadow_opportunity_key(
                evaluation.enrollment_id, entity_id, parameters, now
            )
            existing = self.store.autonomy_shadow_outcome(
                evaluation.enrollment_id, key
            )
            if existing is not None:
                continue
            outcome = AutonomyShadowOutcomeV1(
                id="autonomy-shadow:" + artifact_sha256(
                    {
                        "enrollment_id": evaluation.enrollment_id,
                        "key": key,
                        "evaluation_id": evaluation.id,
                    }
                ),
                enrollment_id=evaluation.enrollment_id,
                opportunity_key=key,
                triggered_at=now.isoformat(),
                window_ends_at=(now + SHADOW_WINDOW).isoformat(),
                trigger_snapshot_id=snapshot.id,
                entity_id=entity_id,
                canonical_parameters=dict(parameters),
                evaluation_id=evaluation.id,
                desired_effect_ids=tuple(item.id for item in goal.desired_effects),
            )
            self.store.save_autonomy_shadow_outcome(outcome)

    def _close(
        self,
        outcome: AutonomyShadowOutcomeV1,
        snapshot: WorldSnapshotV2,
        now: datetime,
    ) -> AutonomyShadowOutcomeV1 | None:
        evaluation = self.store.get_autonomy_evaluation(outcome.evaluation_id)
        goal = self._goal_for_evaluation(evaluation)
        if goal is None:
            if now > _as_utc(outcome.window_ends_at):
                return replace(
                    outcome, agreement=False, close_snapshot_id=snapshot.id
                )
            return None
        effects = evaluate_effects(goal, snapshot)
        evidence_ids = tuple(
            dict.fromkeys(
                value
                for item in effects.values()
                for value in item.evidence_ids
            )
        )
        effects_true = bool(effects) and all(item.value is True for item in effects.values())
        if effects_true and now <= _as_utc(outcome.window_ends_at):
            return replace(
                outcome,
                agreement=True,
                close_snapshot_id=snapshot.id,
                desired_effect_observed_at=now.isoformat(),
                evidence_ids=evidence_ids,
            )
        if now > _as_utc(outcome.window_ends_at):
            return replace(
                outcome,
                agreement=False,
                close_snapshot_id=snapshot.id,
                evidence_ids=evidence_ids,
            )
        if self._opposing(outcome, goal, snapshot):
            return replace(
                outcome,
                agreement=False,
                strict_disagreement=True,
                close_snapshot_id=snapshot.id,
                evidence_ids=evidence_ids,
            )
        return None

    def _opposing(
        self,
        outcome: AutonomyShadowOutcomeV1,
        goal: GoalSpecV2,
        snapshot: WorldSnapshotV2,
    ) -> bool:
        try:
            trigger = self.store.world_snapshot(outcome.trigger_snapshot_id)
        except KeyError:
            return False
        properties = tuple(
            item
            for effect in goal.desired_effects
            for item in _observation_properties(effect.condition)
        )
        if not properties:
            return False
        entities = {
            item.id
            for effect in goal.desired_effects
            for item in select_entities(snapshot, effect.entity_selector)
        }
        if outcome.entity_id:
            entities.add(outcome.entity_id)
        for entity_id in entities:
            for property_name in properties:
                current = _observation_value(snapshot, entity_id, property_name)
                previous = _observation_value(trigger, entity_id, property_name)
                if current is _MISSING or previous is _MISSING:
                    continue
                if current != previous:
                    return True
        return False

    def _goal_for_evaluation(self, evaluation: AutonomyEvaluationV1) -> GoalSpecV2 | None:
        decision = evaluation.decision
        if (
            decision.kind is AutonomyDecisionKindV1.PROPOSE_EFFECT
            and decision.proposed_action is not None
        ):
            action = decision.proposed_action
            if self.store.has_goal(action.goal_id):
                return self.store.get_goal(action.goal_id)
            return _synthetic_goal(action.goal_id, action)
        if (
            decision.kind is AutonomyDecisionKindV1.PROPOSE_GOAL_CANDIDATE
            and decision.goal_candidate is not None
        ):
            candidate = decision.goal_candidate
            template = self.registry.goal_template(
                candidate.plugin_id, candidate.template_id
            )
            compiler = self.registry.goal_template_compiler(
                candidate.plugin_id, candidate.template_id
            )
            if template is None or compiler is None:
                return None
            compiled = compiler.compile(template, candidate, evaluation.context)
            if not isinstance(compiled, GoalSpecV2):
                return None
            return compiled
        return None


def shadow_opportunity_key(
    enrollment_id: str,
    entity_id: str,
    parameters: dict[str, Any],
    triggered_at: datetime,
) -> str:
    bucket = int(triggered_at.timestamp() // OPPORTUNITY_BUCKET.total_seconds())
    return artifact_sha256(
        {
            "enrollment_id": enrollment_id,
            "entity_id": entity_id,
            "parameters": parameters,
            "bucket": bucket,
        }
    )


def _subjects(
    decision: Any, goal: GoalSpecV2
) -> tuple[tuple[str, dict[str, Any]], ...]:
    if decision.proposed_action is not None:
        action = decision.proposed_action
        return ((action.entity_id, dict(action.semantic_parameters)),)
    if decision.goal_candidate is not None:
        candidate = decision.goal_candidate
        parameters = dict(candidate.parameters)
        return tuple((entity_id, parameters) for entity_id in candidate.entity_ids)
    selected: list[tuple[str, dict[str, Any]]] = []
    for effect in goal.desired_effects:
        for entity_id in effect.entity_selector.get("entity_ids", ()):
            selected.append((str(entity_id), dict(effect.parameters)))
    return tuple(selected)


def _synthetic_goal(goal_id: str, action: Any) -> GoalSpecV2:
    children = tuple(
        ConditionV1("eq", path=f"observation:{key}", value=value)
        for key, value in action.semantic_parameters.items()
    )
    condition = (
        children[0]
        if len(children) == 1
        else ConditionV1("all", children=children)
    )
    effect = DesiredEffectV1(
        id=action.desired_effect_id or "shadow-effect",
        capability_family=action.capability_family,
        entity_selector={"entity_ids": [action.entity_id]},
        condition=condition,
        parameters=dict(action.semantic_parameters),
    )
    return GoalSpecV2(
        id=goal_id,
        source_intent="autonomy-shadow-synthetic",
        mode=GoalModeV2.MAINTAIN,
        entity_scope={"entity_ids": [action.entity_id]},
        desired_effects=(effect,),
    )


def _observation_properties(condition: ConditionV1) -> tuple[str, ...]:
    found: list[str] = []
    if condition.path and condition.path.startswith("observation:"):
        found.append(condition.path.removeprefix("observation:"))
    for child in condition.children:
        found.extend(_observation_properties(child))
    return tuple(found)


_MISSING = object()


def _observation_value(
    snapshot: WorldSnapshotV2, entity_id: str, property_name: str
) -> Any:
    item = next(
        (
            observation
            for observation in snapshot.observations
            if observation.entity_id == entity_id
            and observation.property == property_name
        ),
        None,
    )
    return _MISSING if item is None else item.value


def _as_utc(value: datetime | str) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def shadow_report(store: Any, registry: Any) -> dict[str, Any]:
    """Counts and rates only. Thresholds stay in the experiment protocol."""
    outcomes = store.autonomy_shadow_outcomes()
    closed = tuple(item for item in outcomes if item.agreement is not None)
    open_outcomes = tuple(item for item in outcomes if item.agreement is None)
    days = _spanned_days(outcomes)
    snapshots = store.world_snapshots()
    scorer = AutonomyShadowScorerV1(store, registry)
    engine = _policy_counts(
        tuple(
            (item.agreement is True, item.strict_disagreement)
            for item in closed
        )
    )
    baselines = {
        "always_defer": _policy_counts(
            tuple(
                _baseline_verdict(
                    scorer, item, snapshots, kind="always_defer"
                )
                for item in closed
            )
        ),
        "hour_of_week": _policy_counts(
            tuple(
                _baseline_verdict(
                    scorer, item, snapshots, kind="hour_of_week"
                )
                for item in closed
            )
        ),
        "persistence": _policy_counts(
            tuple(
                _baseline_verdict(
                    scorer, item, snapshots, kind="persistence"
                )
                for item in closed
            )
        ),
    }
    return {
        "closed": len(closed),
        "open": len(open_outcomes),
        "enrollments": len({item.enrollment_id for item in outcomes}),
        "days": days,
        "dispatch_count": sum(item.dispatch_count for item in outcomes),
        "engine": engine,
        "baselines": baselines,
    }


def _policy_counts(
    verdicts: tuple[tuple[bool | None, bool], ...],
) -> dict[str, Any]:
    scored = tuple(item for item in verdicts if item[0] is not None)
    agreements = sum(1 for item in scored if item[0] is True)
    disagreements = sum(1 for item in scored if item[0] is False)
    strict = sum(1 for item in scored if item[1])
    total = len(scored)
    return {
        "scored": total,
        "agreement_count": agreements,
        "disagreement_count": disagreements,
        "strict_disagreement_count": strict,
        "agreement_rate": (agreements / total) if total else None,
        "strict_false_intervention_rate": (strict / total) if total else None,
    }


def _baseline_verdict(
    scorer: AutonomyShadowScorerV1,
    outcome: AutonomyShadowOutcomeV1,
    snapshots: tuple[WorldSnapshotV2, ...],
    *,
    kind: str,
) -> tuple[bool | None, bool]:
    if outcome.close_snapshot_id is None:
        return None, False
    try:
        trigger = next(
            item for item in snapshots if item.id == outcome.trigger_snapshot_id
        )
        close = next(
            item for item in snapshots if item.id == outcome.close_snapshot_id
        )
    except StopIteration:
        return None, False
    evaluation = scorer.store.get_autonomy_evaluation(outcome.evaluation_id)
    goal = scorer._goal_for_evaluation(evaluation)
    if goal is None:
        return None, False
    properties = tuple(
        item
        for effect in goal.desired_effects
        for item in _observation_properties(effect.condition)
    )
    if not properties:
        return None, False
    predicted = _baseline_prediction(
        kind, outcome, trigger, snapshots, properties
    )
    if predicted is None:
        return None, False
    observed = tuple(
        _observation_value(close, outcome.entity_id, property_name)
        for property_name in properties
    )
    if any(item is _MISSING for item in observed):
        return None, False
    agrees = observed == predicted
    return agrees, (not agrees)


def _baseline_prediction(
    kind: str,
    outcome: AutonomyShadowOutcomeV1,
    trigger: WorldSnapshotV2,
    snapshots: tuple[WorldSnapshotV2, ...],
    properties: tuple[str, ...],
) -> tuple[Any, ...] | None:
    trigger_values = tuple(
        _observation_value(trigger, outcome.entity_id, property_name)
        for property_name in properties
    )
    if any(item is _MISSING for item in trigger_values):
        return None
    if kind == "always_defer":
        return trigger_values
    earlier = tuple(
        item for item in snapshots if item.revision < trigger.revision
    )
    if kind == "persistence":
        if not earlier:
            return trigger_values
        previous = earlier[-1]
        values = tuple(
            _observation_value(previous, outcome.entity_id, property_name)
            for property_name in properties
        )
        if any(item is _MISSING for item in values):
            return trigger_values
        return values
    if kind != "hour_of_week":
        raise ValueError(f"unknown baseline: {kind}")
    trigger_at = _as_utc(trigger.observed_at)
    window_start = trigger_at - timedelta(days=7)
    samples: list[tuple[Any, ...]] = []
    for snapshot in earlier:
        stamp = _as_utc(snapshot.observed_at)
        if stamp < window_start or stamp >= trigger_at:
            continue
        if (
            stamp.weekday() != trigger_at.weekday()
            or stamp.hour != trigger_at.hour
        ):
            continue
        values = tuple(
            _observation_value(snapshot, outcome.entity_id, property_name)
            for property_name in properties
        )
        if any(item is _MISSING for item in values):
            continue
        samples.append(values)
    if not samples:
        return trigger_values
    counts: dict[tuple[Any, ...], int] = {}
    for sample in samples:
        counts[sample] = counts.get(sample, 0) + 1
    return max(
        counts,
        key=lambda item: (counts[item], artifact_sha256(list(item))),
    )


def _spanned_days(outcomes: tuple[AutonomyShadowOutcomeV1, ...]) -> int:
    if not outcomes:
        return 0
    stamps = tuple(_as_utc(item.triggered_at).date() for item in outcomes)
    return (max(stamps) - min(stamps)).days + 1
