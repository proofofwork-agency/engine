from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

from .models import ExperienceEvent, Goal, GoalMode, JsonObject, WorldSnapshot


class EngineStore:
    """Durable owner of goals, attention state, snapshots, and experience."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._thread_id = threading.get_ident()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                target_id TEXT NOT NULL,
                instruction TEXT NOT NULL,
                success_spec_json TEXT NOT NULL,
                priority INTEGER NOT NULL,
                max_cycles INTEGER NOT NULL,
                status TEXT NOT NULL,
                cycle INTEGER NOT NULL,
                mode TEXT NOT NULL DEFAULT 'achieve',
                intervention_cycle INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id TEXT NOT NULL REFERENCES goals(id),
                cycle INTEGER NOT NULL,
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id TEXT NOT NULL REFERENCES goals(id),
                cycle INTEGER NOT NULL,
                target_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS working_memory (
                goal_id TEXT NOT NULL REFERENCES goals(id),
                key TEXT NOT NULL,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (goal_id, key)
            );

            CREATE TABLE IF NOT EXISTS runtime_state (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS brain_performance (
                brain_id TEXT NOT NULL,
                target_profile TEXT NOT NULL,
                capability_id TEXT NOT NULL,
                consults INTEGER NOT NULL DEFAULT 0,
                effectful INTEGER NOT NULL DEFAULT 0,
                ineffectual INTEGER NOT NULL DEFAULT 0,
                total_latency_ms REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (brain_id, target_profile, capability_id)
            );
            """
        )
        self._ensure_goal_column(
            "mode", "TEXT NOT NULL DEFAULT 'achieve'"
        )
        self._ensure_goal_column(
            "intervention_cycle", "INTEGER NOT NULL DEFAULT 0"
        )
        self._connection.commit()

    def _ensure_goal_column(self, name: str, declaration: str) -> None:
        columns = {
            str(row["name"])
            for row in self._connection.execute("PRAGMA table_info(goals)").fetchall()
        }
        if name not in columns:
            self._connection.execute(
                f"ALTER TABLE goals ADD COLUMN {name} {declaration}"
            )

    def close(self) -> None:
        self._connection.close()

    @property
    def owned_by_current_thread(self) -> bool:
        return self._thread_id == threading.get_ident()

    def create_goal(self, goal: Goal) -> None:
        self._connection.execute(
            """
            INSERT INTO goals (
                id, target_id, instruction, success_spec_json,
                priority, max_cycles, status, cycle, mode, intervention_cycle
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                goal.id,
                goal.target_id,
                goal.instruction,
                self._dump(goal.success_spec),
                goal.priority,
                goal.max_cycles,
                goal.status,
                goal.cycle,
                goal.mode.value,
                goal.intervention_cycle,
            ),
        )
        self._connection.commit()
        self.append_event(goal.id, goal.cycle, "goal_created", "heart", {
            "instruction": goal.instruction,
            "target_id": goal.target_id,
            "priority": goal.priority,
            "mode": goal.mode.value,
        })

    def has_goal(self, goal_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM goals WHERE id = ?", (goal_id,)
        ).fetchone()
        return row is not None

    def get_goal(self, goal_id: str) -> Goal:
        row = self._connection.execute(
            "SELECT * FROM goals WHERE id = ?", (goal_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown goal: {goal_id}")
        return Goal(
            id=row["id"],
            target_id=row["target_id"],
            instruction=row["instruction"],
            success_spec=json.loads(row["success_spec_json"]),
            priority=row["priority"],
            max_cycles=row["max_cycles"],
            status=row["status"],
            cycle=row["cycle"],
            mode=GoalMode(row["mode"]),
            intervention_cycle=row["intervention_cycle"],
        )

    def next_active_goal(self) -> Goal | None:
        row = self._connection.execute(
            """
            SELECT id FROM goals
            WHERE status = 'active'
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
            """
        ).fetchone()
        return self.get_goal(row["id"]) if row is not None else None

    def live_goals(self) -> tuple[Goal, ...]:
        """Return goals the live Heart must work or continue observing."""
        rows = self._connection.execute(
            """
            SELECT id FROM goals
            WHERE status IN (
                'active', 'monitoring', 'waiting', 'uncertain', 'degraded'
            )
            ORDER BY
                CASE status WHEN 'active' THEN 0 ELSE 1 END,
                priority DESC,
                created_at ASC
            """
        ).fetchall()
        return tuple(self.get_goal(str(row["id"])) for row in rows)

    def advance_cycle(self, goal_id: str) -> Goal:
        self._connection.execute(
            """
            UPDATE goals
            SET cycle = cycle + 1,
                intervention_cycle = intervention_cycle + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (goal_id,),
        )
        self._connection.commit()
        return self.get_goal(goal_id)

    def set_goal_status(self, goal_id: str, status: str) -> Goal:
        self._connection.execute(
            """
            UPDATE goals SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """,
            (status, goal_id),
        )
        self._connection.commit()
        return self.get_goal(goal_id)

    def transition_goal(
        self, goal_id: str, status: str, *, reset_intervention: bool = False
    ) -> Goal:
        """Atomically change lifecycle status and optionally open a new intervention."""
        if reset_intervention:
            self._connection.execute(
                """
                UPDATE goals
                SET status = ?, intervention_cycle = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, goal_id),
            )
        else:
            self._connection.execute(
                """
                UPDATE goals SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, goal_id),
            )
        self._connection.commit()
        return self.get_goal(goal_id)

    def append_event(
        self,
        goal_id: str,
        cycle: int,
        kind: str,
        source: str,
        payload: JsonObject,
    ) -> ExperienceEvent:
        cursor = self._connection.execute(
            """
            INSERT INTO events (goal_id, cycle, kind, source, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (goal_id, cycle, kind, source, self._dump(payload)),
        )
        self._connection.commit()
        row = self._connection.execute(
            "SELECT * FROM events WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        assert row is not None
        return self._event_from_row(row)

    def recent_events(self, goal_id: str, limit: int = 30) -> tuple[ExperienceEvent, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM (
                SELECT * FROM events WHERE goal_id = ? ORDER BY id DESC LIMIT ?
            ) ORDER BY id ASC
            """,
            (goal_id, limit),
        ).fetchall()
        return tuple(self._event_from_row(row) for row in rows)

    def all_events(self, goal_id: str) -> tuple[ExperienceEvent, ...]:
        rows = self._connection.execute(
            "SELECT * FROM events WHERE goal_id = ? ORDER BY id ASC", (goal_id,)
        ).fetchall()
        return tuple(self._event_from_row(row) for row in rows)

    def save_snapshot(self, goal_id: str, cycle: int, snapshot: WorldSnapshot) -> None:
        self._connection.execute(
            """
            INSERT INTO snapshots (
                goal_id, cycle, target_id, revision, state_json, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                goal_id,
                cycle,
                snapshot.target_id,
                snapshot.revision,
                self._dump(snapshot.state),
                snapshot.observed_at,
            ),
        )
        self._connection.commit()

    def latest_snapshot(self, goal_id: str) -> WorldSnapshot | None:
        row = self._connection.execute(
            """
            SELECT * FROM snapshots WHERE goal_id = ? ORDER BY id DESC LIMIT 1
            """,
            (goal_id,),
        ).fetchone()
        if row is None:
            return None
        return WorldSnapshot(
            target_id=row["target_id"],
            revision=row["revision"],
            state=json.loads(row["state_json"]),
            observed_at=row["observed_at"],
        )

    def set_memory(self, goal_id: str, key: str, value: Any) -> None:
        self._connection.execute(
            """
            INSERT INTO working_memory (goal_id, key, value_json)
            VALUES (?, ?, ?)
            ON CONFLICT(goal_id, key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (goal_id, key, self._dump(value)),
        )
        self._connection.commit()

    def delete_memory(self, goal_id: str, key: str) -> None:
        self._connection.execute(
            "DELETE FROM working_memory WHERE goal_id = ? AND key = ?",
            (goal_id, key),
        )
        self._connection.commit()

    def load_memory(self, goal_id: str) -> JsonObject:
        rows = self._connection.execute(
            "SELECT key, value_json FROM working_memory WHERE goal_id = ?",
            (goal_id,),
        ).fetchall()
        return {row["key"]: json.loads(row["value_json"]) for row in rows}

    def note_catalog(self, fingerprint: str, snapshot: JsonObject) -> bool:
        previous = self.get_runtime_state("catalog_fingerprint")
        changed = previous != fingerprint
        if changed:
            self._connection.execute(
                "INSERT INTO system_events (kind, payload_json) VALUES (?, ?)",
                (
                    "catalog_changed",
                    self._dump(
                        {
                            "previous_fingerprint": previous,
                            "fingerprint": fingerprint,
                            "catalog": snapshot,
                        }
                    ),
                ),
            )
            self.set_runtime_state("catalog_fingerprint", fingerprint, commit=False)
            self._connection.commit()
        return changed

    def set_runtime_state(self, key: str, value: Any, commit: bool = True) -> None:
        self._connection.execute(
            """
            INSERT INTO runtime_state (key, value_json) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, self._dump(value)),
        )
        if commit:
            self._connection.commit()

    def get_runtime_state(self, key: str) -> Any | None:
        row = self._connection.execute(
            "SELECT value_json FROM runtime_state WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row["value_json"]) if row is not None else None

    def system_events(self) -> tuple[JsonObject, ...]:
        rows = self._connection.execute(
            "SELECT * FROM system_events ORDER BY id ASC"
        ).fetchall()
        return tuple(
            {
                "id": row["id"],
                "kind": row["kind"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        )

    def append_system_event(self, kind: str, payload: JsonObject) -> JsonObject:
        cursor = self._connection.execute(
            "INSERT INTO system_events (kind, payload_json) VALUES (?, ?)",
            (kind, self._dump(payload)),
        )
        self._connection.commit()
        row = self._connection.execute(
            "SELECT * FROM system_events WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        assert row is not None
        return {
            "id": row["id"],
            "kind": row["kind"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }

    def record_brain_consult(
        self, brain_id: str, target_profile: str, latency_ms: float
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO brain_performance (
                brain_id, target_profile, capability_id, consults, total_latency_ms
            ) VALUES (?, ?, '*', 1, ?)
            ON CONFLICT(brain_id, target_profile, capability_id) DO UPDATE SET
                consults = consults + 1,
                total_latency_ms = total_latency_ms + excluded.total_latency_ms
            """,
            (brain_id, target_profile, latency_ms),
        )
        self._connection.commit()

    def record_brain_outcome(
        self,
        brain_id: str,
        target_profile: str,
        capability_id: str,
        effectful: bool,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO brain_performance (
                brain_id, target_profile, capability_id, effectful, ineffectual
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(brain_id, target_profile, capability_id) DO UPDATE SET
                effectful = effectful + excluded.effectful,
                ineffectual = ineffectual + excluded.ineffectual
            """,
            (
                brain_id,
                target_profile,
                capability_id,
                int(effectful),
                int(not effectful),
            ),
        )
        self._connection.commit()

    def brain_performance(self, target_profile: str) -> JsonObject:
        rows = self._connection.execute(
            """
            SELECT brain_id,
                   SUM(consults) AS consults,
                   SUM(effectful) AS effectful,
                   SUM(ineffectual) AS ineffectual,
                   SUM(total_latency_ms) AS total_latency_ms
            FROM brain_performance
            WHERE target_profile = ?
            GROUP BY brain_id
            """,
            (target_profile,),
        ).fetchall()
        result: JsonObject = {}
        for row in rows:
            outcomes = row["effectful"] + row["ineffectual"]
            result[row["brain_id"]] = {
                "consults": row["consults"],
                "effectful": row["effectful"],
                "ineffectual": row["ineffectual"],
                "mean_latency_ms": (
                    row["total_latency_ms"] / row["consults"]
                    if row["consults"]
                    else 0.0
                ),
                "effect_score": (row["effectful"] + 1) / (outcomes + 2),
            }
        return result

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> ExperienceEvent:
        return ExperienceEvent(
            id=row["id"],
            goal_id=row["goal_id"],
            cycle=row["cycle"],
            kind=row["kind"],
            source=row["source"],
            payload=json.loads(row["payload_json"]),
            created_at=row["created_at"],
        )
