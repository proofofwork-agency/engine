from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from importlib import metadata
from pathlib import Path
from unittest.mock import patch

from engine_homey.charter import HomeCharterCompiler
from engine_homey.plugin import create_plugin
from engine_homey.store import HomeOpsStore
from engine_homey.target import SET_LIGHT, HomeyTarget
from fakes import FakeEventSource, MemoryHomeyTransport, fixture_config, fixture_house

from engine.catalog import CapabilityValidationError, Catalog
from engine.models import Goal, ToolCall

CHARTER = """
Beheer het huis comfortabel, rustig en energiezuinig. Verlicht gebruikte zones
wanneer het werkelijk donker is. Houd gebruikte zones tussen 60 en 120 lux en
onder 20 W per zone. Gebruik passieve koeling voor actieve koeling.
"""


class TargetAndStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-homey-target-")
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _target(
        self,
        *,
        config=None,
        store=None,
        transport=None,
        events=None,
        clock=None,
    ) -> HomeyTarget:
        config = config or fixture_config(self.base)
        store = store or HomeOpsStore(config.plugin_database)
        zones, devices = fixture_house(3)
        transport = transport or MemoryHomeyTransport(zones, devices)
        return HomeyTarget(
            config,
            store,
            transport,
            event_source=events,
            clock=clock,
        )

    def test_whole_house_projection_is_typed_bounded_and_three_zone_generic(
        self,
    ) -> None:
        config = fixture_config(self.base)
        store = HomeOpsStore(config.plugin_database)
        charter = HomeCharterCompiler().compile(CHARTER, devices=config.devices)
        store.save_charter(charter, CHARTER)
        target = self._target(config=config, store=store)

        snapshot = target.observe()

        self.assertEqual("engine.homey.house-snapshot/v1", snapshot.state["schema"])
        self.assertEqual(3, len(snapshot.state["zones"]))
        self.assertEqual(6, len(snapshot.state["devices"]))
        lighting = [
            item
            for item in snapshot.state["obligations"]
            if item["domain"] == "lighting"
        ]
        self.assertEqual(
            {"zone_1", "zone_2", "zone_3"}, {item["zone"] for item in lighting}
        )
        self.assertTrue(all(item["status"] == "VIOLATED" for item in lighting))
        self.assertNotIn("driverId", str(snapshot.state))
        self.assertNotIn(config.token, str(snapshot.state))
        store.close()

    def test_aliases_and_revisions_are_stable_and_monotone_across_restart(self) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        devices["unbound-device"] = {
            "id": "unbound-device",
            "name": "Unbound Sensor",
            "zone": "zone-1",
            "class": "sensor",
            "available": True,
            "capabilities": [],
            "capabilitiesObj": {},
        }
        transport = MemoryHomeyTransport(zones, devices)
        first_store = HomeOpsStore(config.plugin_database)
        target = HomeyTarget(config, first_store, transport)
        first = target.observe()
        same = target.observe()
        aliases = [item["alias"] for item in first.state["devices"]]
        self.assertEqual(first.revision, same.revision)
        first_store.close()

        transport.external_set("light-1", "onoff", True)
        second_store = HomeOpsStore(config.plugin_database)
        restarted = HomeyTarget(config, second_store, transport).observe()
        self.assertGreater(restarted.revision, first.revision)
        self.assertEqual(
            aliases, [item["alias"] for item in restarted.state["devices"]]
        )
        history = second_store.snapshot_history()
        self.assertEqual(
            list(range(history[-1].revision + 1)), [item.revision for item in history]
        )
        second_store.close()

    def test_mutation_is_double_gated_allowlisted_and_observation_verified(
        self,
    ) -> None:
        zones, devices = fixture_house(1)
        transport = MemoryHomeyTransport(zones, devices)
        observe_config = fixture_config(
            self.base, mode="observe", armed=True, zone_count=1
        )
        store = HomeOpsStore(observe_config.plugin_database)
        observe_target = HomeyTarget(observe_config, store, transport)
        observe_target.observe()
        denied = observe_target.execute(
            ToolCall(SET_LIGHT, {"alias": "zone_1_main_light", "on": True})
        )
        self.assertFalse(denied.succeeded)
        self.assertEqual([], transport.writes)

        unarmed_config = replace(observe_config, mode="act", armed=False)
        unarmed_target = HomeyTarget(unarmed_config, store, transport)
        unarmed_target.observe()
        denied = unarmed_target.execute(
            ToolCall(SET_LIGHT, {"alias": "zone_1_main_light", "on": True})
        )
        self.assertFalse(denied.succeeded)
        self.assertEqual([], transport.writes)

        armed = HomeyTarget(replace(unarmed_config, armed=True), store, transport)
        armed.observe()
        result = armed.execute(
            ToolCall(
                SET_LIGHT,
                {"alias": "zone_1_main_light", "on": True, "brightness": 0.5},
            )
        )
        self.assertTrue(result.succeeded)
        self.assertTrue(result.changed)
        self.assertTrue(result.output["verified"])
        self.assertEqual(2, len(transport.writes))

        denied = armed.execute(
            ToolCall(SET_LIGHT, {"alias": "not_configured", "on": True})
        )
        self.assertFalse(denied.succeeded)
        self.assertEqual(2, len(transport.writes))
        store.close()

    def test_ack_without_observed_effect_is_not_success(self) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        transport = MemoryHomeyTransport(zones, devices)
        transport.ack_without_effect.add(("light-1", "onoff"))
        store = HomeOpsStore(config.plugin_database)
        target = HomeyTarget(config, store, transport)
        target.observe()

        result = target.execute(
            ToolCall(SET_LIGHT, {"alias": "zone_1_main_light", "on": True})
        )

        self.assertFalse(result.succeeded)
        self.assertFalse(result.changed)
        self.assertIn("ACK_WITHOUT_OBSERVED_EFFECT", result.error or "")
        store.close()

    def test_missing_setable_metadata_denies_mutation_as_unknown(self) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        devices["light-1"]["capabilitiesObj"]["onoff"].pop("setable")
        transport = MemoryHomeyTransport(zones, devices)
        store = HomeOpsStore(config.plugin_database)
        target = HomeyTarget(config, store, transport)
        target.observe()

        result = target.execute(
            ToolCall(SET_LIGHT, {"alias": "zone_1_main_light", "on": True})
        )

        self.assertFalse(result.succeeded)
        self.assertIn("not freshly observed as controllable", result.error or "")
        self.assertEqual([], transport.writes)
        store.close()

    def test_stale_observation_is_rejected_before_dispatch(self) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        transport = MemoryHomeyTransport(zones, devices)
        store = HomeOpsStore(config.plugin_database)
        target = HomeyTarget(config, store, transport)
        target.observe()
        target._last_observed_monotonic -= config.max_snapshot_age_seconds + 1

        result = target.execute(
            ToolCall(SET_LIGHT, {"alias": "zone_1_main_light", "on": True})
        )

        self.assertFalse(result.succeeded)
        self.assertIn("no fresh Homey observation", result.error or "")
        self.assertEqual([], transport.writes)
        store.close()

    def test_failed_observation_persistence_invalidates_dispatch_freshness(
        self,
    ) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        transport = MemoryHomeyTransport(zones, devices)
        store = HomeOpsStore(config.plugin_database)
        target = HomeyTarget(config, store, transport)
        target.observe()

        with (
            patch.object(
                store, "record_snapshot", side_effect=RuntimeError("fixture db failure")
            ),
            self.assertRaisesRegex(RuntimeError, "fixture db failure"),
        ):
            target.observe()
        result = target.execute(
            ToolCall(SET_LIGHT, {"alias": "zone_1_main_light", "on": True})
        )

        self.assertFalse(result.succeeded)
        self.assertIn("no fresh Homey observation", result.error or "")
        self.assertEqual([], transport.writes)
        store.close()

    def test_catalog_accepts_plugin_contract_and_event_payload_is_only_a_wake(
        self,
    ) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        devices["unbound-device"] = {
            "id": "unbound-device",
            "name": "Unbound Sensor",
            "zone": "zone-1",
            "class": "sensor",
            "available": True,
            "capabilities": [],
            "capabilitiesObj": {},
        }
        transport = MemoryHomeyTransport(zones, devices)
        events = FakeEventSource()
        store = HomeOpsStore(config.plugin_database)
        plugin = create_plugin(config, store, transport=transport, event_source=events)
        catalog = Catalog()
        catalog.register(plugin)
        wakes: list[object] = []
        unsubscribe = plugin.targets[0].subscribe(wakes.append)
        events.emit(duplicates=2)
        self.assertEqual(2, len(wakes))
        self.assertEqual(("light-1", "sensor-1", "unbound-device"), events.device_ids)
        unsubscribe()
        self.assertTrue(events.closed)
        store.close()

    def test_adapter_capability_schema_enforces_alias_ranges_and_units(self) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        store = HomeOpsStore(config.plugin_database)
        plugin = create_plugin(
            config, store, transport=MemoryHomeyTransport(zones, devices)
        )
        catalog = Catalog()
        catalog.register(plugin)
        catalog.validate_call(
            "home",
            ToolCall(
                SET_LIGHT,
                {"alias": "zone_1_main_light", "on": True, "brightness": 0.7},
            ),
        )
        with self.assertRaises(CapabilityValidationError):
            catalog.validate_call(
                "home",
                ToolCall(
                    SET_LIGHT,
                    {"alias": "zone_1_main_light", "brightness": 0.71},
                ),
            )
        snapshot = plugin.targets[0].observe()
        light = next(
            item for item in snapshot.state["devices"] if item["kind"] == "light"
        )
        units = {item["semantic"]: item["unit"] for item in light["capabilities"]}
        self.assertEqual("ratio", units["brightness"])
        self.assertEqual("W", units["power_w"])
        store.close()

    def test_disconnect_is_explicit_and_never_returns_stale_state_as_observed(
        self,
    ) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        transport = MemoryHomeyTransport(zones, devices)
        store = HomeOpsStore(config.plugin_database)
        target = HomeyTarget(config, store, transport)
        target.observe()
        revision = store.latest_snapshot().revision
        transport.connected = False
        with self.assertRaisesRegex(Exception, "disconnected"):
            target.observe()
        self.assertEqual(revision, store.latest_snapshot().revision)
        store.close()

    def test_failed_dispatch_reconciliation_cannot_hide_a_later_external_change(
        self,
    ) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        transport = MemoryHomeyTransport(zones, devices)
        transport.raise_on_write.add(("light-1", "onoff"))
        transport.disconnect_on_write_error = True
        store = HomeOpsStore(config.plugin_database)
        target = HomeyTarget(config, store, transport)
        target.observe()

        with self.assertRaisesRegex(Exception, "lost acknowledgement"):
            target.execute(
                ToolCall(SET_LIGHT, {"alias": "zone_1_main_light", "on": True})
            )
        denied = target.execute(
            ToolCall(SET_LIGHT, {"alias": "zone_1_main_light", "on": True})
        )
        self.assertFalse(denied.succeeded)
        self.assertIn("no fresh Homey observation", denied.error or "")
        self.assertEqual(1, len(transport.writes))
        with self.assertRaisesRegex(Exception, "disconnected"):
            target.observe()

        transport.connected = True
        transport.external_set("light-1", "onoff", True)
        target.observe()

        evidence = store.preferences()
        self.assertEqual(1, len(evidence))
        self.assertEqual("INFERRED", evidence[0]["grade"])
        self.assertEqual(
            "unattributed_control_change_detected", evidence[0]["source"]
        )
        store.close()

    def test_missing_house_scope_is_unknown_not_vacuously_satisfied(self) -> None:
        config = fixture_config(self.base, zone_count=1)
        store = HomeOpsStore(config.plugin_database)
        charter = HomeCharterCompiler().compile(CHARTER, devices=config.devices)
        store.save_charter(charter, CHARTER)
        target = HomeyTarget(config, store, MemoryHomeyTransport({}, {}))

        snapshot = target.observe()

        self.assertTrue(snapshot.state["obligations"])
        self.assertTrue(
            all(item["status"] == "UNKNOWN" for item in snapshot.state["obligations"])
        )
        with self.assertRaisesRegex(RuntimeError, "lacks complete evidence"):
            target.goal_satisfied(
                Goal("goal", "home", "maintain", {"charter": "active"}), snapshot
            )
        store.close()

    def test_explicit_charter_zone_ignores_unconfigured_observed_zones(self) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(3)
        store = HomeOpsStore(config.plugin_database)
        charter = HomeCharterCompiler().compile(
            CHARTER,
            zone_aliases=("zone_1",),
            devices=config.devices,
        )
        store.save_charter(charter, CHARTER)
        target = HomeyTarget(config, store, MemoryHomeyTransport(zones, devices))

        snapshot = target.observe()

        lighting = [
            item
            for item in snapshot.state["obligations"]
            if item["domain"] == "lighting"
        ]
        self.assertEqual(["zone_1"], [item["zone"] for item in lighting])
        self.assertEqual("VIOLATED", lighting[0]["status"])
        store.close()

    def test_installed_distribution_exposes_engine_plugins_entrypoint(self) -> None:
        entrypoints = {
            item.name: item.value
            for item in metadata.entry_points(group="engine.plugins")
        }
        self.assertEqual("engine_homey.v2:load_plugin_v2", entrypoints.get("homey"))
        self.assertNotIn("homey_v1", entrypoints)

    def test_v2_registry_discovers_zero_argument_installed_plugin_factory(self) -> None:
        config_path = self.base / "entrypoint.toml"
        config_path.write_text(
            f"""
[homey]
address = "http://127.0.0.1"
target_id = "home"
mode = "observe"
events = false
plugin_database = "{self.base / 'entrypoint-homeops.db'}"
engine_database = "{self.base / 'entrypoint-engine.db'}"
""".strip(),
            encoding="utf-8",
        )
        from engine import PluginRegistryV2

        registry = PluginRegistryV2()
        with patch.dict(
            "os.environ",
            {
                "ENGINE_HOMEY_CONFIG": str(config_path),
                "ENGINE_HOMEY_TOKEN": "entrypoint-secret",
            },
            clear=False,
        ):
            loaded = registry.discover_installed()
        self.assertIn("engine.homey", loaded, registry.discovery_failures)
        target = next(item for item in registry.providers if item.target_id == "home")
        self.assertNotIn("entrypoint-secret", repr(target.target.config))
        target.target.store.close()


if __name__ == "__main__":
    unittest.main()
