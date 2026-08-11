from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from engine_context.plugin import (
    ContextPlugin,
    ContextStore,
    ContextWorldProvider,
    ExplicitLocationProvider,
)
from engine_homey.config import DeviceBinding
from engine_homey.store import HomeOpsStore
from engine_homey.v2 import (
    LIGHTING_ZONE_STATE,
    PRESENCE_DARK_ON,
    HomeyGoalBaselineV2,
    create_plugin_v2,
    load_plugin_v2,
)
from engine_runtime import EngineApplication, RuntimeConfig
from engine_sdk import (
    AutonomyProfileV1,
    BehaviorBatchV1,
    BehaviorSignalV1,
    ConditionV1,
    ControlLayer,
    DesiredEffectV1,
    EntityV1,
    EvidenceGrade,
    GoalModeV2,
    GoalSpecV2,
    ObservationV1,
    RiskClass,
    RoutineCandidateStatus,
    RoutineCandidateV1,
    RoutineShadowEventV1,
    RoutineSpecV1,
    RoutineStatus,
    ScopedConditionV1,
    StandingMandateV1,
    WorldSnapshotV2,
    canonical_json,
    compare_manifests,
    load_static_manifest,
)
from fakes import FakeEventSource, MemoryHomeyTransport, fixture_config, fixture_house

