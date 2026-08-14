from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime
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
        self.assertEqual(1, len(history))
        self.assertEqual(restarted.revision, history[0].revision)
        self.assertGreater(restarted.revision, first.revision)
        second_store.close()

    def test_snapshot_bodies_are_compressed_and_storage_counters_are_durable(
        self,
    ) -> None:
        database = self.base / "compressed-homeops.db"
        state = {
            "schema": "engine.homey.house-snapshot/v1",
            "devices": [{"alias": "lamp", "padding": "x" * 4096}],
        }
        raw_body = json.dumps(
            state, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        store = HomeOpsStore(database)

        first = store.record_snapshot(state, "2026-08-11T00:00:00+00:00")
        confirmed = store.record_snapshot(
            state, "2026-08-11T00:00:30+00:00"
        )
        row = store._connection.execute(
            "SELECT typeof(state_json) AS storage_type, state_json FROM snapshots"
        ).fetchone()
        assert row is not None
        stored_body = bytes(row["state_json"])
        status = store.snapshot_storage_status()

        self.assertEqual("blob", row["storage_type"])
        self.assertTrue(
            stored_body.startswith(b"engine.homey.snapshot.zlib/v1\x00")
        )
        self.assertLess(len(stored_body), len(raw_body))
        self.assertEqual(first.revision, confirmed.revision)
        self.assertEqual(first, store.latest_snapshot())
        self.assertEqual(1, status.rows)
        self.assertEqual(len(stored_body), status.body_bytes)
        self.assertGreater(status.database_bytes, 0)
        self.assertEqual(
            status.database_bytes + status.wal_bytes,
            status.total_database_bytes,
        )
        self.assertEqual(
            {
                "snapshot_deduplications": 1,
                "snapshot_prune_runs": 0,
                "snapshot_raw_body_bytes_written": len(raw_body),
                "snapshot_rows_written": 1,
                "snapshot_rows_pruned": 0,
                "snapshot_stored_body_bytes_written": len(stored_body),
            },
            status.counters,
        )
        store.close()

        restarted = HomeOpsStore(database)
        self.assertEqual(first, restarted.latest_snapshot())
        self.assertEqual(status.counters, restarted.snapshot_storage_status().counters)
        restarted.close()

    def test_legacy_text_snapshot_remains_readable_alongside_compressed_rows(
        self,
    ) -> None:
        database = self.base / "legacy-homeops.db"
        legacy_state = {"schema": "legacy", "value": 1}
        legacy_body = json.dumps(
            legacy_state, sort_keys=True, separators=(",", ":")
        )
        legacy_hash = hashlib.sha256(legacy_body.encode("utf-8")).hexdigest()
        connection = sqlite3.connect(database)
        connection.execute(
            """
            CREATE TABLE snapshots (
                revision INTEGER PRIMARY KEY,
                state_hash TEXT NOT NULL,
                state_json TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO snapshots(
                revision, state_hash, state_json, observed_at, created_at
            ) VALUES(0, ?, ?, ?, ?)
            """,
            (
                legacy_hash,
                legacy_body,
                "2026-08-11T00:00:00+00:00",
                "2026-08-11T00:00:00+00:00",
            ),
        )
        connection.commit()
        connection.close()

        store = HomeOpsStore(database)
        self.assertEqual(legacy_state, store.latest_snapshot().state)
        changed_state = {"schema": "legacy", "value": 2}
        changed = store.record_snapshot(
            changed_state, "2026-08-11T00:01:00+00:00"
        )
        rows = store._connection.execute(
            "SELECT revision, typeof(state_json) AS storage_type FROM snapshots "
            "ORDER BY revision"
        ).fetchall()

        self.assertEqual(1, changed.revision)
        self.assertEqual([(0, "text"), (1, "blob")], [tuple(row) for row in rows])
        self.assertEqual(
            [legacy_state, changed_state],
            [snapshot.state for snapshot in store.snapshot_history()],
        )
        store.close()

    def test_snapshot_revision_stays_monotone_across_compressed_restart(self) -> None:
        database = self.base / "restart-homeops.db"
        first_state = {"schema": "snapshot", "value": 1}
        first_store = HomeOpsStore(database)
        first = first_store.record_snapshot(
            first_state, "2026-08-11T00:00:00+00:00"
        )
        first_store.close()

        restarted = HomeOpsStore(database)
        same = restarted.record_snapshot(
            first_state, "2026-08-11T00:00:30+00:00"
        )
        changed = restarted.record_snapshot(
            {"schema": "snapshot", "value": 2},
            "2026-08-11T00:01:00+00:00",
        )

        self.assertEqual(first.revision, same.revision)
        self.assertEqual(first.revision + 1, changed.revision)
        self.assertEqual(changed, restarted.latest_snapshot())
        self.assertEqual(
            [first.revision, changed.revision],
            [item.revision for item in restarted.snapshot_history()],
        )
        restarted.close()

    def test_meter_only_tick_dedupes_but_light_change_stores_current_watts(
        self,
    ) -> None:
        def house(*, on: bool, watts: float, kwh: float, observed: str) -> dict:
            return {
                "schema": "engine.homey.house-snapshot/v1",
                "devices": [
                    {
                        "alias": "lamp",
                        "kind": "light",
                        "capabilities": [
                            {
                                "id": "onoff",
                                "semantic": "on",
                                "value": on,
                                "observed_at": observed,
                                "evidence": "OBSERVED",
                            },
                            {
                                "id": "measure_power",
                                "semantic": "power_w",
                                "value": watts,
                                "observed_at": observed,
                                "evidence": "OBSERVED",
                            },
                            {
                                "id": "meter_power.imported",
                                "semantic": "energy_kwh",
                                "value": kwh,
                                "observed_at": observed,
                                "evidence": "OBSERVED",
                            },
                            {
                                "id": "voltage.phase1",
                                "semantic": "voltage",
                                "value": 230.0 + watts,
                                "observed_at": observed,
                                "evidence": "OBSERVED",
                            },
                            {
                                "id": "rssi",
                                "semantic": "rssi",
                                "value": 90 + int(watts) % 10,
                                "observed_at": observed,
                                "evidence": "OBSERVED",
                            },
                            {
                                "id": "net_load_phase1_pct",
                                "semantic": "net_load_phase1_pct",
                                "value": int(watts) % 5,
                                "observed_at": observed,
                                "evidence": "OBSERVED",
                            },
                        ],
                    }
                ],
                "obligations": [
                    {
                        "id": "energy",
                        "status": "SATISFIED",
                        "observations": {"house_power_w": watts},
                    }
                ],
            }

        store = HomeOpsStore(self.base / "meter-identity.db")
        first = store.record_snapshot(
            house(on=False, watts=1.2, kwh=10.0, observed="t0"),
            "2026-08-14T00:00:00+00:00",
        )
        meter_only = store.record_snapshot(
            house(on=False, watts=47.8, kwh=10.01, observed="t1"),
            "2026-08-14T00:00:30+00:00",
        )
        flipped = store.record_snapshot(
            house(on=True, watts=48.1, kwh=10.02, observed="t2"),
            "2026-08-14T00:01:00+00:00",
        )
        stored = store.latest_snapshot()
        status = store.snapshot_storage_status()
        store.close()

        self.assertEqual(first.revision, meter_only.revision)
        self.assertEqual(first.revision + 1, flipped.revision)
        self.assertEqual(True, stored.state["devices"][0]["capabilities"][0]["value"])
        self.assertEqual(48.1, stored.state["devices"][0]["capabilities"][1]["value"])
        self.assertEqual(
            48.1, stored.state["obligations"][0]["observations"]["house_power_w"]
        )
        self.assertEqual(1, status.counters["snapshot_deduplications"])
        self.assertEqual(2, status.counters["snapshot_rows_written"])

    def test_snapshot_insert_rolls_back_when_counter_update_fails(self) -> None:
        store = HomeOpsStore(self.base / "transactional-homeops.db")
        store._connection.execute(
            """
            CREATE TRIGGER reject_snapshot_counter
            BEFORE UPDATE ON snapshot_storage_counters_v1
            BEGIN
                SELECT RAISE(ABORT, 'counter update failed');
            END
            """
        )
        store._connection.commit()

        with self.assertRaisesRegex(sqlite3.IntegrityError, "counter update failed"):
            store.record_snapshot(
                {"schema": "snapshot", "value": 1},
                "2026-08-11T00:00:00+00:00",
            )

        self.assertIsNone(store.latest_snapshot())
        self.assertEqual(0, store.snapshot_storage_status().rows)
        store.close()

    def test_provider_projection_revision_and_state_update_atomically(self) -> None:
        config = fixture_config(self.base, zone_count=1)
        store = HomeOpsStore(config.plugin_database)
        try:
            first, changed = store.save_provider_projection(
                "homey-world",
                "semantic-a",
                {"inactive_since": {"zone_1": "2026-01-01T00:00:00+00:00"}},
                "2026-01-01T00:00:01+00:00",
            )
            self.assertTrue(changed)
            confirmed, changed = store.save_provider_projection(
                "homey-world",
                "semantic-a",
                first.presence_state,
                "2026-01-01T00:00:02+00:00",
            )
            self.assertFalse(changed)
            self.assertEqual(first.revision, confirmed.revision)

            second, changed = store.save_provider_projection(
                "homey-world",
                "semantic-b",
                {},
                "2026-01-01T00:00:03+00:00",
            )
            self.assertTrue(changed)
            self.assertEqual(first.revision + 1, second.revision)
            self.assertEqual(second, store.provider_projection("homey-world"))
        finally:
            store.close()

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

    def test_override_visible_for_each_actuator_family_outside_write_allowlist(
        self,
    ) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        now = datetime.now(UTC).isoformat()
        devices["stray-light"] = {
            "id": "stray-light",
            "name": "Stray Light",
            "zone": "zone-1",
            "class": "light",
            "available": True,
            "capabilities": ["onoff", "dim", "measure_power"],
            "capabilitiesObj": {
                "onoff": {
                    "id": "onoff",
                    "value": False,
                    "lastUpdated": now,
                    "type": "boolean",
                    "getable": True,
                    "setable": True,
                },
                "dim": {
                    "id": "dim",
                    "value": 0.2,
                    "lastUpdated": now,
                    "type": "number",
                    "getable": True,
                    "setable": True,
                },
                "measure_power": {
                    "id": "measure_power",
                    "value": 0.0,
                    "lastUpdated": now,
                    "type": "number",
                    "units": "W",
                    "getable": True,
                    "setable": False,
                },
            },
        }
        devices["thermostat-1"] = {
            "id": "thermostat-1",
            "name": "Hall Thermostat",
            "zone": "zone-1",
            "class": "thermostat",
            "available": True,
            "capabilities": ["target_temperature"],
            "capabilitiesObj": {
                "target_temperature": {
                    "id": "target_temperature",
                    "value": 20.0,
                    "lastUpdated": now,
                    "type": "number",
                    "units": "°C",
                    "getable": True,
                    "setable": True,
                },
            },
        }
        devices["cover-1"] = {
            "id": "cover-1",
            "name": "Hall Cover",
            "zone": "zone-1",
            "class": "windowcoverings",
            "available": True,
            "capabilities": ["windowcoverings_set"],
            "capabilitiesObj": {
                "windowcoverings_set": {
                    "id": "windowcoverings_set",
                    "value": 0.0,
                    "lastUpdated": now,
                    "type": "number",
                    "getable": True,
                    "setable": True,
                },
            },
        }
        devices["switch-1"] = {
            "id": "switch-1",
            "name": "Hall Switch",
            "zone": "zone-1",
            "class": "socket",
            "available": True,
            "capabilities": ["onoff"],
            "capabilitiesObj": {
                "onoff": {
                    "id": "onoff",
                    "value": False,
                    "lastUpdated": now,
                    "type": "boolean",
                    "getable": True,
                    "setable": True,
                },
            },
        }
        transport = MemoryHomeyTransport(zones, devices)
        store = HomeOpsStore(config.plugin_database)
        target = HomeyTarget(config, store, transport)
        target.observe()

        mutations = (
            ("stray-light", "onoff", True),
            ("stray-light", "dim", 0.8),
            ("thermostat-1", "target_temperature", 21.5),
            ("cover-1", "windowcoverings_set", 0.4),
            ("switch-1", "onoff", True),
        )
        for device_id, capability_id, value in mutations:
            before = len(store.preferences())
            transport.external_set(device_id, capability_id, value)
            target.observe()
            evidence = store.preferences()
            self.assertEqual(before + 1, len(evidence), capability_id)
            latest = evidence[-1]
            self.assertEqual("INFERRED", latest["grade"])
            self.assertEqual(
                "unattributed_control_change_detected", latest["source"]
            )
            changes = latest["context"]["changes"]
            self.assertTrue(
                any(item["capability_id"] == capability_id for item in changes),
                capability_id,
            )

        transport.external_set("sensor-1", "measure_luminance", 80.0)
        after_sensor = len(store.preferences())
        target.observe()
        self.assertEqual(after_sensor, len(store.preferences()))

        denied = target.execute(
            ToolCall(SET_LIGHT, {"alias": "zone_1_stray_light", "on": False})
        )
        self.assertFalse(denied.succeeded)
        self.assertIn("not allowlisted", denied.error or "")
        store.close()

    def test_engine_dispatch_still_suppresses_override_detection(self) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        transport = MemoryHomeyTransport(zones, devices)
        store = HomeOpsStore(config.plugin_database)
        target = HomeyTarget(config, store, transport)
        target.observe()
        result = target.execute(
            ToolCall(
                SET_LIGHT,
                {"alias": "zone_1_main_light", "on": True, "brightness": 0.5},
            )
        )
        self.assertTrue(result.succeeded)
        target.observe()
        self.assertEqual((), store.preferences())
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
