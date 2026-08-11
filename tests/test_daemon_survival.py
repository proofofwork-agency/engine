from __future__ import annotations

import plistlib
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

    def test_run_forever_records_runtime_started_and_stopped_as_first_and_last(
        self,
    ) -> None:
        _, provider, store, heart = self._system()
        provider.poll_interval_seconds = 0.0

        passes = heart.run_forever(threading.Event(), max_passes=2)

        self.assertEqual(2, passes)
        started = self._events(store, "runtime_started")
        stopped = self._events(store, "runtime_stopped")
        self.assertEqual(1, len(started))
        self.assertEqual(1, len(stopped))
        self.assertEqual(1, started[0]["payload"]["targets"])
        self.assertEqual(2, stopped[0]["payload"]["passes"])
        self.assertEqual("max_passes", stopped[0]["payload"]["reason"])
        ordered = store.events()
        self.assertEqual("runtime_started", ordered[0]["kind"])
        self.assertEqual("runtime_stopped", ordered[-1]["kind"])
        self.assertEqual((), self._events(store, "runtime_lease_lost"))

    def test_preset_stop_event_records_stop_requested_reason(self) -> None:
        _, provider, store, heart = self._system()
        provider.poll_interval_seconds = 0.0
        stop = threading.Event()
        stop.set()

        passes = heart.run_forever(stop, max_passes=2)

        self.assertEqual(0, passes)
        stopped = self._events(store, "runtime_stopped")
        self.assertEqual(1, len(stopped))
        self.assertEqual("stop_requested", stopped[0]["payload"]["reason"])

    def test_lease_loss_is_recorded_durably_at_loop_exit(self) -> None:
        _, provider, store, heart = self._system()
        provider.poll_interval_seconds = 0.0

        passes = heart.run_forever(
            threading.Event(), max_passes=1, lease_lost=lambda: True
        )

        self.assertEqual(1, passes)
        lost = self._events(store, "runtime_lease_lost")
        stopped = self._events(store, "runtime_stopped")
        self.assertEqual(1, len(lost))
        self.assertEqual(1, lost[0]["payload"]["passes"])
        self.assertEqual(1, len(stopped))
        self.assertEqual("lease_lost", stopped[0]["payload"]["reason"])

    def test_escaping_loop_fault_is_recorded_as_crashed_before_reraising(
        self,
    ) -> None:
        _, provider, store, heart = self._system()
        provider.poll_interval_seconds = 30.0

        with (
            patch.object(
                heart,
                "_waiter",
                side_effect=RuntimeError("fatal loop fixture"),
            ),
            self.assertRaisesRegex(RuntimeError, "fatal loop fixture"),
        ):
            heart.run_forever(
                threading.Event(), max_passes=2, lease_lost=lambda: True
            )

        stopped = self._events(store, "runtime_stopped")
        self.assertEqual(1, len(stopped))
        self.assertEqual(1, stopped[0]["payload"]["passes"])
        self.assertEqual("crashed", stopped[0]["payload"]["reason"])
        self.assertEqual(1, len(self._events(store, "runtime_lease_lost")))

    def test_durable_wake_read_outages_degrade_to_polling_once_per_outage(
        self,
    ) -> None:
        _, provider, store, heart = self._system()
        provider.poll_interval_seconds = 0.0
        wake_reads = (
            OSError("durable wake unavailable"),
            OSError("durable wake unavailable"),
            None,
            OSError("durable wake unavailable again"),
        )

        with patch.object(store, "next_wake_at", side_effect=wake_reads):
            passes = heart.run_forever(threading.Event(), max_passes=4)

        self.assertEqual(4, passes)
        self.assertEqual(4, self._row_count(store, "world_snapshots_v2"))
        failures = self._events(store, "durable_wake_failed")
        self.assertEqual(2, len(failures))
        self.assertEqual(
            ["durable wake unavailable", "durable wake unavailable again"],
            [item["payload"]["message"] for item in failures],
        )
        self.assertTrue(
            all(item["payload"]["exception_type"] == "OSError" for item in failures)
        )
        self.assertEqual((), self._events(store, "cycle_failed"))

    def test_daily_heartbeat_fires_once_per_utc_day_with_counts_only_payload(
        self,
    ) -> None:
        clock = _MutableClock(datetime(2026, 8, 11, 12, tzinfo=UTC))
        provider = _DayJumpProvider(
            "plugin.dayjump", "target:dayjump", clock, ("entity:day",)
        )
        provider.poll_interval_seconds = 0.0
        registry = PluginRegistryV2()
        registry._targets = {provider.target_id: provider}
        store = WorldStore(self.base / "heartbeat.sqlite3")
        self.addCleanup(store.close)
        heart = WorldHeartV2(
            store, registry, DeterministicExecutiveBrainV2(), clock=clock
        )

        passes = heart.run_forever(threading.Event(), max_passes=3)

        self.assertEqual(3, passes)
        beats = self._events(store, "runtime_heartbeat")
        self.assertEqual(3, len(beats))
        self.assertEqual(
            ["2026-08-11", "2026-08-12", "2026-08-13"],
            [item["payload"]["at"][:10] for item in beats],
        )
        self.assertEqual(
            [0, 1, 2], [item["payload"]["cycles"] for item in beats]
        )
        for item in beats:
            payload = item["payload"]
            self.assertEqual(
                {
                    "at",
                    "cycles",
                    "rows_written",
                    "rows_confirmed",
                    "store_bytes",
                    "open_attempts",
                },
                set(payload),
            )
            for key in (
                "cycles",
                "rows_written",
                "rows_confirmed",
                "store_bytes",
                "open_attempts",
            ):
                self.assertIsInstance(payload[key], int)
                self.assertGreaterEqual(payload[key], 0)
        self.assertGreater(beats[0]["payload"]["store_bytes"], 0)
        self.assertEqual(0, beats[0]["payload"]["open_attempts"])
        self.assertEqual((), self._events(store, "heartbeat_failed"))

    def test_transient_heartbeat_write_failure_retries_within_the_same_day(
        self,
    ) -> None:
        _, provider, store, heart = self._system()
        provider.poll_interval_seconds = 0.0
        original_append = store.append_event
        heartbeat_attempts = 0

        def flaky_append(goal_id, kind, source, payload):
            nonlocal heartbeat_attempts
            if kind == "runtime_heartbeat":
                heartbeat_attempts += 1
                if heartbeat_attempts == 1:
                    raise OSError("transient heartbeat write")
            return original_append(goal_id, kind, source, payload)

        with patch.object(store, "append_event", side_effect=flaky_append):
            passes = heart.run_forever(threading.Event(), max_passes=2)

        self.assertEqual(2, passes)
        self.assertEqual(2, heartbeat_attempts)
        self.assertEqual(1, len(self._events(store, "runtime_heartbeat")))

    def test_heartbeat_payload_failure_isolated_once_and_retried(self) -> None:
        _, provider, store, heart = self._system()
        provider.poll_interval_seconds = 0.0
        original_payload = heart._runtime_heartbeat_payload
        payload_attempts = 0

        def flaky_payload(boundary, passes):
            nonlocal payload_attempts
            payload_attempts += 1
            if payload_attempts == 1:
                raise OSError("transient heartbeat read")
            return original_payload(boundary, passes)

        with patch.object(
            heart, "_runtime_heartbeat_payload", side_effect=flaky_payload
        ):
            passes = heart.run_forever(threading.Event(), max_passes=2)

        self.assertEqual(2, passes)
        self.assertEqual(2, payload_attempts)
        self.assertEqual(1, len(self._events(store, "heartbeat_failed")))
        self.assertEqual(1, len(self._events(store, "runtime_heartbeat")))
        self.assertEqual((), self._events(store, "runtime_heartbeat_failed"))

    def test_run_forever_flushes_stopped_event_before_releasing_its_caller(self) -> None:
        registry, provider, store, _ = self._system()
        provider.poll_interval_seconds = 0.0
        observer = _RecordingLifecycleObserver()
        heart = WorldHeartV2(
            store,
            registry,
            DeterministicExecutiveBrainV2(),
            clock=_MutableClock(datetime(2026, 8, 11, 12, tzinfo=UTC)),
            lifecycle_observers=(observer,),
        )

        heart.run_forever(threading.Event(), max_passes=1)

        self.assertEqual("runtime_stopped", observer.kinds[-1])
        self.assertEqual(1, observer.kinds.count("runtime_stopped"))
        self.assertEqual(
            store.latest_event_sequence(),
            store.lifecycle_cursor(observer.id),
        )

    def test_heartbeat_is_not_reemitted_by_restart_within_the_same_day(self) -> None:
        registry, provider, store, heart = self._system()
        provider.poll_interval_seconds = 0.0
        heart.run_forever(threading.Event(), max_passes=1)
        self.assertEqual(1, len(self._events(store, "runtime_heartbeat")))

        same_day = WorldHeartV2(
            store,
            registry,
            DeterministicExecutiveBrainV2(),
            clock=_MutableClock(datetime(2026, 8, 11, 18, tzinfo=UTC)),
        )
        same_day.run_forever(threading.Event(), max_passes=1)
        self.assertEqual(1, len(self._events(store, "runtime_heartbeat")))

        next_day = WorldHeartV2(
            store,
            registry,
            DeterministicExecutiveBrainV2(),
            clock=_MutableClock(datetime(2026, 8, 12, 0, 30, tzinfo=UTC)),
        )
        next_day.run_forever(threading.Event(), max_passes=1)
        beats = self._events(store, "runtime_heartbeat")
        self.assertEqual(2, len(beats))
        self.assertEqual("2026-08-12", beats[-1]["payload"]["at"][:10])

    def test_launchd_template_keeps_daemon_alive_without_secrets(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "launchd"
            / "com.proofofworks.engine.observe.plist"
        )
        data = plistlib.loads(path.read_bytes())
        self.assertTrue(data["KeepAlive"])
        self.assertTrue(data["RunAtLoad"])
        self.assertEqual(30, int(data["ThrottleInterval"]))
        self.assertEqual(["engine", "run"], data["ProgramArguments"][-2:])
        environment = data["EnvironmentVariables"]
        self.assertEqual("observe", environment["ENGINE_HOMEY_MODE"])
        self.assertEqual("token", environment["ENGINE_HOMEY_AUTH"])
        self.assertNotIn("ENGINE_HOMEY_ARMED", environment)
        self.assertIn("REPLACE", environment["ENGINE_HOMEY_TOKEN"])

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


class _DayJumpProvider(_CollisionProvider):
    """Advance the shared clock past a UTC-day boundary on every observe."""

    def observe(self) -> TargetObservationV2:
        observation = super().observe()
        self.clock.advance(timedelta(hours=25))
        return observation


class _RecordingLifecycleObserver:
    id = "test.daemon-lifecycle"
    plugin_id = "test.notifications"

    def __init__(self) -> None:
        self.kinds: list[str] = []

    def observe(self, events) -> None:
        self.kinds.extend(item.kind for item in events)


if __name__ == "__main__":
    unittest.main()
