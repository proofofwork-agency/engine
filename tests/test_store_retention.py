from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from engine_reference_world import create_plugin
from engine_runtime import EngineApplication, RuntimeConfig
from engine_runtime.cli import build_parser
from engine_sdk import (
    ActionRequestV1,
    AutonomyBindingStatusV1,
    AutonomyShadowOutcomeV1,
    DispatchAttemptStateV1,
    DispatchAttemptV1,
    canonical_json,
)
from test_world_v2 import _MutableClock

from engine import (
    DeterministicExecutiveBrainV2,
    PluginRegistryV2,
    WorldHeartV2,
    WorldStore,
)

PLUGIN_ID = "engine.reference-world"
TARGET_ID = "engine.reference-world.warehouse"
ENTITY_ID = "warehouse:bin:reserve"
FAMILY = "warehouse.transfer-bin"


class StoreRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-retention-")
        self.base = Path(self.temporary.name)
        plugin = create_plugin(self.base / "warehouse.sqlite3")
        self.addCleanup(plugin.providers[0].store.close)
        self.registry = PluginRegistryV2()
        self.registry.register(plugin, "plugins/reference-world")
        self.store = WorldStore(self.base / "engine.sqlite3")
        self.addCleanup(self.store.close)
        self.boundary = datetime(2026, 8, 11, 12, tzinfo=UTC)
        self.clock = _MutableClock(self.boundary - timedelta(hours=72))
        self.heart = WorldHeartV2(
            self.store,
            self.registry,
            DeterministicExecutiveBrainV2(),
            clock=self.clock,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_snapshots_inside_twenty_four_hours_are_retained(self) -> None:
        old = self._observe_at(self.boundary - timedelta(hours=25))
        recent = self._observe_at(self.boundary - timedelta(hours=23))

        summary = self.store.prune(self.boundary)

        with self.assertRaises(KeyError):
            self.store.world_snapshot(old.id)
        self.assertEqual(recent, self.store.world_snapshot(recent.id))
        self.assertEqual(1, summary.rows_deleted["world_snapshots_v2"])

    def test_open_dispatch_attempt_pins_old_snapshot(self) -> None:
        old, middle, recent = self._multi_day_snapshots()
        request = ActionRequestV1(
            id="request:retention-pin",
            proposal_id="proposal:retention-pin",
            goal_id="goal:retention-pin",
            plugin_id=PLUGIN_ID,
            target_id=TARGET_ID,
            entity_id=ENTITY_ID,
            capability_id="warehouse.transfer-bin/v1",
            capability_family=FAMILY,
            parameters={},
            snapshot_id=old.id,
            world_revision=old.revision,
            target_revision=old.target_revisions[TARGET_ID],
            preconditions=(),
            idempotency_key="retention-pin",
            deadline_at=(self.boundary + timedelta(hours=1)).isoformat(),
        )
        self.store.save_request(request)
        self.store.save_dispatch_attempt(
            DispatchAttemptV1(
                id="dispatch-attempt:retention-pin",
                operation_key="operation:retention-pin",
                request_id=request.id,
                authorization_id="authorization:retention-pin",
                target_id=TARGET_ID,
                entity_id=ENTITY_ID,
                conflict_domain=FAMILY,
                state=DispatchAttemptStateV1.PREPARED,
                prepared_at=self.boundary.isoformat(),
            )
        )

        self.store.prune(self.boundary)

        self.assertEqual(old, self.store.world_snapshot(old.id))
        with self.assertRaises(KeyError):
            self.store.world_snapshot(middle.id)
        self.assertEqual(recent, self.store.world_snapshot(recent.id))

    def test_pending_approval_pins_context_snapshots(self) -> None:
        old, middle, recent = self._multi_day_snapshots()
        evaluation_id = "evaluation:retention-pin"
        evaluation = {
            "id": evaluation_id,
            "context": {
                "previous_snapshot_id": old.id,
                "current_snapshot_id": middle.id,
            },
        }
        self.store.connection.execute(
            """
            INSERT INTO autonomy_evaluations_v1(
                id,enrollment_id,enrollment_revision,body_json
            ) VALUES(?,?,?,?)
            """,
            (evaluation_id, "enrollment:pin", 1, canonical_json(evaluation)),
        )
        self.store.connection.execute(
            """
            INSERT INTO autonomy_bindings_v1(
                evaluation_id,enrollment_id,status,decision_json,binding_json
            ) VALUES(?,?,?,?,?)
            """,
            (
                evaluation_id,
                "enrollment:pin",
                AutonomyBindingStatusV1.PENDING_APPROVAL.value,
                "{}",
                "{}",
            ),
        )
        self.store.connection.commit()

        self.store.prune(self.boundary)

        self.assertEqual(old, self.store.world_snapshot(old.id))
        self.assertEqual(middle, self.store.world_snapshot(middle.id))
        self.assertEqual(recent, self.store.world_snapshot(recent.id))

    def test_unscored_autonomy_shadow_outcome_pins_trigger_snapshot(self) -> None:
        old, middle, recent = self._multi_day_snapshots()
        self.store.save_autonomy_shadow_outcome(
            AutonomyShadowOutcomeV1(
                id="autonomy-shadow:retention-pin",
                enrollment_id="enrollment:pin",
                opportunity_key="key:pin",
                triggered_at=self.boundary.isoformat(),
                window_ends_at=(self.boundary + timedelta(minutes=45)).isoformat(),
                trigger_snapshot_id=old.id,
                entity_id=ENTITY_ID,
                canonical_parameters={"count": 3},
                evaluation_id="evaluation:shadow-pin",
            )
        )

        self.store.prune(self.boundary)

        self.assertEqual(old, self.store.world_snapshot(old.id))
        with self.assertRaises(KeyError):
            self.store.world_snapshot(middle.id)
        self.assertEqual(recent, self.store.world_snapshot(recent.id))
        self.assertIn(old.id, self.store.retention_pinned_snapshot_ids())

    def test_caller_supplied_pin_retains_old_snapshot(self) -> None:
        old, middle, recent = self._multi_day_snapshots()

        summary = self.store.prune(
            self.boundary, pinned_snapshot_ids=(middle.id,)
        )

        with self.assertRaises(KeyError):
            self.store.world_snapshot(old.id)
        self.assertEqual(middle, self.store.world_snapshot(middle.id))
        self.assertEqual(recent, self.store.world_snapshot(recent.id))
        self.assertIn(middle.id, summary.pinned_snapshot_ids)

    def test_every_retained_snapshot_reconstructs_and_hash_verifies(self) -> None:
        old, middle, recent = self._multi_day_snapshots()
        expected = {middle.id: middle, recent.id: recent}

        self.store.prune(
            self.boundary, pinned_snapshot_ids=(middle.id,)
        )

        rows = self.store.connection.execute(
            "SELECT snapshot_id FROM world_snapshots_v2 ORDER BY revision"
        ).fetchall()
        retained_ids = tuple(str(row["snapshot_id"]) for row in rows)
        self.assertEqual(tuple(expected), retained_ids)
        for snapshot_id in retained_ids:
            loaded = self.store.world_snapshot(snapshot_id)
            self.assertEqual(expected[snapshot_id].sha256, loaded.sha256)
            self.assertEqual(
                expected[snapshot_id].semantic_fingerprint(),
                loaded.semantic_fingerprint(),
            )
        with self.assertRaises(KeyError):
            self.store.world_snapshot(old.id)

    def test_prune_preserves_world_and_target_revision_monotonicity(self) -> None:
        _, _, recent = self._multi_day_snapshots()
        target_revision = recent.target_revisions[TARGET_ID]

        self.store.prune(self.boundary)
        next_snapshot = self._observe_at(self.boundary + timedelta(hours=1))

        self.assertEqual(recent.revision + 1, next_snapshot.revision)
        self.assertEqual(
            target_revision + 1,
            next_snapshot.target_revisions[TARGET_ID],
        )
        self.assertEqual(next_snapshot, self.store.latest_world_snapshot())

    def test_audit_tables_are_never_pruned(self) -> None:
        self._multi_day_snapshots()
        self._seed_audit_tables()
        tables = (
            "autonomy_evaluations_v1",
            "autonomy_bindings_v1",
            "execution_receipts_v2",
            "effect_deltas_v1",
            "behavior_signals_v1",
            "world_events_v2",
        )
        before = {table: self._row_count(table) for table in tables}

        self.store.prune(self.boundary)

        self.assertEqual(
            before,
            {table: self._row_count(table) for table in tables},
        )

    def test_prune_summary_status_and_counters_are_accurate(self) -> None:
        self._multi_day_snapshots()
        latest_target = self.store.latest_target_observation(TARGET_ID)
        assert latest_target is not None
        self.store.save_target_observation(
            replace(
                latest_target,
                confirmed_at=(self.boundary + timedelta(minutes=1)).isoformat(),
            )
        )
        before_snapshots = self._row_count("world_snapshots_v2")
        before_targets = self._row_count("target_observations_v2")

        summary = self.store.prune(self.boundary)
        status = self.store.retention_status()

        self.assertEqual(
            before_snapshots - self._row_count("world_snapshots_v2"),
            summary.rows_deleted["world_snapshots_v2"],
        )
        self.assertEqual(
            before_targets - self._row_count("target_observations_v2"),
            summary.rows_deleted["target_observations_v2"],
        )
        self.assertEqual(2, summary.rows_deleted["world_snapshots_v2"])
        self.assertEqual(2, summary.rows_deleted["target_observations_v2"])
        self.assertEqual(1, summary.retained_snapshots)
        self.assertEqual(1, status.counters["prune_runs"])
        self.assertEqual(1, status.counters["target_observation_deduplications"])
        self.assertEqual(2, status.counters["world_snapshots_pruned"])
        self.assertEqual(2, status.counters["target_observations_pruned"])
        self.assertEqual(1, status.tables["world_snapshots_v2"].rows)
        self.assertGreater(
            status.tables["world_snapshots_v2"].estimated_bytes, 0
        )
        self.assertEqual("incremental", status.auto_vacuum)

    def test_existing_store_auto_vacuum_setting_is_untouched(self) -> None:
        database = self.base / "existing.sqlite3"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE existing(value TEXT)")
        connection.commit()
        self.assertEqual(0, connection.execute("PRAGMA auto_vacuum").fetchone()[0])
        connection.close()

        store = WorldStore(database)
        self.addCleanup(store.close)

        self.assertEqual("none", store.retention_status().auto_vacuum)

    def test_run_forever_prunes_at_most_hourly(self) -> None:
        self.registry.providers[0].poll_interval_seconds = 0.0
        with patch.object(
            self.store, "prune", wraps=self.store.prune
        ) as prune:
            passes = self.heart.run_forever(threading.Event(), max_passes=2)

        self.assertEqual(2, passes)
        prune.assert_called_once()

    def test_runtime_store_surfaces_are_typed_and_parseable(self) -> None:
        parser = build_parser()
        status_args = parser.parse_args(["store", "status"])
        prune_args = parser.parse_args(["store", "prune", "--vacuum"])
        self.assertEqual("status", status_args.store_command)
        self.assertTrue(prune_args.vacuum)
        app = EngineApplication(
            RuntimeConfig(store_path=self.base / "runtime.sqlite3"),
            registry=PluginRegistryV2(),
        )
        self.addCleanup(app.close)

        status = app.store_status()
        with patch.object(app.store, "vacuum") as vacuum:
            summary = app.store_prune(vacuum=False)
            vacuum.assert_not_called()
            app.store_prune(vacuum=True)
            vacuum.assert_called_once_with()

        self.assertIn("world_snapshots_v2", status.tables)
        self.assertEqual(0, summary.retained_snapshots)

    def _observe_at(self, value: datetime):
        self.clock.value = value
        return self.heart.observe_connected_world(refresh_targets=None)

    def _multi_day_snapshots(self):
        return (
            self._observe_at(self.boundary - timedelta(hours=72)),
            self._observe_at(self.boundary - timedelta(hours=48)),
            self._observe_at(self.boundary - timedelta(hours=1)),
        )

    def _row_count(self, table: str) -> int:
        row = self.store.connection.execute(
            f'SELECT COUNT(*) AS value FROM "{table}"'
        ).fetchone()
        return int(row["value"])

    def _seed_audit_tables(self) -> None:
        self.store.connection.execute(
            """
            INSERT INTO autonomy_evaluations_v1(
                id,enrollment_id,enrollment_revision,body_json
            ) VALUES('evaluation:audit','enrollment:audit',1,'{}')
            """
        )
        self.store.connection.execute(
            """
            INSERT INTO autonomy_bindings_v1(
                evaluation_id,enrollment_id,status,decision_json,binding_json
            ) VALUES('evaluation:audit','enrollment:audit','rejected','{}','{}')
            """
        )
        self.store.connection.execute(
            """
            INSERT INTO execution_receipts_v2(id,request_id,body_json)
            VALUES('receipt:audit','request:audit','{}')
            """
        )
        self.store.connection.execute(
            """
            INSERT INTO effect_deltas_v1(id,request_id,body_json)
            VALUES('effect:audit','request:audit','{}')
            """
        )
        self.store.connection.execute(
            """
            INSERT INTO behavior_signals_v1(
                id,provider_id,plugin_id,target_id,entity_id,
                capability_family,preference_id,body_json
            ) VALUES(
                'signal:audit','provider:audit','plugin:audit','target:audit',
                'entity:audit','capability:audit','preference:audit','{}'
            )
            """
        )
        self.store.connection.execute(
            """
            INSERT INTO world_events_v2(goal_id,kind,source,payload_json)
            VALUES(NULL,'retention_audit_fixture','test','{}')
            """
        )
        self.store.connection.commit()


if __name__ == "__main__":
    unittest.main()
