from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from engine_homey.brains import HomeOpsExecutiveBrain
from engine_homey.charter import HomeCharterCompiler
from engine_homey.plugin import create_plugin
from engine_homey.store import HomeOpsStore
from fakes import FakeEventSource, MemoryHomeyTransport, fixture_config, fixture_house

from engine.catalog import Catalog
from engine.heart import Heart
from engine.models import Goal, GoalMode
from engine.runtime import LiveEngine
from engine.store import EngineStore

CHARTER = """
Beheer het huis comfortabel, rustig en energiezuinig. Verlicht gebruikte zones
wanneer het werkelijk donker is. Houd gebruikte zones tussen 60 en 120 lux en
onder 20 W per zone. Buiten moet een pad bij recente beweging zichtbaar zijn,
maar 's nachts niet onnodig fel. Gebruik passieve koeling voor actieve koeling.
"""


class ClosedLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-homey-loop-")
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _system(self, *, zone_count: int = 3):
        config = fixture_config(self.base, zone_count=zone_count)
        zones, devices = fixture_house(zone_count)
        transport = MemoryHomeyTransport(zones, devices)
        event_source = FakeEventSource()
        plugin_store = HomeOpsStore(config.plugin_database)
        charter = HomeCharterCompiler().compile(CHARTER, devices=config.devices)
        plugin_store.save_charter(charter, CHARTER)
        plugin = create_plugin(
            config,
            plugin_store,
            transport=transport,
            event_source=event_source,
        )
        catalog = Catalog()
        catalog.register(plugin)
        engine_store = EngineStore(config.engine_database)
        brain = HomeOpsExecutiveBrain()
        heart = Heart(
            engine_store,
            brain,
            catalog,
            require_specialist_first=True,
        )
        goal = Goal(
            id="homeops-maintain",
            target_id="home",
            instruction="Maintain the active typed HomeCharterV1",
            success_spec={"charter": "active"},
            priority=100,
            max_cycles=32,
            mode=GoalMode.MAINTAIN,
        )
        heart.register_goal(goal)
        return (
            config,
            transport,
            event_source,
            plugin_store,
            engine_store,
            brain,
            heart,
            goal,
            plugin.targets[0],
        )

    def test_three_zone_house_closes_loop_and_stable_monitoring_has_zero_brain_calls(
        self,
    ) -> None:
        (
            config,
            transport,
            event_source,
            plugin_store,
            engine_store,
            brain,
            heart,
            goal,
            target,
        ) = self._system(zone_count=3)
        del config, event_source, target
        try:
            result = heart.run(goal.id)
            self.assertEqual("monitoring", result.goal.status)
            for index in range(1, 4):
                light = transport.devices[f"light-{index}"]["capabilitiesObj"]
                sensor = transport.devices[f"sensor-{index}"]["capabilitiesObj"]
                self.assertTrue(light["onoff"]["value"])
                self.assertGreaterEqual(sensor["measure_luminance"]["value"], 60.0)
                self.assertLessEqual(sensor["measure_luminance"]["value"], 120.0)
                self.assertLessEqual(light["measure_power"]["value"], 20.0)

            calls_at_stable = brain.calls
            runtime = LiveEngine(heart, poll_interval=0.01)
            for _ in range(5):
                pass_result = runtime.run_once()
                self.assertEqual(0, pass_result.failures)
            self.assertEqual(calls_at_stable, brain.calls)

            events = engine_store.all_events(goal.id)
            invocations = [item for item in events if item.kind == "invocation"]
            requested_ids = {
                item.payload["id"]
                for item in invocations
                if item.payload["state"] == "requested"
            }
            terminal_ids = {
                item.payload["id"]
                for item in invocations
                if item.payload["state"] != "requested"
            }
            tool_results = [item for item in events if item.kind == "tool_result"]
            self.assertEqual(requested_ids, terminal_ids)
            self.assertEqual(
                requested_ids, {item.payload["invocation_id"] for item in tool_results}
            )
            self.assertTrue(
                all(item.payload["post_revision"] is not None for item in tool_results)
            )
            self.assertTrue(
                all(
                    item.payload["result"]["output"]["verified"]
                    for item in tool_results
                )
            )
            self.assertEqual((), plugin_store.preferences())
        finally:
            engine_store.close()
            plugin_store.close()

    def test_duplicate_event_is_one_wake_and_missed_event_is_repaired_by_polling(
        self,
    ) -> None:
        (
            config,
            transport,
            event_source,
            plugin_store,
            engine_store,
            brain,
            heart,
            goal,
            target,
        ) = self._system(zone_count=1)
        del config, brain
        unsubscribe = None
        try:
            heart.run(goal.id)
            charter_version = plugin_store.active_charter()["version_id"]
            runtime = LiveEngine(heart, poll_interval=60.0)
            unsubscribe = target.subscribe(runtime.wake)
            transport.external_set("light-1", "onoff", False)
            event_source.emit(duplicates=2)
            self.assertTrue(runtime.wake_pending)
            self._until_monitoring(runtime, engine_store, goal.id)
            self.assertTrue(
                transport.devices["light-1"]["capabilitiesObj"]["onoff"]["value"]
            )

            # No event is emitted for the second external drift. The ordinary
            # polling pass still performs a fresh observation and repairs it.
            transport.external_set("light-1", "onoff", False)
            self._until_monitoring(runtime, engine_store, goal.id)
            self.assertTrue(
                transport.devices["light-1"]["capabilitiesObj"]["onoff"]["value"]
            )
            kinds = [item.kind for item in engine_store.all_events(goal.id)]
            self.assertGreaterEqual(kinds.count("goal_drifted"), 2)
            inferred = [
                item
                for item in plugin_store.preferences()
                if item["source"] == "unattributed_control_change_detected"
            ]
            self.assertGreaterEqual(len(inferred), 2)
            self.assertTrue(all(item["grade"] == "INFERRED" for item in inferred))
            self.assertEqual(
                charter_version, plugin_store.active_charter()["version_id"]
            )
        finally:
            if unsubscribe is not None:
                unsubscribe()
            engine_store.close()
            plugin_store.close()

    def test_lost_ack_is_unknown_and_never_blindly_retried(self) -> None:
        (
            config,
            transport,
            event_source,
            plugin_store,
            engine_store,
            brain,
            heart,
            goal,
            target,
        ) = self._system(zone_count=1)
        del config, event_source, brain, target
        transport.raise_on_write.add(("light-1", "dim"))
        try:
            result = heart.run(goal.id, step_limit=2)
            self.assertEqual("active", result.goal.status)
            terminal = [
                item
                for item in engine_store.all_events(goal.id)
                if item.kind == "invocation" and item.payload["state"] != "requested"
            ]
            self.assertEqual(1, len(terminal))
            self.assertEqual("unknown", terminal[0].payload["state"])
            self.assertEqual(1, len(transport.writes))
        finally:
            engine_store.close()
            plugin_store.close()

    def test_ack_and_command_match_without_lux_change_never_satisfy_charter(
        self,
    ) -> None:
        system = self._system(zone_count=1)
        transport = system[1]
        plugin_store = system[3]
        engine_store = system[4]
        heart = system[6]
        goal = system[7]
        transport.freeze_lux = True
        try:
            result = heart.run(goal.id, step_limit=2)
            self.assertEqual("active", result.goal.status)
            self.assertEqual(
                5.0,
                transport.devices["sensor-1"]["capabilitiesObj"]["measure_luminance"][
                    "value"
                ],
            )
            kinds = [item.kind for item in engine_store.all_events(goal.id)]
            self.assertNotIn("goal_monitoring", kinds)
            self.assertFalse(system[8].goal_satisfied(goal, result.final_snapshot))
        finally:
            engine_store.close()
            plugin_store.close()

    def test_five_simulated_runs_reach_lux_band_within_power_budget(self) -> None:
        # This protects deterministic controller behavior only. It does not
        # replace the separately documented five-run physical acceptance gate.
        for run_index in range(5):
            with self.subTest(run=run_index):
                run_base = self.base / f"run-{run_index}"
                run_base.mkdir()
                original_base = self.base
                self.base = run_base
                try:
                    system = self._system(zone_count=1)
                    transport = system[1]
                    plugin_store = system[3]
                    engine_store = system[4]
                    heart = system[6]
                    goal = system[7]
                    transport.devices["sensor-1"]["capabilitiesObj"][
                        "measure_luminance"
                    ]["value"] = float(run_index)
                    result = heart.run(goal.id)
                    self.assertEqual("monitoring", result.goal.status)
                    lux = transport.devices["sensor-1"]["capabilitiesObj"][
                        "measure_luminance"
                    ]["value"]
                    watts = transport.devices["light-1"]["capabilitiesObj"][
                        "measure_power"
                    ]["value"]
                    self.assertTrue(60.0 <= lux <= 120.0)
                    self.assertLessEqual(watts, 20.0)
                    engine_store.close()
                    plugin_store.close()
                finally:
                    self.base = original_base

    @staticmethod
    def _until_monitoring(
        runtime: LiveEngine, store: EngineStore, goal_id: str, limit: int = 20
    ) -> None:
        for _ in range(limit):
            runtime.run_once()
            if store.get_goal(goal_id).status == "monitoring":
                return
        raise AssertionError("house did not return to monitoring")


if __name__ == "__main__":
    unittest.main()
