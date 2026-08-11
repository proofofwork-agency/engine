from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from engine_reference_world import create_plugin
from engine_sdk import (
    EntityV1,
    EvidenceGrade,
    ObservationV1,
    TargetObservationV2,
)
from test_world_v2 import _goal, _mandate, _MutableClock

from engine import (
    DeterministicExecutiveBrainV2,
    PluginRegistryV2,
    WorldHeartV2,
    WorldStore,
)

TARGET_ID = "engine.reference-world.warehouse"


class DaemonSurvivalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-daemon-")
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_escaping_cycle_faults_back_off_to_cap_and_open_circuit_once(
        self,
    ) -> None:
        runtime_time = _RuntimeTime()
        _, provider, store, heart = self._system(runtime_time=runtime_time)
        provider.poll_interval_seconds = 0.0

        with patch.object(
            store,
            "save_world_snapshot",
            side_effect=OSError("simulated disk full"),
        ):
            passes = heart.run_forever(threading.Event(), max_passes=9)

        self.assertEqual(9, passes)
        failures = self._events(store, "cycle_failed")
        self.assertEqual(9, len(failures))
        delays = [item["payload"]["backoff_seconds"] for item in failures]
        self.assertEqual([1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0], delays)
        self.assertEqual(delays[:-1], runtime_time.waits)
        self.assertTrue(all(left <= right for left, right in zip(delays, delays[1:])))
        circuits = self._events(store, "runtime_circuit_open")
        self.assertEqual(1, len(circuits))
        self.assertEqual(5, circuits[0]["payload"]["consecutive_failures"])
        self.assertEqual("OSError", failures[0]["payload"]["exception_type"])
        self.assertEqual("simulated disk full", failures[0]["payload"]["message"])

    def test_success_resets_cycle_backoff_and_circuit_streak(self) -> None:
        runtime_time = _RuntimeTime()
        _, provider, store, heart = self._system(runtime_time=runtime_time)
        provider.poll_interval_seconds = 0.0
        original_save = store.save_world_snapshot
        calls = 0

        def flaky_save(snapshot):
            nonlocal calls
            calls += 1
            if calls in {1, 2, 3, 5}:
                raise OSError(f"transient store failure {calls}")
            return original_save(snapshot)

        with patch.object(store, "save_world_snapshot", side_effect=flaky_save):
            passes = heart.run_forever(threading.Event(), max_passes=6)

        self.assertEqual(6, passes)
        failures = self._events(store, "cycle_failed")
        self.assertEqual([1.0, 2.0, 4.0, 1.0], runtime_time.waits)
        self.assertEqual(
            [1.0, 2.0, 4.0, 1.0],
            [item["payload"]["backoff_seconds"] for item in failures],
        )
        self.assertEqual((), self._events(store, "runtime_circuit_open"))
        self.assertIsNotNone(store.latest_world_snapshot())

    def test_routine_learner_failure_does_not_skip_goal_loop(self) -> None:
        _, _, store, heart = self._system(with_goal=True)

        with patch.object(
            heart.routine_learner,
            "advance",
            side_effect=RuntimeError("learner fixture failed"),
        ):
            passes = heart.run_cycle()

        self.assertEqual(1, len(passes))
        self.assertEqual("goal:reference", passes[0].goal_id)
        failures = self._events(store, "routine_learner_failed")
        self.assertEqual(1, len(failures))
        self.assertEqual(
            "learner fixture failed", failures[0]["payload"]["message"]
        )
        self.assertIsNotNone(store.latest_world_snapshot())

    def test_prune_failure_does_not_block_observation_cycle(self) -> None:
        _, provider, store, heart = self._system()
        provider.poll_interval_seconds = 0.0

        with patch.object(
            store,
            "prune",
            side_effect=RuntimeError("retention fixture failed"),
        ):
            passes = heart.run_forever(threading.Event(), max_passes=1)

        self.assertEqual(1, passes)
        self.assertIsNotNone(store.latest_world_snapshot())
        failures = self._events(store, "prune_failed")
        self.assertEqual(1, len(failures))
        self.assertEqual(
            "retention fixture failed", failures[0]["payload"]["message"]
        )
        self.assertEqual((), self._events(store, "cycle_failed"))

    def test_collision_drops_later_registry_provider_and_keeps_snapshot_valid(
        self,
    ) -> None:
        clock = _MutableClock(datetime(2026, 8, 11, 12, tzinfo=UTC))
        earlier = _CollisionProvider(
            "plugin.earlier",
            "target:a-earlier",
            clock,
            ("entity:shared",),
        )
        later = _CollisionProvider(
            "plugin.later",
            "target:z-later",
            clock,
            ("entity:shared", "entity:later-only"),
        )
        registry = PluginRegistryV2()
        registry._targets = {
            earlier.target_id: earlier,
            later.target_id: later,
        }
        store = WorldStore(self.base / "collision.sqlite3")
        self.addCleanup(store.close)
        heart = WorldHeartV2(
            store,
            registry,
            DeterministicExecutiveBrainV2(),
            clock=clock,
        )

        snapshot = heart.observe_connected_world(refresh_targets=None)

        self.assertEqual(("entity:shared",), tuple(item.id for item in snapshot.entities))
        self.assertEqual({earlier.target_id: 1}, snapshot.target_revisions)
        self.assertNotIn("entity:later-only", {item.id for item in snapshot.entities})
        later_coverage = snapshot.coverage["targets"][later.target_id]
        self.assertFalse(later_coverage["available"])
        self.assertTrue(later_coverage["stale"])
        self.assertIn("collision", snapshot.coverage["failures"][later.target_id])
        loaded = store.world_snapshot(snapshot.id)
        self.assertEqual(snapshot.sha256, loaded.sha256)
        collisions = self._events(store, "entity_identity_collision")
        self.assertEqual(1, len(collisions))
        self.assertEqual("entity:shared", collisions[0]["payload"]["entity_id"])
        self.assertEqual("plugin.earlier", collisions[0]["payload"]["earlier_source"])
        self.assertEqual("plugin.later", collisions[0]["payload"]["later_source"])

    def test_subscription_outage_polls_and_restores_without_event_spam(self) -> None:
        runtime_time = _RuntimeTime(wait_jumps=[300.0, 300.0])
        _, provider, store, heart = self._system(runtime_time=runtime_time)
        provider.poll_interval_seconds = 601.0
        subscribe_calls = 0
        unsubscribed = 0

        def flaky_subscribe(callback):
            del callback
            nonlocal subscribe_calls, unsubscribed
            subscribe_calls += 1
            if subscribe_calls < 3:
                raise ConnectionError("subscription transport unavailable")

            def unsubscribe() -> None:
                nonlocal unsubscribed
                unsubscribed += 1

            return unsubscribe

        provider.subscribe = flaky_subscribe

        passes = heart.run_forever(threading.Event(), max_passes=2)

        self.assertEqual(2, passes)
        self.assertEqual(3, subscribe_calls)
        self.assertEqual(1, unsubscribed)
        self.assertEqual(2, self._row_count(store, "world_snapshots_v2"))
        failures = self._events(store, "subscription_failed")
        restored = self._events(store, "subscription_restored")
        self.assertEqual(1, len(failures))
        self.assertEqual(1, len(restored))
        self.assertEqual(TARGET_ID, restored[0]["payload"]["target_id"])

    def _system(
        self,
        *,
        runtime_time: _RuntimeTime | None = None,
        with_goal: bool = False,
    ):
        plugin = create_plugin(self.base / "warehouse.sqlite3")
        provider = plugin.providers[0]
        self.addCleanup(provider.store.close)
        registry = PluginRegistryV2()
        registry.register(plugin, "plugins/reference-world")
        store = WorldStore(self.base / "engine.sqlite3")
        self.addCleanup(store.close)
        clock = runtime_time.clock if runtime_time is not None else _MutableClock(
            datetime(2026, 8, 11, 12, tzinfo=UTC)
        )
        if with_goal:
            mandate = _mandate()
            store.save_mandate(mandate)
            store.create_goal(_goal(mandate.id))
        heart = WorldHeartV2(
            store,
            registry,
            DeterministicExecutiveBrainV2(),
            clock=clock,
            monotonic=(runtime_time.monotonic if runtime_time else None),
            waiter=(runtime_time.wait if runtime_time else None),
        )
        return registry, provider, store, heart

    @staticmethod
    def _events(store: WorldStore, kind: str):
        return tuple(item for item in store.events() if item["kind"] == kind)

    @staticmethod
    def _row_count(store: WorldStore, table: str) -> int:
        row = store.connection.execute(
            f'SELECT COUNT(*) AS value FROM "{table}"'
        ).fetchone()
        return int(row["value"])


