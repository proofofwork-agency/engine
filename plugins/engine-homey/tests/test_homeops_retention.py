from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from engine_homey.store import HomeOpsStore


class HomeOpsRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="engine-homey-retention-"
        )
        self.base = Path(self.temporary.name)
        self.database = self.base / "homeops.db"
        self.store = HomeOpsStore(self.database)
        self.addCleanup(self.store.close)
        self.boundary = datetime(2026, 8, 12, 12, tzinfo=UTC)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_prune_keeps_only_the_newest_snapshot(self) -> None:
        old = self._record(0, self.boundary - timedelta(hours=72))
        middle = self._record(1, self.boundary - timedelta(hours=23))
        newest = self._record(2, self.boundary - timedelta(hours=1))

        summary = self.store.prune_snapshots(self.boundary, keep_latest=1)

        history = self.store.snapshot_history()
        self.assertEqual([newest.revision], [item.revision for item in history])
        self.assertNotIn(old.revision, [item.revision for item in history])
        self.assertNotIn(middle.revision, [item.revision for item in history])
        self.assertEqual(newest.revision, summary.newest_revision)
        self.assertEqual(1, summary.retained_rows)
        self.assertEqual(2, summary.rows_deleted)
        self.assertEqual(0.0, summary.horizon_hours)

    def test_prune_leaves_every_non_snapshot_table_untouched(self) -> None:
        self._record(0, self.boundary - timedelta(hours=48))
        self._record(1, self.boundary - timedelta(hours=1))
        alias = self.store.alias_for("zone", "zone-id", "Living Room")
        charter = {"version_id": "charter:v1", "rules": ["observe"]}
        self.store.save_charter(charter, "observe")
        preference_id = self.store.record_preference(
            grade="INFERRED",
            source="test",
            text=None,
            context={"fixture": True},
        )
        projection, _ = self.store.save_provider_projection(
            "homey-world",
            "semantic-fixture",
            {"inactive_since": {}},
            self.boundary.isoformat(),
        )
        tables = (
            "aliases",
            "charters",
            "active_charter",
            "preference_evidence",
            "provider_revision_ledger",
            "provider_projection_state",
        )
        before = {table: self._row_count(table) for table in tables}

        self.store.prune_snapshots(self.boundary, keep_latest=1)

        self.assertEqual(before, {table: self._row_count(table) for table in tables})
        self.assertEqual(alias, self.store.alias_for("zone", "zone-id", "ignored"))
        self.assertEqual(charter, self.store.active_charter())
        self.assertEqual(preference_id, self.store.preferences()[0]["id"])
        self.assertEqual(projection, self.store.provider_projection("homey-world"))

    def test_revision_remains_monotone_after_pruning(self) -> None:
        first = self._record(0, self.boundary - timedelta(hours=72))
        newest = self._record(1, self.boundary - timedelta(hours=48))

        self.store.prune_snapshots(self.boundary, keep_latest=1)
        after = self._record(2, self.boundary + timedelta(minutes=1))

        self.assertEqual(first.revision + 1, newest.revision)
        self.assertEqual(newest.revision + 1, after.revision)
        self.assertEqual(after, self.store.latest_snapshot())

    def test_prune_reclaims_allocated_pages_on_fresh_store(self) -> None:
        for index in range(72):
            self._record(
                index,
                self.boundary - timedelta(hours=72 - index),
                payload_bytes=16_384,
            )
        self._checkpoint()
        before_size = self.database.stat().st_size
        before_pages = self._pragma("page_count")

        summary = self.store.prune_snapshots(self.boundary, keep_latest=1)
        self._checkpoint()
        status = self.store.snapshot_storage_status()

        self.assertEqual("incremental", status.auto_vacuum)
        self.assertGreater(summary.rows_deleted, 0)
        self.assertGreater(summary.pages_reclaimed, before_pages // 2)
        self.assertLess(self._pragma("page_count"), before_pages)
        self.assertLess(self.database.stat().st_size, before_size)
        self.assertEqual(0, status.free_bytes)
        self.assertEqual(summary.retained_rows, status.rows)
        self.assertEqual(1, status.counters["snapshot_prune_runs"])
        self.assertEqual(
            summary.rows_deleted,
            status.counters["snapshot_rows_pruned"],
        )

    def test_retention_capability_is_never_invoked_implicitly(self) -> None:
        for index in range(4):
            self._record(
                index,
                self.boundary - timedelta(hours=48 - index),
            )

        status = self.store.snapshot_storage_status()

        self.assertEqual(4, status.rows)
        self.assertEqual(0, status.counters["snapshot_prune_runs"])
        self.assertEqual(0, status.counters["snapshot_rows_pruned"])

    def test_prune_and_counters_roll_back_together(self) -> None:
        self._record(0, self.boundary - timedelta(hours=48))
        self._record(1, self.boundary - timedelta(hours=1))
        self.store._connection.execute(
            """
            CREATE TRIGGER reject_prune_counter
            BEFORE UPDATE ON snapshot_storage_counters_v1
            WHEN NEW.name = 'snapshot_prune_runs'
            BEGIN
                SELECT RAISE(ABORT, 'prune counter failed');
            END
            """
        )
        self.store._connection.commit()

        with self.assertRaisesRegex(sqlite3.IntegrityError, "prune counter failed"):
            self.store.prune_snapshots(self.boundary, keep_latest=1)

        status = self.store.snapshot_storage_status()
        self.assertEqual(2, status.rows)
        self.assertEqual(0, status.counters["snapshot_prune_runs"])
        self.assertEqual(0, status.counters["snapshot_rows_pruned"])

    def test_existing_store_auto_vacuum_setting_is_untouched(self) -> None:
        database = self.base / "existing-homeops.db"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE existing(value TEXT)")
        connection.commit()
        self.assertEqual(0, connection.execute("PRAGMA auto_vacuum").fetchone()[0])
        connection.close()

        store = HomeOpsStore(database)
        try:
            self.assertEqual("none", store.snapshot_storage_status().auto_vacuum)
        finally:
            store.close()

    def test_keep_latest_pruning_plateaus_after_many_writes(self) -> None:
        start = self.boundary - timedelta(hours=6)
        halfway_status = None
        for poll in range(25):
            observed_at = start + timedelta(minutes=15 * poll)
            self._record(poll, observed_at, payload_bytes=4096)
            self.store.prune_snapshots(observed_at, keep_latest=1)
            if poll == 12:
                self._checkpoint()
                halfway_status = self.store.snapshot_storage_status()

        self._checkpoint()
        final_status = self.store.snapshot_storage_status()
        assert halfway_status is not None

        self.assertEqual(1, halfway_status.rows)
        self.assertEqual(1, final_status.rows)
        self.assertLessEqual(
            final_status.allocated_bytes,
            halfway_status.allocated_bytes * 1.15,
        )
        self.assertEqual(25, final_status.counters["snapshot_prune_runs"])
        self.assertEqual(24, final_status.counters["snapshot_rows_pruned"])

    def _record(
        self,
        index: int,
        observed_at: datetime,
        *,
        payload_bytes: int = 128,
    ):
        return self.store.record_snapshot(
            {
                "schema": "engine.homey.house-snapshot/v1",
                "poll": index,
                "payload": _payload(index, payload_bytes),
            },
            observed_at.isoformat(),
        )

    def _row_count(self, table: str) -> int:
        row = self.store._connection.execute(
            f'SELECT COUNT(*) AS value FROM "{table}"'
        ).fetchone()
        return int(row["value"])

    def _pragma(self, name: str) -> int:
        row = self.store._connection.execute(f"PRAGMA {name}").fetchone()
        return int(row[0])

    def _checkpoint(self) -> None:
        self.store._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _payload(seed: int, size: int) -> str:
    chunks: list[str] = []
    index = 0
    while sum(len(item) for item in chunks) < size:
        chunks.append(hashlib.sha256(f"{seed}:{index}".encode()).hexdigest())
        index += 1
    return "".join(chunks)[:size]


if __name__ == "__main__":
    unittest.main()
