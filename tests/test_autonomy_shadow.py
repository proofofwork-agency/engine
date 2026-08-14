from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from engine_sdk import (
    AutonomyContextV1,
    AutonomyDecisionKindV1,
    AutonomyDecisionV1,
    AutonomyEvaluationV1,
    AutonomyModeV1,
    AutonomyShadowOutcomeV1,
    ConditionV1,
    ContractError,
    DesiredEffectV1,
    EntityV1,
    EvidenceGrade,
    GoalModeV2,
    GoalSpecV2,
    ObservationV1,
    ProposedActionV1,
    TargetObservationV2,
    WorldSnapshotV2,
    artifact_sha256,
    canonical_json,
)
from test_world_v2 import _MutableClock

from engine.autonomy_shadow import (
    AutonomyShadowScorerV1,
    shadow_opportunity_key,
    shadow_report,
)
from engine.world_heart import DeterministicExecutiveBrainV2, WorldHeartV2
from engine.world_store import WorldStore

ENROLLMENT = "enrollment:shadow"
ENTITY = "zone:living"
TARGET = "homey:home"
STARTED = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)


class _EmptyRegistry:
    def goal_template(self, plugin_id: str, template_id: str) -> None:
        del plugin_id, template_id
        return None

    def goal_template_compiler(self, plugin_id: str, template_id: str) -> None:
        del plugin_id, template_id
        return None

    @property
    def lifecycle_observers(self) -> tuple[object, ...]:
        return ()


class AutonomyShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-shadow-")
        self.base = Path(self.temporary.name)
        self.store = WorldStore(self.base / "engine.sqlite3")
        self.clock = _MutableClock(STARTED)
        self.registry = _EmptyRegistry()
        self.scorer = AutonomyShadowScorerV1(
            self.store, self.registry, clock=self.clock
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def test_contract_rejects_dispatch_count(self) -> None:
        with self.assertRaisesRegex(ContractError, "cannot record dispatches"):
            AutonomyShadowOutcomeV1(
                "shadow:bad",
                ENROLLMENT,
                "key",
                STARTED.isoformat(),
                (STARTED + timedelta(minutes=45)).isoformat(),
                "world:1",
                ENTITY,
                {"lighting.any_on": True},
                "evaluation:1",
                dispatch_count=1,
            )

    def test_proposal_opens_and_agrees_inside_window(self) -> None:
        first = self._world(1, False)
        self._record_proposal(first)
        self.scorer.advance(first)
        opened = self.store.autonomy_shadow_outcomes()
        self.assertEqual(1, len(opened))
        self.assertIsNone(opened[0].agreement)
        self.assertEqual(0, opened[0].dispatch_count)

        self.clock.advance(timedelta(minutes=20))
        second = self._world(2, True)
        self.scorer.advance(second)
        closed = self.store.autonomy_shadow_outcomes()
        self.assertEqual(1, len(closed))
        self.assertTrue(closed[0].agreement)
        self.assertFalse(closed[0].strict_disagreement)
        self.assertEqual(0, closed[0].dispatch_count)

    def test_sleep_gap_closes_by_timestamp_not_waiting(self) -> None:
        first = self._world(1, False)
        self._record_proposal(first)
        self.scorer.advance(first)
        self.clock.advance(timedelta(hours=2))
        later = self._world(2, False)
        self.scorer.advance(later)
        closed = self.store.autonomy_shadow_outcomes()
        self.assertEqual(1, len(closed))
        self.assertIs(False, closed[0].agreement)
        self.assertFalse(closed[0].strict_disagreement)

    def test_opposing_change_is_strict_disagreement(self) -> None:
        first = self._world(1, False, extra=("brightness", 0.2))
        self._record_proposal(
            first,
            parameters={"lighting.any_on": True, "brightness": 0.8},
            condition=ConditionV1(
                "all",
                children=(
                    ConditionV1("eq", path="observation:lighting.any_on", value=True),
                    ConditionV1("eq", path="observation:brightness", value=0.8),
                ),
            ),
        )
        self.scorer.advance(first)
        self.clock.advance(timedelta(minutes=10))
        second = self._world(2, False, extra=("brightness", 0.1))
        self.scorer.advance(second)
        closed = self.store.autonomy_shadow_outcomes()
        self.assertEqual(1, len(closed))
        self.assertIs(False, closed[0].agreement)
        self.assertTrue(closed[0].strict_disagreement)

    def test_same_bucket_does_not_duplicate_opportunity(self) -> None:
        first = self._world(1, False)
        self._record_proposal(first, evaluation_id="evaluation:a")
        self.scorer.advance(first)
        self.clock.advance(timedelta(minutes=10))
        second = self._world(2, False)
        self._record_proposal(second, evaluation_id="evaluation:b")
        self.scorer.advance(second)
        self.assertEqual(1, len(self.store.autonomy_shadow_outcomes()))

    def test_defer_does_not_open_an_opportunity(self) -> None:
        snapshot = self._world(1, False)
        self._record_decision(
            snapshot,
            AutonomyDecisionV1(AutonomyDecisionKindV1.DEFER, rationale="wait"),
        )
        self.scorer.advance(snapshot)
        self.assertEqual((), self.store.autonomy_shadow_outcomes())

    def test_unscored_outcome_pins_trigger_snapshot(self) -> None:
        first = self._world(1, False)
        self._record_proposal(first)
        self.scorer.advance(first)
        self.clock.advance(timedelta(hours=30))
        recent = self._world(2, False)
        self.store.prune(self.clock.value)
        self.assertEqual(first, self.store.world_snapshot(first.id))
        self.assertEqual(recent, self.store.world_snapshot(recent.id))
        self.assertIn(first.id, self.store.retention_pinned_snapshot_ids())

    def test_scorer_fault_cannot_kill_heart_cycle(self) -> None:
        heart = WorldHeartV2(
            self.store,
            SimpleNamespace(
                lifecycle_observers=(),
                providers=(),
                experience_providers=(),
            ),
            DeterministicExecutiveBrainV2(),
            clock=self.clock,
        )
        heart.shadow_scorer.advance = lambda snapshot: (_ for _ in ()).throw(
            RuntimeError("scorer boom")
        )
        passes = heart.run_cycle(refresh_targets=set())
        self.assertEqual((), passes)
        kinds = [
            str(row["kind"])
            for row in self.store.connection.execute(
                "SELECT kind FROM world_events_v2"
            ).fetchall()
        ]
        self.assertIn("autonomy_shadow_failed", kinds)

    def test_shadow_report_is_byte_reproducible_and_has_no_thresholds(self) -> None:
        first = self._world(1, False)
        self._record_proposal(first, evaluation_id="evaluation:agree")
        self.scorer.advance(first)
        self.clock.advance(timedelta(minutes=20))
        self.scorer.advance(self._world(2, True))
        self.clock.advance(timedelta(minutes=20))
        third = self._world(3, False)
        self._record_proposal(third, evaluation_id="evaluation:expire")
        self.scorer.advance(third)
        self.clock.advance(timedelta(hours=2))
        self.scorer.advance(self._world(4, False))

        first_report = shadow_report(self.store, self.registry)
        second_report = shadow_report(self.store, self.registry)
        encoded = canonical_json(first_report)
        self.assertEqual(encoded, canonical_json(second_report))
        self.assertEqual(2, first_report["closed"])
        self.assertEqual(0, first_report["open"])
        self.assertEqual(0, first_report["dispatch_count"])
        self.assertEqual(0.5, first_report["engine"]["agreement_rate"])
        self.assertIn("always_defer", first_report["baselines"])
        self.assertIn("hour_of_week", first_report["baselines"])
        self.assertIn("persistence", first_report["baselines"])
        self.assertNotIn("threshold", encoded)
        self.assertNotIn("0.6", encoded)
        self.assertNotIn("60", encoded)

    def test_opportunity_key_uses_thirty_minute_bucket(self) -> None:
        first = shadow_opportunity_key(
            ENROLLMENT, ENTITY, {"on": True}, STARTED
        )
        same_bucket = shadow_opportunity_key(
            ENROLLMENT, ENTITY, {"on": True}, STARTED + timedelta(minutes=29)
        )
        next_bucket = shadow_opportunity_key(
            ENROLLMENT, ENTITY, {"on": True}, STARTED + timedelta(minutes=30)
        )
        self.assertEqual(first, same_bucket)
        self.assertNotEqual(first, next_bucket)

    def _world(
        self,
        revision: int,
        any_on: bool,
        *,
        extra: tuple[str, object] | None = None,
    ) -> WorldSnapshotV2:
        observed_at = self.clock.value.isoformat()
        observations = [
            ObservationV1(
                f"obs:{revision}:on",
                ENTITY,
                "lighting.any_on",
                any_on,
                "fixture",
                observed_at,
                EvidenceGrade.DERIVED,
            )
        ]
        if extra is not None:
            observations.append(
                ObservationV1(
                    f"obs:{revision}:{extra[0]}",
                    ENTITY,
                    extra[0],
                    extra[1],
                    "fixture",
                    observed_at,
                    EvidenceGrade.OBSERVED,
                )
            )
        entity = EntityV1(ENTITY, TARGET, "homey.zone", "fixture")
        target = TargetObservationV2(
            target_id=TARGET,
            revision=revision,
            observed_at=observed_at,
            entities=(entity,),
            relations=(),
            observations=tuple(observations),
            coverage={},
            source="fixture",
        )
        self.store.save_target_observation(target)
        snapshot = WorldSnapshotV2(
            f"world:{revision}",
            revision,
            observed_at,
            {TARGET: revision},
            (entity,),
            (),
            tuple(sorted(observations, key=lambda item: item.id)),
            {},
        )
        self.store.save_world_snapshot(snapshot)
        return snapshot

    def _record_proposal(
        self,
        snapshot: WorldSnapshotV2,
        *,
        evaluation_id: str = "evaluation:shadow",
        parameters: dict[str, object] | None = None,
        condition: ConditionV1 | None = None,
    ) -> None:
        params = parameters or {"lighting.any_on": True}
        goal = GoalSpecV2(
            id="goal:shadow",
            source_intent="shadow fixture",
            mode=GoalModeV2.MAINTAIN,
            entity_scope={"entity_ids": [ENTITY]},
            desired_effects=(
                DesiredEffectV1(
                    id="effect:zone-on",
                    capability_family="homey.lighting.zone-state",
                    entity_selector={"entity_ids": [ENTITY]},
                    condition=condition
                    or ConditionV1(
                        "eq", path="observation:lighting.any_on", value=True
                    ),
                    parameters=params,
                ),
            ),
        )
        if not self.store.has_goal(goal.id):
            self.store.create_goal(goal)
        action = ProposedActionV1(
            id=f"proposal:{evaluation_id}",
            goal_id=goal.id,
            desired_effect_id="effect:zone-on",
            capability_family="homey.lighting.zone-state",
            target_id=TARGET,
            entity_id=ENTITY,
            semantic_parameters=params,
            based_on_snapshot_id=snapshot.id,
            based_on_world_revision=snapshot.revision,
            proposed_by="fixture",
        )
        self._record_decision(
            snapshot,
            AutonomyDecisionV1(
                AutonomyDecisionKindV1.PROPOSE_EFFECT,
                proposed_action=action,
                rationale="fixture wants the zone on",
            ),
            evaluation_id=evaluation_id,
        )

    def _record_decision(
        self,
        snapshot: WorldSnapshotV2,
        decision: AutonomyDecisionV1,
        *,
        evaluation_id: str = "evaluation:shadow",
    ) -> None:
        projection = {"fixture": True}
        context = AutonomyContextV1(
            enrollment_id=ENROLLMENT,
            enrollment_revision=1,
            mode=AutonomyModeV1.OBSERVE,
            mode_epoch=1,
            previous_snapshot_id=None,
            current_snapshot_id=snapshot.id,
            current_world_revision=snapshot.revision,
            projection=projection,
            projection_sha256=artifact_sha256(projection),
        )
        evaluation = AutonomyEvaluationV1(
            id=evaluation_id,
            enrollment_id=ENROLLMENT,
            enrollment_revision=1,
            strategy_id="fixture.strategy/v1",
            mode=AutonomyModeV1.OBSERVE,
            mode_epoch=1,
            context=context,
            decision=decision,
            strategy_fingerprint="strategy-fp",
            manifest_fingerprint="manifest-fp",
        )
        self.store.save_autonomy_evaluation(evaluation)


if __name__ == "__main__":
    unittest.main()
