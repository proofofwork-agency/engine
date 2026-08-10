from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from engine.catalog import Catalog, EnginePlugin
from engine.heart import Heart
from engine.models import (
    BrainDecision,
    BrainManifest,
    CapabilitySpec,
    DecisionKind,
    Goal,
    GoalMode,
    PluginManifest,
    TargetManifest,
    ToolCall,
    ToolResult,
    WorldSnapshot,
)
from engine.runtime import LiveEngine
from engine.store import EngineStore


class LiveLevelTarget:
    capability_id = "engine.live-test.set-level/v1"

    def __init__(self, target_id: str, level: int = 21) -> None:
        self.manifest = TargetManifest(
            id=target_id,
            description="Event-capable level controller fixture",
            plugin_id="engine.live-test",
        )
        self._level = level
        self._telemetry = 0
        self._revision = 0
        self._callbacks: list[object] = []
        self._lock = threading.Lock()
        self.satisfied_seen = threading.Event()
        self.repaired = threading.Event()
        self.oracle_available = True

    def capabilities(self) -> tuple[CapabilitySpec, ...]:
        return (
            CapabilitySpec(
                id=self.capability_id,
                local_name="set-level",
                description="Set the observed level",
                input_schema={
                    "type": "object",
                    "properties": {"level": {"type": "integer"}},
                    "required": ["level"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {"level": {"type": "integer"}},
                    "required": ["level"],
                    "additionalProperties": False,
                },
                idempotent=True,
            ),
        )

    def observe(self) -> WorldSnapshot:
        with self._lock:
            level = self._level
            telemetry = self._telemetry
            revision = self._revision
        return WorldSnapshot(
            self.manifest.id,
            revision,
            {"level": level, "telemetry": telemetry},
            datetime.now(UTC).isoformat(),
        )

    def execute(self, call: ToolCall) -> ToolResult:
        if call.capability_id != self.capability_id:
            return ToolResult(False, False, error="unsupported capability")
        changed = self._set_level(int(call.arguments["level"]))
        self.repaired.set()
        return ToolResult(True, changed, output={"level": self.level})

    def goal_satisfied(self, goal: Goal, snapshot: WorldSnapshot) -> bool:
        if not self.oracle_available:
            raise RuntimeError("oracle offline")
        satisfied = snapshot.state["level"] == goal.success_spec["level"]
        if satisfied:
            self.satisfied_seen.set()
        return satisfied

    @property
    def level(self) -> int:
        with self._lock:
            return self._level

    def external_set(self, level: int) -> None:
        self._set_level(level)

    def external_telemetry(self) -> None:
        with self._lock:
            self._telemetry += 1
            self._revision += 1
            callbacks = tuple(self._callbacks)
        for callback in callbacks:
            callback({"target_id": self.manifest.id, "kind": "telemetry"})

    def goal_relevant_change(
        self,
        goal: Goal,
        previous: WorldSnapshot,
        current: WorldSnapshot,
    ) -> bool:
        return previous.state["level"] != current.state["level"]

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._callbacks)

    def subscribe(self, callback):
        with self._lock:
            self._callbacks.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._callbacks:
                    self._callbacks.remove(callback)

        return unsubscribe

    def _set_level(self, level: int) -> bool:
        with self._lock:
            changed = level != self._level
            if changed:
                self._level = level
                self._revision += 1
            callbacks = tuple(self._callbacks)
        if changed:
            for callback in callbacks:
                callback({"target_id": self.manifest.id})
        return changed


class LevelBrain:
    manifest = BrainManifest(
        "level-brain",
        "Direct executive fixture for maintained level goals",
        id="engine.test.level-brain/v1",
    )

    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()

    def decide(self, context):
        with self._lock:
            self.calls += 1
        return BrainDecision(
            DecisionKind.USE_TOOL,
            name=LiveLevelTarget.capability_id,
            arguments={"level": context.goal.success_spec["level"]},
            rationale="Restore the maintained level",
        )