class _RuntimeTime:
    def __init__(self, *, wait_jumps: list[float] | None = None) -> None:
        self.value = 0.0
        self.clock = _MutableClock(datetime(2026, 8, 11, 12, tzinfo=UTC))
        self.waits: list[float] = []
        self.wait_jumps = list(wait_jumps or ())

    def monotonic(self) -> float:
        return self.value

    def wait(self, event: threading.Event, timeout: float) -> bool:
        self.waits.append(timeout)
        advance = self.wait_jumps.pop(0) if self.wait_jumps else timeout
        self.value += advance
        self.clock.advance(timedelta(seconds=advance))
        return event.is_set()


class _CollisionProvider:
    poll_interval_seconds = 30.0
    freshness_seconds = 60.0

    def __init__(
        self,
        plugin_id: str,
        target_id: str,
        clock: _MutableClock,
        entity_ids: tuple[str, ...],
    ) -> None:
        self.id = target_id + ":provider"
        self.plugin_id = plugin_id
        self.target_id = target_id
        self.clock = clock
        self.entity_ids = entity_ids
        self.revision = 0

    def observe(self) -> TargetObservationV2:
        self.revision += 1
        observed_at = self.clock().isoformat()
        entities = tuple(
            EntityV1(
                id=entity_id,
                target_id=self.target_id,
                entity_type="fixture.entity",
                source=self.plugin_id,
            )
            for entity_id in self.entity_ids
        )
        observations = tuple(
            ObservationV1(
                id=f"{self.target_id}:{entity.id}:r{self.revision}",
                entity_id=entity.id,
                property="fixture.value",
                value=self.revision,
                source=self.plugin_id,
                observed_at=observed_at,
                evidence_grade=EvidenceGrade.OBSERVED,
                coverage="complete",
            )
            for entity in entities
        )
        return TargetObservationV2(
            target_id=self.target_id,
            revision=self.revision,
            observed_at=observed_at,
            entities=entities,
            relations=(),
            observations=observations,
            coverage={"fixture.value": "complete"},
            source=self.plugin_id,
        )

    def subscribe(self, wake):
        del wake
        return None


if __name__ == "__main__":
    unittest.main()
