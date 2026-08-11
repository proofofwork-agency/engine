from __future__ import annotations

import importlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from engine_reference_world import create_plugin
from engine_sdk import (
    BrainDecisionV2,
    ConditionV1,
    DecisionKindV2,
    DesiredEffectV1,
    EvidenceGrade,
    ExecutionReceiptV2,
    ExecutionStateV2,
    GoalModeV2,
    GoalSpecV2,
    LearningStatus,
    PolicyOutcome,
    ProposedActionV1,
    StandingMandateV1,
    artifact_sha256,
    canonical_json,
)
from engine_sdk.scaffold import scaffold_plugin

from engine import (
    DeterministicExecutiveBrainV2,
    EngineStore,
    PluginRegistryV2,
    WorldHeartV2,
    WorldStore,
)
from engine.conditions_v2 import evaluate_condition
from engine.learning_v2 import BoundedPreferenceLearner
from engine.models import Goal

PLUGIN_ID = "engine.reference-world"
TARGET_ID = "engine.reference-world.warehouse"
ENTITY_ID = "warehouse:bin:reserve"
FAMILY = "warehouse.transfer-bin"


class WorldV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-world-v2-")
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _system(self, *, executor: Any | None = None):
        plugin = create_plugin(self.base / "warehouse.sqlite3")
        self.addCleanup(plugin.providers[0].store.close)
        if executor is not None:
            plugin = replace(plugin, executors=(executor,))
        registry = PluginRegistryV2()
        registry.register(plugin, "plugins/reference-world")
        store = WorldStore(self.base / "engine.sqlite3")
        self.addCleanup(store.close)
        mandate = _mandate()
        store.save_mandate(mandate)
        goal = _goal(mandate.id)
        store.create_goal(goal)
        brain = DeterministicExecutiveBrainV2()
        heart = WorldHeartV2(store, registry, brain)
        return plugin, registry, store, brain, heart, goal

    def test_reference_world_closes_full_lifecycle_then_stays_cognitively_quiet(self) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        del plugin, registry

        first = heart.run_once(goal.id)

        self.assertEqual("waiting", first.status)
        self.assertTrue(first.brain_called)
        self.assertFalse(first.effect_achieved)
        self.assertTrue(
            any(
                item["kind"] == "proposal_created"
                and item["payload"]["proposal_id"] == first.proposal_id
                for item in store.events(goal.id)
            )
        )
        self.assertEqual(
            {
                "proposals": 1,
                "requests": 1,
                "decisions": 1,
                "authorizations": 1,
                "receipts": 1,
                "effects": 1,
            },
            store.lifecycle_counts(goal.id),
        )
        calls = store.brain_call_count(goal.id)

        completed = heart.run_once(goal.id)

        self.assertEqual("monitoring", completed.status)
        self.assertFalse(completed.brain_called)
        self.assertTrue(completed.effect_achieved)
        self.assertEqual(
            {
                "proposals": 1,
                "requests": 1,
                "decisions": 1,
                "authorizations": 1,
                "receipts": 2,
                "effects": 2,
            },
            store.lifecycle_counts(goal.id),
        )

        stable = heart.run_once(goal.id)

        self.assertEqual("monitoring", stable.status)
        self.assertFalse(stable.brain_called)
        self.assertEqual(calls, store.brain_call_count(goal.id))
        self.assertEqual(1, brain.calls)

    def test_lifecycle_observer_starts_at_registration_and_retries_failure(self) -> None:
        plugin, registry, store, brain, _, goal = self._system()
        del plugin
        store.append_event(goal.id, "before_observer", "fixture", {})
        observer = _RetryingLifecycleObserver()
        heart = WorldHeartV2(
            store,
            registry,
            brain,
            lifecycle_observers=(observer,),
        )
        store.append_event(
            goal.id,
            "goal_created",
            "fixture",
            {"id": "goal:after-observer"},
        )

        heart.run_cycle()
        self.assertEqual(1, observer.calls)
        self.assertEqual((), observer.delivered)

        heart.run_cycle()
        self.assertEqual(2, observer.calls)
        self.assertIn("goal_created", observer.delivered)
        self.assertNotIn("before_observer", observer.delivered)
        self.assertTrue(
            any(
                item["kind"] == "lifecycle_observer_failed"
                for item in store.events()
            )
        )

    def test_lifecycle_cursor_survives_restart_without_drop_or_duplicate(self) -> None:
        plugin, registry, store, brain, _, goal = self._system()
        del plugin
        store.append_event(goal.id, "before_observer", "fixture", {})
        first_observer = _RecordingLifecycleObserver()
        heart = WorldHeartV2(
            store, registry, brain, lifecycle_observers=(first_observer,)
        )
        store.append_event(goal.id, "goal_created", "fixture", {"id": "goal:first"})
        heart.notify_lifecycle_observers()
        self.assertEqual(("goal_created",), first_observer.delivered)

        store.append_event(
            goal.id,
            "routine_activated",
            "fixture",
            {"routine_id": "routine:while-down"},
        )

        second_observer = _RecordingLifecycleObserver()
        restarted = WorldHeartV2(
            store, registry, brain, lifecycle_observers=(second_observer,)
        )
        restarted.notify_lifecycle_observers()
        self.assertEqual(("routine_activated",), second_observer.delivered)
        self.assertEqual(
            store.latest_event_sequence(),
            store.lifecycle_cursor(_RecordingLifecycleObserver.id),
        )

    def test_failed_delivery_keeps_durable_cursor_for_redelivery_after_restart(
        self,
    ) -> None:
        plugin, registry, store, brain, _, goal = self._system()
        del plugin
        baseline = store.latest_event_sequence()
        failing = _RecordingLifecycleObserver(fail_times=1)
        heart = WorldHeartV2(store, registry, brain, lifecycle_observers=(failing,))
        self.assertEqual(baseline, store.lifecycle_cursor(_RecordingLifecycleObserver.id))
        store.append_event(goal.id, "goal_created", "fixture", {"id": "goal:retry"})

        heart.notify_lifecycle_observers()

        self.assertEqual((), failing.delivered)
        self.assertEqual(
            baseline, store.lifecycle_cursor(_RecordingLifecycleObserver.id)
        )

        recovered = _RecordingLifecycleObserver()
        restarted = WorldHeartV2(
            store, registry, brain, lifecycle_observers=(recovered,)
        )
        restarted.notify_lifecycle_observers()
        self.assertEqual(
            ("goal_created", "lifecycle_observer_failed"), recovered.delivered
        )
        self.assertEqual(
            store.latest_event_sequence(),
            store.lifecycle_cursor(_RecordingLifecycleObserver.id),
        )

    def test_lifecycle_cursor_seed_and_advance_are_cross_connection_monotonic(
        self,
    ) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        del plugin, registry, brain, heart
        store.append_event(goal.id, "before_registration", "fixture", {})
        baseline = store.latest_event_sequence()
        observer_id = "test.concurrent-observer"

        first = store.initialize_lifecycle_cursor(observer_id)
        store.append_event(goal.id, "after_registration", "fixture", {})
        latest = store.latest_event_sequence()
        peer = WorldStore(store.path)
        self.addCleanup(peer.close)
        second = peer.initialize_lifecycle_cursor(observer_id)

        self.assertEqual(baseline, first)
        self.assertEqual(baseline, second)
        self.assertEqual(latest, peer.save_lifecycle_cursor(observer_id, latest))
        self.assertEqual(latest, store.save_lifecycle_cursor(observer_id, baseline))
        self.assertEqual(latest, peer.lifecycle_cursor(observer_id))

    def test_generated_bootstrap_world_runs_same_maintain_heart_without_core_change(self) -> None:
        root = scaffold_plugin(self.base, "generated-world", "world")
        sys.path.insert(0, str(root / "src"))
        try:
            module = importlib.import_module("generated_world.plugin")
            plugin = module.load_plugin()
            registry = PluginRegistryV2()
            registry.register(plugin, root)
            store = WorldStore(self.base / "generated-engine.sqlite3")
            self.addCleanup(store.close)
            now = datetime.now(UTC)
            mandate = StandingMandateV1(
                "mandate:generated",
                ("example.generated-world",),
                ("example.generated-world.warehouse",),
                (ENTITY_ID,),
                (FAMILY,),
                {}, (), (),
                (now - timedelta(minutes=1)).isoformat(),
                (now + timedelta(days=1)).isoformat(),
                {"example.generated-world": "0.1.0"},
                "owner",
            )
            store.save_mandate(mandate)
            goal = replace(
                _goal(mandate.id),
                id="goal:generated",
                entity_scope={"target_ids": ["example.generated-world.warehouse"]},
            )
            store.create_goal(goal)
            heart = WorldHeartV2(
                store, registry, DeterministicExecutiveBrainV2()
            )

            result = heart.run_once(goal.id)

            self.assertEqual("monitoring", result.status)
            self.assertTrue(result.effect_achieved)
        finally:
            sys.path.remove(str(root / "src"))
            for name in tuple(sys.modules):
                if name == "generated_world" or name.startswith("generated_world."):
                    del sys.modules[name]

    def test_goal_world_and_target_state_survive_process_restart_without_model_session(self) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        self.assertEqual("waiting", heart.run_once(goal.id).status)
        plugin.providers[0].store.close()
        store.close()
        del plugin, registry, brain, heart

        plugin2 = create_plugin(self.base / "warehouse.sqlite3")
        self.addCleanup(plugin2.providers[0].store.close)
        registry2 = PluginRegistryV2()
        registry2.register(plugin2, "plugins/reference-world")
        store2 = WorldStore(self.base / "engine.sqlite3")
        self.addCleanup(store2.close)
        brain2 = DeterministicExecutiveBrainV2()
        heart2 = WorldHeartV2(store2, registry2, brain2)

        result = heart2.run_once(goal.id)

        self.assertEqual("monitoring", result.status)
        self.assertFalse(result.brain_called)
        self.assertEqual(0, brain2.calls)
        self.assertEqual(3, _reserve_count(store2.latest_world_snapshot()))

    def test_task_deadline_cancels_durably_without_applying_the_effect(self) -> None:
        plugin, registry, store, brain, _, goal = self._system()
        clock = _MutableClock(datetime.now(UTC))
        heart = WorldHeartV2(store, registry, brain, clock=clock)

        started = heart.run_once(goal.id)
        self.assertEqual("waiting", started.status)
        clock.advance(timedelta(seconds=6))

        cancelled = heart.run_once(goal.id)

        self.assertEqual("active", cancelled.status)
        self.assertFalse(cancelled.effect_achieved)
        task = plugin.providers[0].store.task(started.proposal_id)
        self.assertIsNotNone(task)
        self.assertEqual("cancelled", task["status"])
        self.assertEqual(0, _reserve_count(store.latest_world_snapshot()))
        self.assertIsNone(store.pending_task(goal.id))

    def test_successful_typed_plan_is_reused_for_same_recurrent_situation(self) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        del registry
        self.assertEqual("waiting", heart.run_once(goal.id).status)
        self.assertEqual("monitoring", heart.run_once(goal.id).status)
        connection = plugin.providers[0].store.connection
        connection.execute(
            "UPDATE state SET incoming=incoming+reserve, reserve=0 WHERE id=1"
        )
        connection.commit()
        calls = store.brain_call_count(goal.id)

        started = heart.run_once(goal.id)
        repaired = heart.run_once(goal.id)

        self.assertEqual("waiting", started.status)
        self.assertEqual("monitoring", repaired.status)
        self.assertFalse(repaired.brain_called)
        self.assertEqual(calls, store.brain_call_count(goal.id))
        self.assertEqual(1, brain.calls)

    def test_ack_without_effect_is_observed_as_failure_not_success(self) -> None:
        plugin = create_plugin(self.base / "warehouse.sqlite3")
        self.addCleanup(plugin.providers[0].store.close)
        ack_only = _AckOnlyExecutor()
        plugin = replace(plugin, executors=(ack_only,))
        registry = PluginRegistryV2()
        registry.register(plugin, "plugins/reference-world")
        store = WorldStore(self.base / "engine.sqlite3")
        self.addCleanup(store.close)
        mandate = _mandate()
        store.save_mandate(mandate)
        goal = _goal(mandate.id)
        store.create_goal(goal)
        heart = WorldHeartV2(store, registry, DeterministicExecutiveBrainV2())

        result = heart.run_once(goal.id)

        self.assertEqual("active", result.status)
        self.assertFalse(result.effect_achieved)
        self.assertEqual(1, ack_only.calls)
        self.assertIn("below", result.reason)
        self.assertEqual(0, _reserve_count(store.latest_world_snapshot()))

    def test_malformed_stale_proposal_never_reaches_controller_or_dispatch(self) -> None:
        plugin = create_plugin(self.base / "warehouse.sqlite3")
        self.addCleanup(plugin.providers[0].store.close)
        registry = PluginRegistryV2()
        registry.register(plugin, "plugins/reference-world")
        store = WorldStore(self.base / "engine.sqlite3")
        self.addCleanup(store.close)
        mandate = _mandate()
        store.save_mandate(mandate)
        goal = _goal(mandate.id)
        store.create_goal(goal)
        heart = WorldHeartV2(store, registry, _StaleBrain())

        result = heart.run_once(goal.id)

        self.assertEqual("waiting", result.status)
        self.assertIn("stale", result.reason)
        self.assertEqual(
            {"proposals": 1, "requests": 0, "decisions": 0, "authorizations": 0, "receipts": 0, "effects": 0},
            store.lifecycle_counts(goal.id),
        )
        self.assertEqual(0, _reserve_count(store.latest_world_snapshot()))

    def test_expired_or_out_of_scope_mandate_denies_before_dispatch(self) -> None:
        plugin = create_plugin(self.base / "warehouse.sqlite3")
        self.addCleanup(plugin.providers[0].store.close)
        registry = PluginRegistryV2()
        registry.register(plugin, "plugins/reference-world")
        store = WorldStore(self.base / "engine.sqlite3")
        self.addCleanup(store.close)
        expired = _mandate(expired=True)
        store.save_mandate(expired)
        goal = _goal(expired.id)
        store.create_goal(goal)
        heart = WorldHeartV2(store, registry, DeterministicExecutiveBrainV2())

        result = heart.run_once(goal.id)

        self.assertEqual(PolicyOutcome.DENY, result.policy_outcome)
        self.assertEqual(
            {"proposals": 1, "requests": 1, "decisions": 1, "authorizations": 0, "receipts": 0, "effects": 0},
            store.lifecycle_counts(goal.id),
        )

    def test_same_target_revision_cannot_change_state(self) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        del heart, goal
        observation = plugin.providers[0].observe()
        clock = _MutableClock(datetime.fromisoformat(observation.observed_at))
        first = replace(observation, observed_at=clock().isoformat())
        self.assertTrue(store.save_target_observation(first))
        clock.advance(timedelta(seconds=9))
        confirmation = replace(observation, observed_at=clock().isoformat())
        self.assertFalse(store.save_target_observation(confirmation))
        latest = store.latest_target_observation(observation.target_id)
        assert latest is not None
        self.assertEqual(first.observed_at, latest.observed_at)
        self.assertEqual(confirmation.observed_at, latest.confirmed_at)
        self.assertEqual(
            1,
            store.connection.execute(
                "SELECT COUNT(*) FROM target_observations_v2 WHERE target_id=?",
                (observation.target_id,),
            ).fetchone()[0],
        )

        clock.advance(timedelta(seconds=2))
        confirming_heart = WorldHeartV2(store, registry, brain, clock=clock)
        snapshot = confirming_heart.observe_connected_world(refresh_targets=set())
        self.assertFalse(snapshot.coverage["targets"][observation.target_id]["stale"])

        changed = replace(
            observation,
            coverage={"bins": "partial"},
        )
        with self.assertRaisesRegex(ValueError, "same target revision"):
            store.save_target_observation(changed)

    def test_target_confirmation_columns_migrate_additively(self) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        del registry, store, brain, heart, goal
        observation = plugin.providers[0].observe()
        body = observation.to_dict()
        body.pop("confirmed_at")
        path = self.base / "legacy-target-observation.sqlite3"
        connection = sqlite3.connect(path)
        connection.execute(
            """
            CREATE TABLE target_observations_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                body_json TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(target_id, revision)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO target_observations_v2(
                target_id, revision, body_json, artifact_sha256, observed_at
            ) VALUES(?,?,?,?,?)
            """,
            (
                observation.target_id,
                observation.revision,
                canonical_json(body),
                artifact_sha256(body),
                observation.observed_at,
            ),
        )
        connection.commit()
        connection.close()

        migrated = WorldStore(path)
        self.addCleanup(migrated.close)
        columns = {
            str(row["name"])
            for row in migrated.connection.execute(
                "PRAGMA table_info(target_observations_v2)"
            ).fetchall()
        }
        self.assertIn("semantic_sha256", columns)
        self.assertIn("confirmed_at", columns)
        latest = migrated.latest_target_observation(observation.target_id)
        assert latest is not None
        self.assertEqual(observation.observed_at, latest.confirmed_at)
        row = migrated.connection.execute(
            "SELECT semantic_sha256 FROM target_observations_v2"
        ).fetchone()
        self.assertEqual(latest.semantic_fingerprint(), row["semantic_sha256"])

    def test_reference_snapshot_round_trip_preserves_hashes_and_stale_grade(
        self,
    ) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        del heart, goal
        boundary = datetime.now(UTC)
        clock = _MutableClock(boundary)
        confirming_heart = WorldHeartV2(store, registry, brain, clock=clock)
        fresh = confirming_heart.observe_connected_world(refresh_targets=None)
        clock.advance(
            timedelta(seconds=plugin.providers[0].freshness_seconds + 1)
        )
        stale = confirming_heart.observe_connected_world(refresh_targets=set())

        loaded = store.world_snapshot(stale.id)

        self.assertEqual(stale.sha256, loaded.sha256)
        self.assertEqual(
            stale.semantic_fingerprint(), loaded.semantic_fingerprint()
        )
        self.assertTrue(
            all(
                item.evidence_grade is EvidenceGrade.STALE
                for item in loaded.observations
            )
        )
        self.assertNotEqual(fresh.semantic_fingerprint(), loaded.semantic_fingerprint())
        row = store.connection.execute(
            "SELECT body_json FROM world_snapshots_v2 WHERE snapshot_id=?",
            (stale.id,),
        ).fetchone()
        self.assertEqual(
            {
                "coverage",
                "observed_at",
                "revision",
                "snapshot_id",
                "target_revisions",
            },
            set(json.loads(row["body_json"])),
        )

    def test_legacy_and_reference_world_snapshots_coexist(self) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        del plugin, registry, brain, goal
        legacy = heart.observe_connected_world(refresh_targets=None)
        store.connection.execute(
            "UPDATE world_snapshots_v2 SET body_json=? WHERE snapshot_id=?",
            (canonical_json(legacy), legacy.id),
        )
        store.connection.commit()
        reference = heart.observe_connected_world(refresh_targets=None)

        loaded_legacy = store.world_snapshot(legacy.id)
        loaded_reference = store.world_snapshot(reference.id)

        self.assertEqual(legacy.sha256, loaded_legacy.sha256)
        self.assertEqual(
            legacy.semantic_fingerprint(),
            loaded_legacy.semantic_fingerprint(),
        )
        self.assertEqual(reference.sha256, loaded_reference.sha256)
        self.assertEqual(
            reference.semantic_fingerprint(),
            loaded_reference.semantic_fingerprint(),
        )
        self.assertEqual(reference, store.latest_world_snapshot())

    def test_compressed_and_legacy_target_observation_bodies_both_load(
        self,
    ) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        del registry, brain, heart, goal
        observation = plugin.providers[0].observe()
        store.save_target_observation(observation)
        row = store.connection.execute(
            """
            SELECT body_json, typeof(body_json) AS storage_type
            FROM target_observations_v2 WHERE target_id=? AND revision=?
            """,
            (observation.target_id, observation.revision),
        ).fetchone()
        self.assertEqual("blob", row["storage_type"])
        self.assertIsInstance(row["body_json"], bytes)
        compressed = store.latest_target_observation(observation.target_id)
        assert compressed is not None
        self.assertEqual(
            observation.semantic_fingerprint(),
            compressed.semantic_fingerprint(),
        )

        store.connection.execute(
            """
            UPDATE target_observations_v2 SET body_json=?
            WHERE target_id=? AND revision=?
            """,
            (
                canonical_json(observation),
                observation.target_id,
                observation.revision,
            ),
        )
        store.connection.commit()
        row = store.connection.execute(
            """
            SELECT typeof(body_json) AS storage_type
            FROM target_observations_v2 WHERE target_id=? AND revision=?
            """,
            (observation.target_id, observation.revision),
        ).fetchone()
        self.assertEqual("text", row["storage_type"])
        legacy = store.latest_target_observation(observation.target_id)
        assert legacy is not None
        self.assertEqual(
            observation.semantic_fingerprint(), legacy.semantic_fingerprint()
        )

    def test_referenced_target_tamper_fails_world_reconstruction(self) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        del plugin, registry, brain, goal
        snapshot = heart.observe_connected_world(refresh_targets=None)
        target = store.latest_target_observation(TARGET_ID)
        assert target is not None
        original = target.observations[0]
        tampered = replace(
            target,
            observations=(
                replace(original, value=int(original.value) + 1),
                *target.observations[1:],
            ),
        )
        store.connection.execute(
            """
            UPDATE target_observations_v2 SET body_json=?
            WHERE target_id=? AND revision=?
            """,
            (canonical_json(tampered), target.target_id, target.revision),
        )
        store.connection.commit()

        with self.assertRaisesRegex(ValueError, "artifact mismatch"):
            store.world_snapshot(snapshot.id)

    def test_read_only_snapshot_verifier_accepts_synthetic_mixed_store(self) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        del plugin, registry, brain, goal
        legacy = heart.observe_connected_world(refresh_targets=None)
        store.connection.execute(
            "UPDATE world_snapshots_v2 SET body_json=? WHERE snapshot_id=?",
            (canonical_json(legacy), legacy.id),
        )
        store.connection.commit()
        heart.observe_connected_world(refresh_targets=None)
        database = store.path
        store.close()

        result = subprocess.run(
            (
                sys.executable,
                "tools/verify_snapshot_reconstruction.py",
                "--database",
                str(database),
            ),
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(
            "verified=2 legacy=1 reference=1 failures=0", result.stdout
        )

    def test_declarative_conditions_preserve_units_unknown_and_boolean_composition(self) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        del plugin, registry, brain
        snapshot = heart.observe_world(goal, refresh_targets=None)
        condition = ConditionV1(
            "all",
            children=(
                ConditionV1("gte", path="observation:bin.count", value=0, unit="crate"),
                ConditionV1("not", children=(ConditionV1("lt", path="observation:bin.count", value=0, unit="crate"),)),
            ),
        )
        selector = {"entity_ids": [ENTITY_ID]}

        self.assertTrue(evaluate_condition(condition, snapshot, selector=selector).value)
        mismatch = evaluate_condition(
            ConditionV1("gte", path="observation:bin.count", value=0, unit="kg"),
            snapshot,
            selector=selector,
        )
        self.assertIsNone(mismatch.value)
        self.assertEqual(EvidenceGrade.CONFLICTING, mismatch.grade)

    def test_v1_goal_migrates_to_observe_only_target_selector(self) -> None:
        path = self.base / "migration.sqlite3"
        old = EngineStore(path)
        old.create_goal(Goal("legacy", "old-target", "legacy intent", {"done": True}))
        old.close()

        store = WorldStore(path)
        self.addCleanup(store.close)
        migrated = store.get_goal("legacy")

        self.assertEqual({"target_ids": ["old-target"]}, migrated.entity_scope)
        self.assertEqual("imported_observe_only", migrated.status)
        self.assertIsNone(migrated.mandate_id)

    def test_explicit_learning_is_immediate_but_inferred_habit_waits_for_fixed_gate(self) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        del plugin, registry, brain, heart
        learner = BoundedPreferenceLearner(store)
        corrected = learner.record_explicit_correction(
            goal,
            field_path="lighting.brightness_band",
            old_value=[0.2, 0.7],
            new_value=[0.15, 0.6],
            context={"period": "quiet"},
            observed_at=datetime.now(UTC).isoformat(),
        )
        self.assertEqual([0.15, 0.6], corrected.budgets["preferences"]["lighting.brightness_band"])
        base = datetime.now(UTC) - timedelta(days=10)
        for index in range(5):
            learner.record_manual_override(
                corrected.id,
                field_path="lighting.switch_off_delay_seconds",
                old_value=60,
                new_value=120,
                context={"presence": False, "period": "quiet"},
                observed_at=(base + timedelta(days=index // 2)).isoformat(),
            )
        mandate = replace(_mandate(), learning_permissions=("learning.low-risk",))
        candidate = learner.candidate(
            corrected, "lighting.switch_off_delay_seconds", mandate
        )
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(LearningStatus.SHADOW, candidate.status)
        self.assertTrue(
            any(
                item["kind"] == "learning_candidate_created"
                and item["payload"]["candidate_id"] == candidate.id
                for item in store.events()
            )
        )
        before_shadow_end = learner.promote(
            corrected, candidate, ({"achieved": True},), now=base + timedelta(days=6)
        )
        self.assertIsNone(before_shadow_end)
        promoted = learner.promote(
            corrected,
            candidate,
            ({"achieved": True, "effect_id": "shadow-1"},),
            now=datetime.fromisoformat(candidate.shadow_ends_at) + timedelta(seconds=1),
        )
        self.assertIsNotNone(promoted)
        assert promoted is not None
        self.assertEqual(120, promoted.budgets["preferences"]["lighting.switch_off_delay_seconds"])

    def test_sensitive_learning_domains_never_auto_promote(self) -> None:
        plugin, registry, store, brain, heart, goal = self._system()
        del plugin, registry, brain, heart
        learner = BoundedPreferenceLearner(store)
        now = datetime.now(UTC)
        for index in range(5):
            learner.record_manual_override(
                goal.id,
                field_path="camera.surveillance_mode",
                old_value=False,
                new_value=True,
                context={"mode": "away"},
                observed_at=(now - timedelta(days=4 - index // 2)).isoformat(),
            )
        mandate = replace(_mandate(), learning_permissions=("learning.low-risk",))
        self.assertIsNone(learner.candidate(goal, "camera.surveillance_mode", mandate))


class _RecordingLifecycleObserver:
    id = "test.lifecycle-recorder"
    plugin_id = "test.notifications"

    def __init__(self, *, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.delivered: tuple[str, ...] = ()

    def observe(self, events: tuple[Any, ...]) -> None:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("delivery transport failed")
        self.delivered += tuple(item.kind for item in events)


class _RetryingLifecycleObserver:
    id = "test.lifecycle-observer"
    plugin_id = "test.notifications"

    def __init__(self) -> None:
        self.calls = 0
        self.delivered: tuple[str, ...] = ()

    def observe(self, events: tuple[Any, ...]) -> None:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary delivery failure")
        self.delivered = tuple(item.kind for item in events)


class _AckOnlyExecutor:
    id = "warehouse-task-executor"
    plugin_id = PLUGIN_ID

    def __init__(self) -> None:
        self.calls = 0

    def dispatch(self, request: Any, authorization: Any) -> ExecutionReceiptV2:
        self.calls += 1
        return ExecutionReceiptV2(
            "receipt:ack-only", request.id, authorization.id, request.target_id,
            request.capability_id, ExecutionStateV2.SUCCEEDED,
            datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat(), True,
            {"ack": True}, adapter_version="test",
        )

    def poll(self, external_handle: str) -> Any:
        raise KeyError(external_handle)

    def cancel(self, external_handle: str) -> Any:
        raise KeyError(external_handle)


class _MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


class _StaleBrain:
    id = "test.stale-brain/v1"

    def decide(self, goal: GoalSpecV2, context: dict[str, object]) -> BrainDecisionV2:
        world = context["world"]
        assert isinstance(world, dict)
        return BrainDecisionV2(
            kind=DecisionKindV2.PROPOSE_EFFECT,
            proposed_action=ProposedActionV1(
                "proposal:stale", goal.id, "reserve-minimum", FAMILY,
                TARGET_ID, ENTITY_ID, {"minimum_count": 3},
                "world:stale", int(world["revision"]), self.id,
            ),
        )


def _mandate(*, expired: bool = False) -> StandingMandateV1:
    now = datetime.now(UTC)
    return StandingMandateV1(
        id="mandate:reference",
        plugin_ids=(PLUGIN_ID,),
        target_ids=(TARGET_ID,),
        entity_ids=(ENTITY_ID,),
        capability_families=(FAMILY,),
        limits={}, privacy_permissions=(), learning_permissions=(),
        valid_from=(now - timedelta(days=2)).isoformat(),
        valid_until=(now - timedelta(days=1) if expired else now + timedelta(days=1)).isoformat(),
        manifest_versions={PLUGIN_ID: "0.2.0"},
        activated_by="owner",
    )


def _goal(mandate_id: str) -> GoalSpecV2:
    effect = DesiredEffectV1(
        id="reserve-minimum",
        capability_family=FAMILY,
        entity_selector={"entity_ids": [ENTITY_ID]},
        condition=ConditionV1(
            "gte", path="observation:bin.count", value=3, unit="crate"
        ),
        parameters={"minimum_count": 3},
    )
    return GoalSpecV2(
        id="goal:reference",
        source_intent="Maintain at least three crates in the reserve bin",
        mode=GoalModeV2.MAINTAIN,
        entity_scope={"target_ids": [TARGET_ID]},
        desired_effects=(effect,),
        mandate_id=mandate_id,
    )


def _reserve_count(snapshot: Any) -> int:
    assert snapshot is not None
    return next(
        int(item.value) for item in snapshot.observations
        if item.entity_id == ENTITY_ID and item.property == "bin.count"
    )


if __name__ == "__main__":
    unittest.main()
