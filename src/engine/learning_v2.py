from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatchcase
from typing import Any
from uuid import uuid4

from engine_sdk import (
    BehaviorSignalV1,
    EvidenceGrade,
    GoalSpecV2,
    LearningCandidateV1,
    LearningStatus,
    PreferenceEvidenceV1,
    PreferencePromotionMode,
    PreferenceSpecV1,
    StandingMandateV1,
    artifact_sha256,
    canonical_json,
)

from .world_store import WorldStore

# Compatibility for the pre-plugin-neutral v2 tests and persisted goals. New
# automatic learning is controlled by PreferenceSpecV1, never by this list.
LEGACY_AUTO_FIELDS = (
    "lighting.brightness_band",
    "lighting.switch_off_delay_seconds",
    "lighting.quiet_time_window",
)


class BoundedPreferenceLearner:
    def __init__(
        self,
        store: WorldStore,
        *,
        minimum_examples: int = 5,
        minimum_days: int = 3,
        consistency: float = 0.80,
        shadow_days: int = 7,
    ) -> None:
        self.store = store
        self.minimum_examples = minimum_examples
        self.minimum_days = minimum_days
        self.consistency = consistency
        self.shadow_days = shadow_days

    def record_explicit_correction(
        self,
        goal: GoalSpecV2,
        *,
        field_path: str,
        old_value: Any,
        new_value: Any,
        context: dict[str, Any],
        observed_at: str,
    ) -> GoalSpecV2:
        evidence = PreferenceEvidenceV1(
            id="preference:" + uuid4().hex,
            goal_id=goal.id,
            grade=EvidenceGrade.OBSERVED,
            source="explicit_owner_correction",
            field_path=field_path,
            old_value=old_value,
            new_value=new_value,
            context=context,
            observed_at=observed_at,
            preference_id=field_path if _is_namespaced_preference(field_path) else None,
        )
        self.store.save_preference_evidence(evidence)
        patched = _patch_goal(goal, field_path, new_value)
        self.store.save_goal_version(patched)
        return patched

    def record_manual_override(
        self,
        goal_id: str,
        *,
        field_path: str,
        old_value: Any,
        new_value: Any,
        context: dict[str, Any],
        observed_at: str,
    ) -> PreferenceEvidenceV1:
        evidence = PreferenceEvidenceV1(
            id="preference:" + uuid4().hex,
            goal_id=goal_id,
            grade=EvidenceGrade.INFERRED,
            source="unexplained_manual_override",
            field_path=field_path,
            old_value=old_value,
            new_value=new_value,
            context=context,
            observed_at=observed_at,
            preference_id=field_path if _is_namespaced_preference(field_path) else None,
        )
        self.store.save_preference_evidence(evidence)
        return evidence

    def record_signal(
        self, goal: GoalSpecV2, signal: BehaviorSignalV1
    ) -> PreferenceEvidenceV1:
        """Link one exactly-once plugin signal to one goal as durable evidence."""
        evidence = PreferenceEvidenceV1(
            id="preference:" + artifact_sha256(
                {"signal_id": signal.id, "goal_id": goal.id}
            ),
            goal_id=goal.id,
            grade=signal.evidence_grade,
            source=f"plugin_behavior:{signal.plugin_id}",
            field_path=signal.preference_id,
            old_value=signal.old_value,
            new_value=signal.new_value,
            context=dict(signal.context),
            observed_at=signal.observed_at,
            explicit_conflict=bool(signal.provenance.get("explicit_conflict", False)),
            signal_id=signal.id,
            plugin_id=signal.plugin_id,
            target_id=signal.target_id,
            entity_id=signal.entity_id,
            capability_family=signal.capability_family,
            preference_id=signal.preference_id,
        )
        self.store.save_preference_evidence(evidence)
        return evidence

    def candidate(
        self,
        goal: GoalSpecV2,
        field_path: str,
        mandate: StandingMandateV1,
    ) -> LearningCandidateV1 | None:
        """Compatibility entrypoint for the original fixed lighting allowlist."""
        if field_path not in LEGACY_AUTO_FIELDS:
            return None
        return self._candidate(
            goal,
            field_path=field_path,
            mandate=mandate,
            preference_id=None,
            plugin_id=None,
            target_id=None,
            entity_id=None,
            capability_family=None,
        )

    def candidate_for_preference(
        self,
        goal: GoalSpecV2,
        spec: PreferenceSpecV1,
        mandate: StandingMandateV1,
        *,
        target_id: str,
        entity_id: str,
    ) -> LearningCandidateV1 | None:
        if spec.promotion_mode is not PreferencePromotionMode.SHADOW_LOW_RISK:
            return None
        if spec.id not in goal.preferences:
            return None
        return self._candidate(
            goal,
            field_path=spec.id,
            mandate=mandate,
            preference_id=spec.id,
            plugin_id=spec.plugin_id,
            target_id=target_id,
            entity_id=entity_id,
            capability_family=spec.capability_family,
        )

    def _candidate(
        self,
        goal: GoalSpecV2,
        *,
        field_path: str,
        mandate: StandingMandateV1,
        preference_id: str | None,
        plugin_id: str | None,
        target_id: str | None,
        entity_id: str | None,
        capability_family: str | None,
    ) -> LearningCandidateV1 | None:
        if "learning.low-risk" not in mandate.learning_permissions:
            return None
        if plugin_id is not None and plugin_id not in mandate.plugin_ids:
            return None
        if target_id is not None and target_id not in mandate.target_ids:
            return None
        if capability_family is not None and capability_family not in mandate.capability_families:
            return None
        if entity_id is not None and not any(
            fnmatchcase(entity_id, pattern) for pattern in mandate.entity_ids
        ):
            return None
        existing = next(
            (
                item
                for item in self.store.learning_candidates(
                    goal_id=goal.id,
                    statuses=(LearningStatus.SHADOW.value, LearningStatus.PROMOTED.value),
                )
                if item.field_path == field_path
                and item.target_id == target_id
                and item.entity_id == entity_id
            ),
            None,
        )
        if existing is not None:
            return existing
        evidence = tuple(
            item
            for item in self.store.preference_evidence(goal.id)
            if item.field_path == field_path
            and item.grade is EvidenceGrade.INFERRED
            and (target_id is None or item.target_id == target_id)
            and (entity_id is None or item.entity_id == entity_id)
            and (
                capability_family is None
                or item.capability_family == capability_family
            )
        )
        selected_value = self._qualifying_value(evidence)
        if selected_value is _NO_VALUE:
            return None
        started = max(_datetime(item.observed_at) for item in evidence)
        candidate = LearningCandidateV1(
            id="habit:" + uuid4().hex,
            goal_id=goal.id,
            field_path=field_path,
            old_value=_field_value(goal, field_path),
            new_value=selected_value,
            evidence_ids=tuple(item.id for item in evidence),
            status=LearningStatus.SHADOW,
            shadow_started_at=started.isoformat(),
            shadow_ends_at=(started + timedelta(days=self.shadow_days)).isoformat(),
            rollback_patch={field_path: _field_value(goal, field_path)},
            preference_id=preference_id,
            plugin_id=plugin_id,
            target_id=target_id,
            entity_id=entity_id,
            capability_family=capability_family,
        )
        self.store.save_learning_candidate(candidate)
        return candidate

    def promote(
        self,
        goal: GoalSpecV2,
        candidate: LearningCandidateV1,
        outcomes: tuple[dict[str, Any], ...],
        *,
        now: datetime,
    ) -> GoalSpecV2 | None:
        if candidate.status is not LearningStatus.SHADOW:
            return None
        if candidate.shadow_ends_at is None or _as_utc(now) < _datetime(candidate.shadow_ends_at):
            return None
        if not outcomes or any(item.get("achieved") is not True for item in outcomes):
            rejected = replace(
                candidate,
                status=LearningStatus.REJECTED,
                shadow_outcomes=outcomes,
            )
            self.store.save_learning_candidate(rejected)
            return None
        patched = _patch_goal(goal, candidate.field_path, candidate.new_value)
        self.store.save_goal_version(patched)
        self.store.save_learning_candidate(
            replace(
                candidate,
                status=LearningStatus.PROMOTED,
                shadow_outcomes=outcomes,
                promoted_goal_version=patched.version,
            )
        )
        return patched

    def advance_shadow(
        self,
        goal: GoalSpecV2,
        candidate: LearningCandidateV1,
        *,
        now: datetime,
    ) -> GoalSpecV2 | None:
        """Promote after the fixed shadow window only if evidence still agrees."""
        evidence = tuple(
            item
            for item in self.store.preference_evidence(goal.id)
            if item.id in candidate.evidence_ids
        )
        selected = self._qualifying_value(evidence)
        consistent = selected is not _NO_VALUE and _stable_value(selected) == _stable_value(
            candidate.new_value
        )
        outcomes = (
            {
                "achieved": consistent,
                "kind": "shadow_consistency_gate",
                "evidence_ids": list(candidate.evidence_ids),
            },
        )
        return self.promote(goal, candidate, outcomes, now=now)

    def rollback(
        self, goal: GoalSpecV2, candidate: LearningCandidateV1
    ) -> GoalSpecV2 | None:
        if candidate.status is not LearningStatus.PROMOTED:
            return None
        if _field_value(goal, candidate.field_path) != candidate.new_value:
            return None
        old_value = candidate.rollback_patch.get(
            candidate.field_path, candidate.old_value
        )
        patched = _patch_goal(goal, candidate.field_path, old_value)
        self.store.save_goal_version(patched)
        self.store.save_learning_candidate(
            replace(candidate, status=LearningStatus.ROLLED_BACK)
        )
        return patched

    def _qualifying_value(
        self, evidence: tuple[PreferenceEvidenceV1, ...]
    ) -> Any:
        if len(evidence) < self.minimum_examples:
            return _NO_VALUE
        if any(item.explicit_conflict for item in evidence):
            return _NO_VALUE
        days = {_datetime(item.observed_at).date() for item in evidence}
        if len(days) < self.minimum_days:
            return _NO_VALUE
        values = Counter(_stable_value(item.new_value) for item in evidence)
        selected, count = values.most_common(1)[0]
        if count / len(evidence) < self.consistency:
            return _NO_VALUE
        contexts = Counter(_stable_value(item.context) for item in evidence)
        if contexts.most_common(1)[0][1] / len(evidence) < self.consistency:
            return _NO_VALUE
        return next(
            item.new_value
            for item in evidence
            if _stable_value(item.new_value) == selected
        )


def _patch_goal(goal: GoalSpecV2, field_path: str, value: Any) -> GoalSpecV2:
    if _is_namespaced_preference(field_path) or field_path in goal.preferences:
        preferences = dict(goal.preferences)
        preferences[field_path] = value
        return replace(goal, preferences=preferences, version=goal.version + 1)
    budgets = dict(goal.budgets)
    preferences = dict(budgets.get("preferences", {}))
    preferences[field_path] = value
    budgets["preferences"] = preferences
    return replace(goal, budgets=budgets, version=goal.version + 1)


def _field_value(goal: GoalSpecV2, field_path: str) -> Any:
    if _is_namespaced_preference(field_path) or field_path in goal.preferences:
        return goal.preferences.get(field_path)
    return goal.budgets.get("preferences", {}).get(field_path)


def _is_namespaced_preference(value: str) -> bool:
    return ".preference." in value


def _stable_value(value: Any) -> str:
    return canonical_json(value)


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


_NO_VALUE = object()