def live_catalog(target: LiveLevelTarget) -> Catalog:
    catalog = Catalog()
    catalog.register(
        EnginePlugin(
            PluginManifest("engine.live-test", "Live target test plugin"),
            targets=(target,),
        )
    )
    return catalog


class LiveRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-live-tests-")
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_maintained_goal_sleeps_when_stable_and_repairs_observed_drift(self) -> None:
        store = EngineStore(self.base / "engine.db")
        target = LiveLevelTarget("room")
        brain = LevelBrain()
        heart = Heart(store, brain, live_catalog(target))
        goal = Goal(
            id="keep-room-level",
            target_id="room",
            instruction="Keep the room level at 21",
            success_spec={"level": 21},
            mode=GoalMode.MAINTAIN,
        )
        heart.register_goal(goal)
        runtime = LiveEngine(heart, poll_interval=0.01)

        runtime.run_once()
        self.assertEqual("monitoring", store.get_goal(goal.id).status)
        for _ in range(5):
            runtime.run_once()
        self.assertEqual(0, brain.calls)

        target.external_set(7)
        runtime.run_once()

        self.assertEqual(21, target.level)
        self.assertEqual("monitoring", store.get_goal(goal.id).status)
        self.assertEqual(1, brain.calls)
        for _ in range(5):
            runtime.run_once()
        self.assertEqual(1, brain.calls)
        kinds = [event.kind for event in store.all_events(goal.id)]
        self.assertIn("goal_drifted", kinds)
        self.assertIn("goal_monitoring", kinds)
        self.assertNotIn("goal_completed", kinds)
        store.close()

    def test_live_loop_wakes_from_target_event_without_human_step(self) -> None:
        target = LiveLevelTarget("room-live")
        brain = LevelBrain()
        ready = threading.Event()
        holder: dict[str, object] = {}

        def serve() -> None:
            store = EngineStore(self.base / "live.db")
            heart = Heart(store, brain, live_catalog(target))
            goal = Goal(
                id="live-room",
                target_id="room-live",
                instruction="Keep the room level at 21",
                success_spec={"level": 21},
                mode=GoalMode.MAINTAIN,
            )
            heart.register_goal(goal)
            runtime = LiveEngine(heart, poll_interval=5.0)
            holder["runtime"] = runtime
            ready.set()
            runtime.run_forever()
            holder["status"] = store.get_goal(goal.id).status
            holder["event_kinds"] = [
                event.kind for event in store.all_events(goal.id)
            ]
            holder["system_kinds"] = [
                event["kind"] for event in store.system_events()
            ]
            store.close()

        thread = threading.Thread(target=serve, name="engine-live-test")
        thread.start()
        self.assertTrue(ready.wait(2.0))
        self.assertTrue(target.satisfied_seen.wait(2.0))
        self.assertEqual(0, brain.calls)

        target.external_set(3)
        self.assertTrue(target.repaired.wait(2.0))
        runtime = holder["runtime"]
        assert isinstance(runtime, LiveEngine)
        runtime.stop()
        thread.join(2.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(21, target.level)
        self.assertEqual(1, brain.calls)
        self.assertEqual("monitoring", holder["status"])
        self.assertIn("goal_drifted", holder["event_kinds"])
        self.assertEqual(
            ["catalog_changed", "live_heart_started", "live_heart_stopped"],
            holder["system_kinds"],
        )

    def test_wait_is_quiet_until_observation_changes(self) -> None:
        class WaitBrain:
            manifest = BrainManifest("wait", "Wait for external state")

            def __init__(self) -> None:
                self.calls = 0

            def decide(self, context):
                self.calls += 1
                return BrainDecision(DecisionKind.WAIT, rationale="Await event")

        store = EngineStore(self.base / "wait.db")
        target = LiveLevelTarget("wait-room", level=0)
        brain = WaitBrain()
        heart = Heart(store, brain, live_catalog(target))
        goal = Goal(
            id="wait-for-room",
            target_id="wait-room",
            instruction="Wait until the room reaches 21",
            success_spec={"level": 21},
        )
        heart.register_goal(goal)

        first = heart.run(goal.id)
        second = heart.run(goal.id)

        self.assertEqual("waiting", first.goal.status)
        self.assertEqual("waiting", second.goal.status)
        self.assertEqual(1, brain.calls)
        self.assertEqual(1, first.goal.cycle)

        target.external_set(21)
        final = heart.run(goal.id)
        self.assertEqual("completed", final.goal.status)
        self.assertEqual(1, brain.calls)
        store.close()

    def test_wait_ignores_goal_irrelevant_telemetry(self) -> None:
        class WaitBrain:
            manifest = BrainManifest("quiet-wait", "Wait through telemetry")

            def __init__(self) -> None:
                self.calls = 0

            def decide(self, context):
                self.calls += 1
                return BrainDecision(DecisionKind.WAIT, rationale="Await level")

        store = EngineStore(self.base / "telemetry.db")
        target = LiveLevelTarget("telemetry-room", level=0)
        brain = WaitBrain()
        heart = Heart(store, brain, live_catalog(target))
        goal = Goal(
            id="quiet-wait",
            target_id="telemetry-room",
            instruction="Wait until level 21",
            success_spec={"level": 21},
        )
        heart.register_goal(goal)
        heart.run(goal.id)

        for _ in range(6):
            target.external_telemetry()
            heart.run(goal.id)

        self.assertEqual(1, brain.calls)
        self.assertEqual("waiting", store.get_goal(goal.id).status)
        self.assertEqual(6, store.latest_snapshot(goal.id).revision)
        self.assertEqual(
            6,
            sum(
                event.kind == "goal_change_ignored"
                for event in store.all_events(goal.id)
            ),
        )
        store.close()

    def test_oracle_unknown_suspends_action_and_recovers_on_same_snapshot(self) -> None:
        store = EngineStore(self.base / "unknown.db")
        target = LiveLevelTarget("unknown-room", level=0)
        target.oracle_available = False
        brain = LevelBrain()
        heart = Heart(store, brain, live_catalog(target))
        goal = Goal(
            id="unknown-goal",
            target_id="unknown-room",
            instruction="Set level to 21",
            success_spec={"level": 21},
        )
        heart.register_goal(goal)

        unknown = heart.run(goal.id)

        self.assertEqual("uncertain", unknown.goal.status)
        self.assertEqual(0, brain.calls)
        self.assertEqual(0, target.level)
        target.oracle_available = True

        recovered = heart.run(goal.id)

        self.assertEqual("completed", recovered.goal.status)
        self.assertEqual(1, brain.calls)
        self.assertEqual(21, target.level)
        self.assertIn(
            "goal_uncertain",
            {event.kind for event in store.all_events(goal.id)},
        )
        store.close()

    def test_changed_wait_snapshot_survives_unknown_until_oracle_recovers(self) -> None:
        class WaitThenRepairBrain(LevelBrain):
            def decide(self, context):
                with self._lock:
                    self.calls += 1
                    calls = self.calls
                if calls == 1:
                    return BrainDecision(DecisionKind.WAIT, rationale="Await change")
                return BrainDecision(
                    DecisionKind.USE_TOOL,
                    name=LiveLevelTarget.capability_id,
                    arguments={"level": 21},
                    rationale="Repair after relevant change",
                )

        store = EngineStore(self.base / "wait-unknown.db")
        target = LiveLevelTarget("wait-unknown-room", level=0)
        brain = WaitThenRepairBrain()
        heart = Heart(store, brain, live_catalog(target))
        goal = Goal(
            id="wait-unknown",
            target_id="wait-unknown-room",
            instruction="Reach level 21 after change",
            success_spec={"level": 21},
        )
        heart.register_goal(goal)
        self.assertEqual("waiting", heart.run(goal.id).goal.status)

        target.external_set(7)
        target.oracle_available = False
        self.assertEqual("uncertain", heart.run(goal.id).goal.status)
        self.assertEqual(1, brain.calls)

        target.oracle_available = True
        recovered = heart.run(goal.id)
        self.assertEqual("completed", recovered.goal.status)
        self.assertEqual(2, brain.calls)
        self.assertEqual(21, target.level)
        store.close()

    def test_provider_failure_has_durable_backoff_and_opens_circuit(self) -> None:
        class FailingBrain:
            manifest = BrainManifest("offline", "Unavailable provider")

            def __init__(self) -> None:
                self.calls = 0

            def decide(self, context):
                self.calls += 1
                raise RuntimeError("provider offline")

        store = EngineStore(self.base / "backoff.db")
        target = LiveLevelTarget("backoff-room", level=0)
        brain = FailingBrain()
        heart = Heart(store, brain, live_catalog(target))
        goal = Goal(
            id="backoff",
            target_id="backoff-room",
            instruction="Set level to 21",
            success_spec={"level": 21},
        )
        heart.register_goal(goal)
        runtime = LiveEngine(
            heart,
            poll_interval=0.01,
            failure_backoff_initial=10.0,
            failure_backoff_max=10.0,
            failure_threshold=2,
        )

        runtime.run_once()
        for _ in range(5):
            runtime.run_once()
        self.assertEqual(1, brain.calls)
        retry = store.load_memory(goal.id)[LiveEngine.retry_memory_key]
        self.assertEqual(1, retry["attempts"])

        retry["retry_at_epoch"] = 0.0
        store.set_memory(goal.id, LiveEngine.retry_memory_key, retry)
        runtime.run_once()
        for _ in range(5):
            runtime.run_once()

        self.assertEqual(2, brain.calls)
        self.assertEqual("degraded", store.get_goal(goal.id).status)
        kinds = [event.kind for event in store.all_events(goal.id)]
        self.assertEqual(2, kinds.count("runtime_goal_error"))
        self.assertIn("runtime_circuit_open", kinds)
        store.close()

    def test_uncertain_pass_does_not_falsely_clear_provider_failure(self) -> None:
        class FailingBrain:
            manifest = BrainManifest("still-offline", "Unavailable provider")

            def __init__(self) -> None:
                self.calls = 0

            def decide(self, context):
                self.calls += 1
                raise RuntimeError("provider offline")

        store = EngineStore(self.base / "uncertain-backoff.db")
        target = LiveLevelTarget("uncertain-backoff-room", level=0)
        brain = FailingBrain()
        heart = Heart(store, brain, live_catalog(target))
        goal = Goal(
            id="uncertain-backoff",
            target_id="uncertain-backoff-room",
            instruction="Set level to 21",
            success_spec={"level": 21},
        )
        heart.register_goal(goal)
        runtime = LiveEngine(
            heart,
            failure_backoff_initial=10.0,
            failure_backoff_max=10.0,
            failure_threshold=3,
        )
        runtime.run_once()
        retry = store.load_memory(goal.id)[LiveEngine.retry_memory_key]
        retry["retry_at_epoch"] = 0.0
        store.set_memory(goal.id, LiveEngine.retry_memory_key, retry)

        target.oracle_available = False
        runtime.run_once()

        preserved = store.load_memory(goal.id)[LiveEngine.retry_memory_key]
        self.assertEqual(1, preserved["attempts"])
        self.assertEqual("uncertain", store.get_goal(goal.id).status)
        self.assertNotIn(
            "runtime_goal_recovered",
            {event.kind for event in store.all_events(goal.id)},
        )

        target.oracle_available = True
        preserved["retry_at_epoch"] = 0.0
        store.set_memory(goal.id, LiveEngine.retry_memory_key, preserved)
        runtime.run_once()

        retried = store.load_memory(goal.id)[LiveEngine.retry_memory_key]
        self.assertEqual(2, retried["attempts"])
        self.assertEqual(2, brain.calls)
        store.close()

    def test_background_launch_uses_thread_local_store_and_cleans_up(self) -> None:
        store = EngineStore(self.base / "background.db")
        target = LiveLevelTarget("background-room")
        brain = LevelBrain()
        heart = Heart(store, brain, live_catalog(target))
        goal = Goal(
            id="background-live",
            target_id="background-room",
            instruction="Keep level 21",
            success_spec={"level": 21},
            mode=GoalMode.MAINTAIN,
        )
        heart.register_goal(goal)
        runtime = LiveEngine(heart, poll_interval=5.0)
        errors: list[BaseException] = []

        def serve() -> None:
            try:
                runtime.run_forever()
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=serve, name="background-live-heart")
        thread.start()
        self.assertTrue(target.satisfied_seen.wait(2.0))
        target.external_set(4)
        self.assertTrue(target.repaired.wait(2.0))
        runtime.stop()
        thread.join(2.0)

        self.assertEqual([], errors)
        self.assertFalse(thread.is_alive())
        self.assertFalse(runtime.running)
        self.assertEqual(0, target.subscriber_count)
        self.assertEqual("monitoring", store.get_goal(goal.id).status)
        self.assertEqual(21, target.level)
        store.close()

    def test_startup_failure_resets_running_and_unsubscribes(self) -> None:
        store = EngineStore(self.base / "startup-failure.db")
        target = LiveLevelTarget("startup-room")
        heart = Heart(store, LevelBrain(), live_catalog(target))
        goal = Goal(
            id="startup-failure",
            target_id="startup-room",
            instruction="Keep level 21",
            success_spec={"level": 21},
            mode=GoalMode.MAINTAIN,
        )
        heart.register_goal(goal)
        runtime = LiveEngine(heart)

        with patch.object(
            store, "append_system_event", side_effect=RuntimeError("store offline")
        ):
            with self.assertRaisesRegex(RuntimeError, "store offline"):
                runtime.run_forever()

        self.assertFalse(runtime.running)
        self.assertEqual(0, target.subscriber_count)
        store.close()

    def test_maintained_goal_lifecycle_survives_store_restart(self) -> None:
        path = self.base / "maintain-restart.db"
        target = LiveLevelTarget("restart-room")
        first_store = EngineStore(path)
        first_brain = LevelBrain()
        first_heart = Heart(first_store, first_brain, live_catalog(target))
        goal = Goal(
            id="maintain-restart",
            target_id="restart-room",
            instruction="Keep level 21",
            success_spec={"level": 21},
            mode=GoalMode.MAINTAIN,
        )
        first_heart.register_goal(goal)
        self.assertEqual("monitoring", first_heart.run(goal.id).goal.status)
        first_store.close()

        target.external_set(8)
        restarted_store = EngineStore(path)
        restarted_brain = LevelBrain()
        restarted_heart = Heart(
            restarted_store, restarted_brain, live_catalog(target)
        )
        repaired = restarted_heart.run(goal.id)

        self.assertEqual("monitoring", repaired.goal.status)
        self.assertEqual(21, target.level)
        self.assertEqual(1, restarted_brain.calls)
        restarted_store.close()

    def test_existing_goal_store_migrates_to_explicit_lifecycle_defaults(self) -> None:
        path = self.base / "old.db"
        connection = sqlite3.connect(path)
        connection.execute(
            """
            CREATE TABLE goals (
                id TEXT PRIMARY KEY,
                target_id TEXT NOT NULL,
                instruction TEXT NOT NULL,
                success_spec_json TEXT NOT NULL,
                priority INTEGER NOT NULL,
                max_cycles INTEGER NOT NULL,
                status TEXT NOT NULL,
                cycle INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO goals (
                id, target_id, instruction, success_spec_json,
                priority, max_cycles, status, cycle
            ) VALUES ('old', 'target', 'old goal', '{}', 0, 80, 'active', 4)
            """
        )
        connection.commit()
        connection.close()

        store = EngineStore(path)
        goal = store.get_goal("old")
        self.assertEqual(GoalMode.ACHIEVE, goal.mode)
        self.assertEqual(0, goal.intervention_cycle)
        store.close()


if __name__ == "__main__":
    unittest.main()