from engine import (
    DeterministicExecutiveBrainV2,
    PluginRegistryV2,
    WorldHeartV2,
    WorldStore,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PLUGINS_ROOT = PLUGIN_ROOT.parent


class HomeyV2WorldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-homey-v2-")
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _home(self, *, zones: int = 3, cameras: int = 8):
        config = fixture_config(self.base, zone_count=zones)
        raw_zones, raw_devices = fixture_house(zones)
        now = datetime.now(UTC).isoformat()
        for index in range(cameras):
            raw_devices[f"camera-{index}"] = {
                "id": f"camera-{index}",
                "name": f"Camera {index}",
                "zone": f"zone-{index % zones + 1}",
                "class": "camera",
                "available": True,
                "capabilities": ["alarm_motion"],
                "capabilitiesObj": {
                    "alarm_motion": {
                        "id": "alarm_motion", "value": False,
                        "lastUpdated": now, "type": "boolean",
                        "getable": True, "setable": False,
                    }
                },
            }
        transport = MemoryHomeyTransport(raw_zones, raw_devices)
        plugin_store = HomeOpsStore(config.plugin_database)
        plugin = create_plugin_v2(
            config, plugin_store, transport=transport,
            event_source=FakeEventSource(),
        )
        return config, transport, plugin_store, plugin

    def test_static_and_loaded_homey_manifests_match(self) -> None:
        config, transport, store, plugin = self._home(zones=1, cameras=0)
        del config, transport
        try:
            static = load_static_manifest(PLUGIN_ROOT)
            self.assertEqual((), compare_manifests(static, plugin.manifest))
        finally:
            store.close()

    def test_entrypoint_factory_is_manifest_only_until_runtime_use(self) -> None:
        plugin = load_plugin_v2()
        self.assertEqual("engine.homey", plugin.manifest.id)
        self.assertIsNone(plugin._plugin)

    def test_generic_v3_autonomy_uses_same_heart_without_homey_core_branch(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        registry = PluginRegistryV2()
        registry.register(plugin, PLUGIN_ROOT)
        app = EngineApplication(
            RuntimeConfig(store_path=self.base / "autonomy-v3.sqlite3"),
            registry=registry,
        )
        zone_id = f"homey:{config.target_id}:zone:zone_1"
        try:
            with app.lease():
                app.autonomy_enroll(
                    plugin_id="engine.homey",
                    strategy_id="homey.enrolled-lighting-state/v1",
                    target_ids=(config.target_id,),
                    entity_ids=(zone_id,),
                    capability_families=(LIGHTING_ZONE_STATE,),
                    goal_template_ids=("homey.lighting-zone-state/v1",),
                    limits={"desired_on": True},
                    instantiate_goal_templates=True,
                )
            app.autonomy_mode("delegated")
            with app.lease():
                app.heart.run_cycle()
            self.assertTrue(
                transport.devices["light-1"]["capabilitiesObj"]["onoff"]["value"]
            )
            self.assertEqual(0, app.store.brain_call_count())
            self.assertEqual(1, len(app.store.dispatch_attempts()))
            self.assertIsNotNone(
                app.store.dispatch_attempts()[0].autonomy_binding
            )
        finally:
            app.close()
            plugin_store.close()

    def test_whole_world_three_zone_closed_loop_and_stable_zero_model_calls(self) -> None:
        config, transport, plugin_store, homey = self._home()
        context_manifest = load_static_manifest(
            PLUGINS_ROOT / "engine-context"
        )
        context_store = ContextStore(self.base / "context.sqlite3")
        context = ContextPlugin(
            context_manifest,
            (
                ContextWorldProvider(
                    context_store, context_manifest,
                    ExplicitLocationProvider(None, None), None,
                    share_location_with_weather=False,
                ),
            ),
        )
        registry = PluginRegistryV2()
        registry.register(homey, PLUGIN_ROOT)
        registry.register(context, PLUGINS_ROOT / "engine-context")
        world_store = WorldStore(self.base / "engine-world.sqlite3")
        mandate = _home_mandate(config.target_id)
        world_store.save_mandate(mandate)
        goal = HomeyGoalBaselineV2().compile_lighting(
            "Ik ben op vakantie; houd relevante donkere gebieden zichtbaar en rustig.",
            target_id=config.target_id,
            mandate_id=mandate.id,
        )
        world_store.create_goal(goal)
        brain = DeterministicExecutiveBrainV2()
        heart = WorldHeartV2(world_store, registry, brain)
        try:
            for _ in range(20):
                result = heart.run_once(goal.id)
                if result.status == "monitoring":
                    break
            self.assertEqual("monitoring", result.status)
            snapshot = world_store.latest_world_snapshot()
            assert snapshot is not None
            self.assertEqual(
                {config.target_id, "engine.context.local"},
                set(snapshot.target_revisions),
            )
            zones = [item for item in snapshot.entities if item.entity_type == "homey.zone"]
            cameras = [item for item in snapshot.entities if item.entity_type == "homey.camera"]
            detections = [item for item in snapshot.observations if item.property == "camera.detection"]
            self.assertEqual(3, len(zones))
            self.assertEqual(8, len(cameras))
            self.assertEqual(8, len(detections))
            for index in range(1, 4):
                light = transport.devices[f"light-{index}"]["capabilitiesObj"]
                sensor = transport.devices[f"sensor-{index}"]["capabilitiesObj"]
                self.assertTrue(light["onoff"]["value"])
                self.assertGreaterEqual(sensor["measure_luminance"]["value"], 60)
                self.assertLessEqual(sensor["measure_luminance"]["value"], 120)
                self.assertLessEqual(light["measure_power"]["value"], 20)
            calls = world_store.brain_call_count(goal.id)
            stable = heart.run_once(goal.id)
            self.assertFalse(stable.brain_called)
            self.assertEqual(calls, world_store.brain_call_count(goal.id))
            counts = world_store.lifecycle_counts(goal.id)
            self.assertGreaterEqual(counts["proposals"], 3)
            self.assertEqual(counts["proposals"], counts["requests"])
            self.assertEqual(counts["requests"], counts["authorizations"])
            self.assertEqual(counts["requests"], counts["receipts"])
            self.assertEqual(counts["requests"], counts["effects"])
        finally:
            world_store.close()
            context_store.close()
            plugin_store.close()

    def test_homey_ack_without_lux_effect_does_not_satisfy_goal(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        transport.freeze_lux = True
        registry = PluginRegistryV2()
        registry.register(plugin, PLUGIN_ROOT)
        store = WorldStore(self.base / "engine.sqlite3")
        mandate = _home_mandate(config.target_id)
        store.save_mandate(mandate)
        goal = HomeyGoalBaselineV2().compile_lighting(
            "Maintain visible light", target_id=config.target_id,
            mandate_id=mandate.id,
        )
        store.create_goal(goal)
        heart = WorldHeartV2(store, registry, DeterministicExecutiveBrainV2())
        try:
            result = heart.run_once(goal.id)
            self.assertFalse(result.effect_achieved)
            self.assertNotEqual("monitoring", result.status)
            self.assertIn("ACK", result.reason)
        finally:
            store.close()
            plugin_store.close()

    def test_homey_behavior_uses_same_automatic_learning_route_as_warehouse(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        del transport
        registry = PluginRegistryV2()
        registry.register(plugin, PLUGIN_ROOT)
        store = WorldStore(self.base / "learning.sqlite3")
        mandate = _home_mandate(config.target_id)
        store.save_mandate(mandate)
        goal = HomeyGoalBaselineV2().compile_lighting(
            "Maintain visible light with learned brightness",
            target_id=config.target_id,
            mandate_id=mandate.id,
        )
        store.create_goal(goal)
        heart = WorldHeartV2(store, registry, DeterministicExecutiveBrainV2())
        try:
            heart.observe_connected_world(refresh_targets=None)
            base = datetime.now(UTC) - timedelta(days=12)
            for index in range(5):
                plugin_store.record_preference(
                    grade="INFERRED",
                    source="unattributed_control_change_detected",
                    text=None,
                    context={
                        "changes": [
                            {
                                "alias": "zone_1_main_light",
                                "capability_id": "dim",
                                "previous": 0.1,
                                "observed": 0.6,
                            }
                        ]
                    },
                    created_at=(base + timedelta(days=index // 2)).isoformat(),
                )

            result = heart.run_cycle()[0]

            promoted = store.get_goal(goal.id)
            preference_id = "engine.homey.preference.lighting-brightness-band/v1"
            self.assertEqual([0.6, 0.65], promoted.preferences[preference_id])
            self.assertEqual(2, promoted.version)
            self.assertEqual(5, store.behavior_signal_count())
            self.assertEqual(
                0.65,
                store.proposals(goal.id)[0].semantic_parameters["brightness_max"],
            )
            self.assertNotEqual("degraded", result.status)
            # The action performed by Heart is suppressed by Homey's external
            # override detector and therefore cannot feed learning back into itself.
            heart.run_cycle()
            self.assertEqual(5, store.behavior_signal_count())
        finally:
            store.close()
            plugin_store.close()

    def test_dynamically_discovered_undeclared_family_is_opaque_read_only(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        del transport
        provider = plugin.providers[0]
        declared = provider.discover()
        unknown = replace(
            declared[0],
            id="vendor.magic.raw/v1",
            family="vendor.magic.raw",
            control_layer=ControlLayer.SEMANTIC,
        )
        provider.discover = lambda: (*declared, unknown)
        registry = PluginRegistryV2()
        registry.register(plugin, PLUGIN_ROOT)
        try:
            projected = next(
                item for item in registry.capabilities_for_target(config.target_id)
                if item.family == "vendor.magic.raw"
            )
            self.assertTrue(projected.opaque)
            self.assertEqual(ControlLayer.QUERY, projected.control_layer)
        finally:
            plugin_store.close()

    def test_presence_dark_routine_uses_guard_then_existing_closed_loop(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        registry = PluginRegistryV2()
        registry.register(plugin, PLUGIN_ROOT)
        store = WorldStore(self.base / "routine-dark.sqlite3")
        heart = WorldHeartV2(store, registry, DeterministicExecutiveBrainV2())
        zone_id = f"homey:{config.target_id}:zone:zone_1"
        template = registry.routine_template("engine.homey", PRESENCE_DARK_ON)
        routine, goal = plugin.routine_compilers[0].compile(
            template,
            {
                "id": "candidate:dark",
                "target_id": config.target_id,
                "entity_ids": (zone_id,),
                "pattern_value": {"maximum_lux": 20, "on": True},
            },
        )
        routine = replace(
            routine,
            status=RoutineStatus.ACTIVE,
            manifest_fingerprint=registry.manifest_fingerprint("engine.homey"),
        )
        mandate = _exact_mandate(
            config.target_id, zone_id, ("homey.lighting.zone",)
        )
        goal = replace(goal, mandate_id=mandate.id)
        store.save_mandate(mandate)
        store.create_goal(goal)
        store.save_routine(routine)
        try:
            for _ in range(6):
                result = heart.run_once(goal.id)
                if result.status == "monitoring":
                    break
            self.assertEqual("monitoring", result.status)
            self.assertTrue(transport.devices["light-1"]["capabilitiesObj"]["onoff"]["value"])
            self.assertGreaterEqual(
                transport.devices["sensor-1"]["capabilitiesObj"]["measure_luminance"]["value"],
                60,
            )
            self.assertIsNone(store.get_routine(routine.id).active_occurrence_key)
        finally:
            store.close()
            plugin_store.close()

    def test_zone_off_controller_mutates_one_fresh_lamp_per_request(self) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        second = deepcopy(devices["light-1"])
        second["id"] = "light-2"
        second["name"] = "Second light"
        second["capabilitiesObj"]["onoff"]["value"] = True
        second["capabilitiesObj"]["dim"]["value"] = 0.4
        devices["light-1"]["capabilitiesObj"]["onoff"]["value"] = True
        devices["light-1"]["capabilitiesObj"]["dim"]["value"] = 0.4
        devices["light-2"] = second
        config = replace(
            config,
            devices=(
                *config.devices,
                DeviceBinding(
                    "light-2", "zone_1_second_light", "zone_1", "light",
                    ("onoff", "dim"),
                    {"on": "onoff", "brightness": "dim"},
                    {"brightness": (0.0, 0.7)},
                    8.0,
                    0,
                ),
            ),
        )
        transport = MemoryHomeyTransport(zones, devices)
        plugin_store = HomeOpsStore(config.plugin_database)
        plugin = create_plugin_v2(
            config, plugin_store, transport=transport,
            event_source=FakeEventSource(),
        )
        registry = PluginRegistryV2()
        registry.register(plugin, PLUGIN_ROOT)
        store = WorldStore(self.base / "routine-off.sqlite3")
        zone_id = f"homey:{config.target_id}:zone:zone_1"
        goal = GoalSpecV2(
            "goal:zone-off", "Turn the zone off", GoalModeV2.MAINTAIN,
            {"entity_ids": [zone_id]},
            (
                DesiredEffectV1(
                    "off", LIGHTING_ZONE_STATE, {"entity_ids": [zone_id]},
                    ConditionV1(
                        "eq", path="observation:lighting.any_on", value=False
                    ),
                    {"on": False},
                ),
            ),
            mandate_id="mandate:exact-off",
        )
        routine = RoutineSpecV1(
            "routine:zone-off", "lighting.presence-absent-off/v1",
            "engine.homey", config.target_id, (zone_id,),
            ScopedConditionV1(
                "eq", {"entity_ids": [zone_id]},
                "observation:lighting.any_on", True,
            ),
            goal.id, {"kind": "event"}, 300, 90, RoutineStatus.ACTIVE,
            "homey.lighting.zone-state", {"on": False},
            manifest_fingerprint=registry.manifest_fingerprint("engine.homey"),
        )
        mandate = _exact_mandate(
            config.target_id, zone_id, (LIGHTING_ZONE_STATE,),
            mandate_id="mandate:exact-off",
        )
        store.save_mandate(mandate)
        store.create_goal(goal)
        store.save_routine(routine)
        heart = WorldHeartV2(store, registry, DeterministicExecutiveBrainV2())
        try:
            first = heart.run_once(goal.id)
            self.assertEqual(1, len(transport.writes))
            self.assertFalse(first.effect_achieved)
            second_pass = heart.run_once(goal.id)
            self.assertEqual(2, len(transport.writes))
            self.assertTrue(second_pass.effect_achieved)
            self.assertEqual("monitoring", second_pass.status)
        finally:
            store.close()
            plugin_store.close()

    def test_presence_inactive_requires_an_uninterrupted_fresh_sequence(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        transport.devices["sensor-1"]["capabilitiesObj"]["alarm_motion"]["value"] = False
        provider = plugin.providers[0]
        try:
            first = provider.observe()
            inactive = next(
                item for item in first.observations
                if item.property == "presence.inactive_since"
            )
            self.assertEqual("UNKNOWN", inactive.evidence_grade.value)
            second = provider.observe()
            inactive = next(
                item for item in second.observations
                if item.property == "presence.inactive_since"
            )
            self.assertEqual("DERIVED", inactive.evidence_grade.value)
            self.assertIsInstance(inactive.value, str)
            datetime.fromisoformat(inactive.value)
        finally:
            plugin_store.close()

    def test_provider_revision_advances_only_on_quantized_semantic_change(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        del config
        provider = plugin.providers[0]
        try:
            provider.observe()
            established = provider.observe()
            unchanged = provider.observe()
            self.assertEqual(established.revision, unchanged.revision)

            sensor = transport.devices["sensor-1"]["capabilitiesObj"]
            sensor["measure_temperature"]["value"] = 21.04
            below_step = provider.observe()
            self.assertEqual(unchanged.revision, below_step.revision)

            sensor["measure_temperature"]["value"] = 21.06
            changed = provider.observe()
            self.assertEqual(below_step.revision + 1, changed.revision)
        finally:
            plugin_store.close()

    def test_restart_with_unchanged_world_preserves_revision_and_presence(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        transport.devices["sensor-1"]["capabilitiesObj"]["alarm_motion"][
            "value"
        ] = False
        provider = plugin.providers[0]
        first_store = plugin_store
        established = provider.observe()
        established = provider.observe()
        inactive_since = next(
            item.value
            for item in established.observations
            if item.entity_id.endswith(":zone:zone_1")
            and item.property == "presence.inactive_since"
        )
        self.assertIsInstance(inactive_since, str)
        first_store.close()

        restarted_store = HomeOpsStore(config.plugin_database)
        restarted_plugin = create_plugin_v2(
            config,
            restarted_store,
            transport=transport,
            event_source=FakeEventSource(),
        )
        try:
            restarted = restarted_plugin.providers[0].observe()
            restarted_inactive_since = next(
                item.value
                for item in restarted.observations
                if item.entity_id.endswith(":zone:zone_1")
                and item.property == "presence.inactive_since"
            )
            self.assertEqual(established.revision, restarted.revision)
            self.assertEqual(inactive_since, restarted_inactive_since)
            projection = restarted_store.provider_projection("homey-world")
            assert projection is not None
            self.assertEqual(established.revision, projection.revision)
        finally:
            restarted_store.close()

    def test_restart_with_changed_world_consumes_exactly_one_revision(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        initial = plugin.providers[0].observe()
        plugin_store.close()
        transport.external_set("sensor-1", "alarm_motion", False)
        native_boundary = transport.devices["sensor-1"]["capabilitiesObj"][
            "alarm_motion"
        ]["lastUpdated"]

        restarted_store = HomeOpsStore(config.plugin_database)
        restarted_plugin = create_plugin_v2(
            config,
            restarted_store,
            transport=transport,
            event_source=FakeEventSource(),
        )
        try:
            provider = restarted_plugin.providers[0]
            changed = provider.observe()
            self.assertEqual(initial.revision + 1, changed.revision)
            inactive_since = next(
                item
                for item in changed.observations
                if item.entity_id.endswith(":zone:zone_1")
                and item.property == "presence.inactive_since"
            )
            self.assertEqual("DERIVED", inactive_since.evidence_grade.value)
            self.assertEqual(native_boundary, inactive_since.value)

            confirmed = provider.observe()
            self.assertEqual(changed.revision, confirmed.revision)
        finally:
            restarted_store.close()

    def test_sensor_quantization_boundaries(self) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        light = devices["light-1"]["capabilitiesObj"]
        sensor = devices["sensor-1"]["capabilitiesObj"]
        light["measure_power"]["value"] = 0.0
        sensor["measure_luminance"]["value"] = 7.49
        sensor["measure_temperature"]["value"] = 21.24
        sensor["measure_battery"] = {
            "id": "measure_battery",
            "value": 52.49,
            "lastUpdated": datetime.now(UTC).isoformat(),
            "type": "number",
            "units": "%",
            "getable": True,
            "setable": False,
        }
        devices["sensor-1"]["capabilities"].append("measure_battery")
        transport = MemoryHomeyTransport(zones, devices)
        plugin_store = HomeOpsStore(config.plugin_database)
        plugin = create_plugin_v2(
            config,
            plugin_store,
            transport=transport,
            event_source=FakeEventSource(),
        )
        provider = plugin.providers[0]

        def value(observation, entity_suffix, property_name):
            return next(
                item.value
                for item in observation.observations
                if item.entity_id.endswith(entity_suffix)
                and item.property == property_name
            )

        try:
            lower = provider.observe()
            self.assertEqual(0.0, value(lower, "main_light", "power_w"))
            self.assertEqual(5.0, value(lower, "sensor", "illuminance_lux"))
            self.assertEqual(21.2, value(lower, "sensor", "temperature_c"))
            self.assertEqual(52.0, value(lower, "sensor", "battery"))

            live_light = transport.devices["light-1"]["capabilitiesObj"]
            live_sensor = transport.devices["sensor-1"]["capabilitiesObj"]
            live_light["measure_power"]["value"] = 0.01
            live_sensor["measure_luminance"]["value"] = 9.99
            live_sensor["measure_temperature"]["value"] = 21.25
            live_sensor["measure_battery"]["value"] = 52.5
            upper = provider.observe()
            self.assertEqual(1.0, value(upper, "main_light", "power_w"))
            self.assertEqual(5.0, value(upper, "sensor", "illuminance_lux"))
            self.assertEqual(21.3, value(upper, "sensor", "temperature_c"))
            self.assertEqual(53.0, value(upper, "sensor", "battery"))

            live_sensor["measure_luminance"]["value"] = 10.0
            next_lux_bucket = provider.observe()
            self.assertEqual(
                10.0, value(next_lux_bucket, "sensor", "illuminance_lux")
            )
        finally:
            plugin_store.close()

    def test_poll_and_freshness_intervals_are_wired_from_config(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        del transport
        try:
            provider = plugin.providers[0]
            self.assertEqual(config.poll_interval_seconds, provider.poll_interval_seconds)
            self.assertEqual(
                config.max_snapshot_age_seconds, provider.freshness_seconds
            )
        finally:
            plugin_store.close()

    def test_same_revision_confirmation_keeps_homey_observation_fresh(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        del transport
        registry = PluginRegistryV2()
        registry.register(plugin, PLUGIN_ROOT)
        store = WorldStore(self.base / "confirmation-engine.sqlite3")
        boundary = [datetime.now(UTC)]
        provider = plugin.providers[0]
        provider.target._clock = lambda: boundary[0]
        heart = WorldHeartV2(
            store,
            registry,
            DeterministicExecutiveBrainV2(),
            clock=lambda: boundary[0],
        )
        try:
            heart.observe_connected_world(refresh_targets=None)
            original = store.latest_target_observation(config.target_id)
            assert original is not None

            boundary[0] += timedelta(seconds=29)
            heart.observe_connected_world(refresh_targets=None)
            confirmed = store.latest_target_observation(config.target_id)
            assert confirmed is not None
            self.assertEqual(original.revision, confirmed.revision)
            self.assertEqual(original.observed_at, confirmed.observed_at)
            self.assertEqual(boundary[0].isoformat(), confirmed.confirmed_at)

            boundary[0] += timedelta(seconds=2)
            snapshot = heart.observe_connected_world(refresh_targets=set())
            self.assertFalse(snapshot.coverage["targets"][config.target_id]["stale"])
        finally:
            store.close()
            plugin_store.close()

    def test_unchanged_idle_loop_writes_at_most_one_target_row(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        del transport
        registry = PluginRegistryV2()
        registry.register(plugin, PLUGIN_ROOT)
        store = WorldStore(self.base / "idle-engine.sqlite3")
        provider = plugin.providers[0]
        try:
            # Establish the continuity-derived presence boundary before the
            # measured idle window.
            store.save_target_observation(provider.observe())
            store.save_target_observation(provider.observe())
            before = store.connection.execute(
                "SELECT COUNT(*) FROM target_observations_v2 WHERE target_id=?",
                (config.target_id,),
            ).fetchone()[0]
            for _ in range(10):
                store.save_target_observation(provider.observe())
            after = store.connection.execute(
                "SELECT COUNT(*) FROM target_observations_v2 WHERE target_id=?",
                (config.target_id,),
            ).fetchone()[0]
            self.assertLessEqual(after - before, 1)
        finally:
            store.close()
            plugin_store.close()

    def test_known_homey_flow_change_is_not_published_as_behavior(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        del config, transport
        provider = plugin.providers[0]
        provider.observe()
        plugin_store.record_preference(
            grade="INFERRED",
            source="unattributed_control_change_detected",
            text=None,
            context={
                "origin": "flow",
                "changes": [
                    {
                        "alias": "zone_1_main_light",
                        "capability_id": "onoff",
                        "previous": False,
                        "observed": True,
                    }
                ],
            },
        )
        try:
            batch = plugin.experience_providers[0].read(None, 100)
            self.assertEqual((), batch.signals)
        finally:
            plugin_store.close()

    def test_yolo_alias_changes_mode_without_creating_homey_authority(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        del transport
        registry = PluginRegistryV2()
        registry.register(plugin, PLUGIN_ROOT)
        app = EngineApplication(
            RuntimeConfig(store_path=self.base / "yolo.sqlite3"), registry=registry
        )
        zone_id = f"homey:{config.target_id}:zone:zone_1"
        try:
            del zone_id
            self.assertEqual("delegated", app.yolo_alias_enable()["mode"])
            self.assertEqual((), app.store.autonomy_enrollments())
            self.assertEqual((), app.store.autonomy_profiles())
            self.assertEqual("paused", app.yolo_alias_disable()["mode"])
        finally:
            app.close()
            plugin_store.close()

    def test_daily_off_real_shadow_survives_restart_and_dispatches_nothing(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        del transport
        registry = PluginRegistryV2()
        registry.register(plugin, PLUGIN_ROOT)
        store_path = self.base / "shadow.sqlite3"
        store = WorldStore(store_path)
        zone_id = f"homey:{config.target_id}:zone:zone_1"
        base = datetime(2026, 7, 20, 22, 0, tzinfo=UTC)
        signals = tuple(
            BehaviorSignalV1(
                id=f"daily-off:{index}",
                plugin_id="engine.homey",
                target_id=config.target_id,
                entity_id=zone_id,
                capability_family=LIGHTING_ZONE_STATE,
                preference_id="engine.homey.preference.lighting-brightness-band/v1",
                old_value=True,
                new_value=False,
                context={"kind": "lighting-routine", "zone_id": zone_id},
                observed_at=(base + timedelta(days=index // 2)).isoformat(),
                provenance={
                    "origin": "unknown",
                    "local_date": (base + timedelta(days=index // 2)).date().isoformat(),
                },
                routine_template_id="lighting.daily-off/v1",
                pattern_value={"minute_of_day": 1320, "on": False},
            )
            for index in range(5)
        )
        store.save_behavior_batch(
            "homey-behavior", "engine.homey", BehaviorBatchV1("5", signals)
        )
        clock = [datetime(2026, 8, 1, 22, 0, tzinfo=UTC)]
        heart = WorldHeartV2(
            store, registry, DeterministicExecutiveBrainV2(),
            clock=lambda: clock[0],
        )
        candidate = heart.routine_learner.ingest_signal(
            signals[-1], _routine_world(1, config.target_id, zone_id, clock[0], True)
        )
        assert candidate is not None
        self.assertEqual(RoutineCandidateStatus.SHADOW, candidate.status)
        try:
            for index in range(3):
                clock[0] = datetime(2026, 8, index + 1, 22, 0, tzinfo=UTC)
                heart.routine_learner.advance(
                    _routine_world(index * 2 + 1, config.target_id, zone_id, clock[0], True)
                )
                clock[0] += timedelta(minutes=10)
                heart.routine_learner.advance(
                    _routine_world(index * 2 + 2, config.target_id, zone_id, clock[0], False)
                )
            ready = store.get_routine_candidate(candidate.id)
            self.assertEqual(RoutineCandidateStatus.READY_FOR_APPROVAL, ready.status)
            events = store.shadow_events(candidate.id)
            self.assertEqual(3, len(events))
            self.assertTrue(all(item.agreement is True for item in events))
            self.assertTrue(all(item.dispatch_count == 0 for item in events))
            self.assertEqual(
                {"proposals": 0, "requests": 0, "decisions": 0,
                 "authorizations": 0, "receipts": 0, "effects": 0},
                store.lifecycle_counts(candidate.goal.id),
            )
        finally:
            store.close()

        restarted = WorldStore(store_path)
        try:
            restored = restarted.get_routine_candidate(candidate.id)
            self.assertEqual(RoutineCandidateStatus.READY_FOR_APPROVAL, restored.status)
            self.assertEqual(3, len(restarted.shadow_events(candidate.id)))
        finally:
            restarted.close()
            plugin_store.close()

    def test_external_opposite_changes_pause_then_roll_back_active_routine(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        del transport
        registry = PluginRegistryV2()
        registry.register(plugin, PLUGIN_ROOT)
        store = WorldStore(self.base / "override.sqlite3")
        zone_id = f"homey:{config.target_id}:zone:zone_1"
        goal = GoalSpecV2(
            "goal:override", "Keep off", GoalModeV2.MAINTAIN,
            {"entity_ids": [zone_id]},
            (
                DesiredEffectV1(
                    "off", LIGHTING_ZONE_STATE, {"entity_ids": [zone_id]},
                    ConditionV1(
                        "eq", path="observation:lighting.any_on", value=False
                    ),
                    {"on": False},
                ),
            ),
            mandate_id="mandate:override",
        )
        routine = RoutineSpecV1(
            "routine:override", "lighting.daily-off/v1", "engine.homey",
            config.target_id, (zone_id,),
            ScopedConditionV1(
                "eq", {"entity_ids": [zone_id]},
                "observation:lighting.any_on", True,
            ),
            goal.id, {"kind": "daily"}, 300, 70, RoutineStatus.ACTIVE,
            "homey.lighting.zone-state", {"on": False},
            manifest_fingerprint=registry.manifest_fingerprint("engine.homey"),
        )
        mandate = _exact_mandate(
            config.target_id, zone_id, (LIGHTING_ZONE_STATE,),
            mandate_id="mandate:override",
        )
        store.save_mandate(mandate)
        store.create_goal(goal)
        store.save_routine(routine)
        heart = WorldHeartV2(store, registry, DeterministicExecutiveBrainV2())
        snapshot = _routine_world(
            1, config.target_id, zone_id, datetime.now(UTC), True
        )
        try:
            for index in range(3):
                observed_at = datetime.now(UTC) + timedelta(hours=index)
                signal = BehaviorSignalV1(
                    id=f"override:{index}",
                    plugin_id="engine.homey",
                    target_id=config.target_id,
                    entity_id=zone_id,
                    capability_family=LIGHTING_ZONE_STATE,
                    preference_id="engine.homey.preference.lighting-brightness-band/v1",
                    old_value=False,
                    new_value=True,
                    context={"kind": "lighting-external-state"},
                    observed_at=observed_at.isoformat(),
                    provenance={"origin": "unknown"},
                    pattern_value={"on": True},
                )
                heart.routine_learner.ingest_signal(signal, snapshot)
                if index == 0:
                    paused = store.get_routine(routine.id)
                    self.assertIsNotNone(paused.override_until)
                    self.assertGreater(
                        datetime.fromisoformat(paused.override_until), observed_at
                    )
            self.assertEqual(
                RoutineStatus.ROLLED_BACK,
                store.get_routine(routine.id).status,
            )
            self.assertEqual("abandoned", store.get_goal(goal.id).status)
            self.assertTrue(store.get_mandate(mandate.id).revoked)
        finally:
            store.close()
            plugin_store.close()

    def test_yolo_auto_promotion_is_atomic_and_refuses_entity_expansion(self) -> None:
        config, transport, plugin_store, plugin = self._home(zones=1, cameras=0)
        del transport
        registry = PluginRegistryV2()
        registry.register(plugin, PLUGIN_ROOT)
        store = WorldStore(self.base / "auto-promote.sqlite3")
        zone_id = f"homey:{config.target_id}:zone:zone_1"
        now = datetime(2026, 8, 10, 22, 0, tzinfo=UTC)
        snapshot = _routine_world(1, config.target_id, zone_id, now, True)
        store.connection.execute(
            """
            INSERT INTO world_snapshots_v2(
                revision, snapshot_id, body_json, artifact_sha256, observed_at
            ) VALUES(?,?,?,?,?)
            """,
            (
                snapshot.revision,
                snapshot.id,
                canonical_json(snapshot),
                snapshot.sha256,
                snapshot.observed_at,
            ),
        )
        store.connection.commit()
        template = registry.routine_template(
            "engine.homey", "lighting.daily-off/v1"
        )
        routine, goal = plugin.routine_compilers[0].compile(
            template,
            {
                "id": "candidate:auto",
                "target_id": config.target_id,
                "entity_ids": (zone_id,),
                "pattern_value": {"minute_of_day": 1320, "on": False},
            },
        )
        routine = replace(
            routine,
            manifest_fingerprint=registry.manifest_fingerprint("engine.homey"),
        )
        candidate = RoutineCandidateV1(
            "candidate:auto",
            "lighting.daily-off/v1",
            "engine.homey",
            config.target_id,
            (zone_id,),
            {"minute_of_day": 1320, "on": False},
            {"kind": "lighting-routine"},
            tuple(f"evidence:{index}" for index in range(5)),
            5,
            ("2026-07-20", "2026-07-21", "2026-07-22"),
            1.0,
            RoutineCandidateStatus.SHADOW,
            routine,
            goal,
            shadow_started_at="2026-07-20T00:00:00+00:00",
            shadow_ends_at="2026-07-27T00:00:00+00:00",
            rollback_patch={"revoke_mandate": True},
        )
        store.save_routine_candidate(candidate)
        premature = replace(
            candidate,
            id="candidate:premature",
            shadow_ends_at=(now + timedelta(days=1)).isoformat(),
        )
        store.save_routine_candidate(premature)
        heart = WorldHeartV2(
            store, registry, DeterministicExecutiveBrainV2(), clock=lambda: now
        )
        with self.assertRaisesRegex(PermissionError, "window is not complete"):
            heart.routine_learner.promote(
                premature.id, profile=None, activated_by="local-owner"
            )
        for index in range(3):
            store.save_shadow_event(
                RoutineShadowEventV1(
                    f"shadow:auto:{index}", candidate.id, f"day:{index}",
                    (now - timedelta(days=3 - index)).isoformat(),
                    (now - timedelta(days=3 - index, minutes=-30)).isoformat(),
                    agreement=True,
                    desired_effect_observed_at=(
                        now - timedelta(days=3 - index, minutes=-10)
                    ).isoformat(),
                )
            )
        bad_profile = AutonomyProfileV1(
            "autonomy:bad", "engine.homey", config.target_id,
            ("homey:home:zone:another",),
            (
                "lighting.daily-off/v1",
                "lighting.presence-dark-on/v1",
                "lighting.presence-absent-off/v1",
            ),
            ("homey.lighting.zone", LIGHTING_ZONE_STATE),
            RiskClass.LOW,
            registry.manifest_fingerprint("engine.homey"),
            {
                "maximum_brightness": 0.7,
                "maximum_power_w": 20.0,
                "minimum_cooldown_seconds": 300,
            },
            now.isoformat(), "owner",
        )
        try:
            with self.assertRaisesRegex(PermissionError, "ready_for_approval"):
                heart.routine_learner.promote(
                    candidate.id, profile=None, activated_by="local-owner"
                )
            with self.assertRaisesRegex(PermissionError, "entity scope"):
                heart.routine_learner.promote(
                    candidate.id, profile=bad_profile, activated_by="yolo-profile"
                )
            profile = replace(bad_profile, id="autonomy:good", entity_ids=(zone_id,))
            store.save_autonomy_profile(profile)
            with self.assertRaisesRegex(ValueError, "immutable"):
                store.save_autonomy_profile(
                    replace(
                        profile,
                        entity_ids=(zone_id, "homey:home:zone:expanded"),
                    )
                )

            heart.routine_learner.advance(snapshot)

            promoted = store.get_routine_candidate(candidate.id)
            self.assertEqual(RoutineCandidateStatus.PROMOTED, promoted.status)
            active = store.get_routine(routine.id)
            self.assertEqual(RoutineStatus.ACTIVE, active.status)
            self.assertEqual(profile.id, active.profile_id)
            installed_goal = store.get_goal(goal.id)
            mandate = store.get_mandate(installed_goal.mandate_id)
            self.assertEqual((zone_id,), mandate.entity_ids)
            self.assertEqual(
                timedelta(hours=24),
                datetime.fromisoformat(mandate.valid_until)
                - datetime.fromisoformat(mandate.valid_from),
            )

            store.disable_autonomy_profile(profile.id, revoked_at=now.isoformat())
            self.assertTrue(store.get_mandate(mandate.id).revoked)
            self.assertEqual(
                RoutineStatus.SUSPENDED, store.get_routine(routine.id).status
            )
        finally:
            store.close()
            plugin_store.close()


def _home_mandate(target_id: str) -> StandingMandateV1:
    now = datetime.now(UTC)
    return StandingMandateV1(
        "mandate:homey-lighting",
        ("engine.homey",),
        (target_id,),
        (f"homey:{target_id}:zone:*",),
        ("homey.lighting.zone",),
        {"parameters": {"brightness": {"max": 0.7}}},
        (),
        ("learning.low-risk",),
        (now - timedelta(minutes=1)).isoformat(),
        (now + timedelta(days=30)).isoformat(),
        {"engine.homey": "0.2.0"},
        "owner",
    )


def _exact_mandate(
    target_id: str,
    entity_id: str,
    families: tuple[str, ...],
    *,
    mandate_id: str = "mandate:exact-routine",
) -> StandingMandateV1:
    now = datetime.now(UTC)
    return StandingMandateV1(
        mandate_id,
        ("engine.homey",),
        (target_id,),
        (entity_id,),
        families,
        {"parameters": {"brightness": {"max": 0.7}}},
        ("local",),
        ("learning.low-risk",),
        (now - timedelta(minutes=1)).isoformat(),
        (now + timedelta(days=30)).isoformat(),
        {"engine.homey": "0.2.0"},
        "owner",
    )


def _routine_world(
    revision: int,
    target_id: str,
    zone_id: str,
    boundary: datetime,
    any_on: bool,
) -> WorldSnapshotV2:
    stamp = boundary.isoformat()
    return WorldSnapshotV2(
        f"shadow-world:{revision}",
        revision,
        stamp,
        {"engine.context.local": revision, target_id: revision},
        (
            EntityV1(
                "context:local", "engine.context.local", "context.local",
                "fixture",
            ),
            EntityV1(zone_id, target_id, "homey.zone", "fixture"),
        ),
        (),
        (
            ObservationV1(
                f"shadow-time:{revision}", "context:local",
                "time.minute_of_day", boundary.hour * 60 + boundary.minute,
                "fixture", stamp, EvidenceGrade.DERIVED, unit="minute",
            ),
            ObservationV1(
                f"shadow-iso:{revision}", "context:local", "time.iso8601",
                stamp, "fixture", stamp, EvidenceGrade.OBSERVED,
            ),
            ObservationV1(
                f"shadow-state:{revision}", zone_id, "lighting.any_on",
                any_on, "fixture", stamp, EvidenceGrade.DERIVED,
            ),
        ),
        {},
    )


if __name__ == "__main__":
    unittest.main()
