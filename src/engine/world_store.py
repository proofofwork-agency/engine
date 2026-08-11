from __future__ import annotations

import json
import sqlite3
import zlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from engine_sdk import (
    ActionRequestV1,
    AuthorizationV1,
    AutonomyBindingStatusV1,
    AutonomyBindingV1,
    AutonomyDecisionV1,
    AutonomyEnrollmentV2,
    AutonomyEvaluationV1,
    AutonomyModeV1,
    AutonomyProfileV1,
    BehaviorBatchV1,
    BehaviorSignalV1,
    ConditionV1,
    DesiredEffectV1,
    DispatchAttemptStateV1,
    DispatchAttemptV1,
    EffectDeltaV1,
    EntityV1,
    EvidenceGrade,
    ExecutionReceiptV2,
    GoalModeV2,
    GoalSpecV2,
    LearningCandidateV1,
    LifecycleEventV1,
    ObservationV1,
    PolicyDecisionV1,
    PreferenceEvidenceV1,
    ProposedActionV1,
    RelationHypothesisV1,
    RelationV1,
    RoutineCandidateStatus,
    RoutineCandidateV1,
    RoutineShadowEventV1,
    RoutineSpecV1,
    RoutineStatus,
    StandingMandateV1,
    SuggestionV1,
    TargetObservationV2,
    WorldSnapshotV2,
    artifact_sha256,
    canonical_json,
)

SCHEMA_VERSION = 9
_TARGET_BODY_ZLIB_PREFIX = b"engine.target-observation.zlib/v1\x00"
_OPEN_DISPATCH_STATES = (
    DispatchAttemptStateV1.PREPARED.value,
    DispatchAttemptStateV1.RECOVERY_REQUIRED.value,
    DispatchAttemptStateV1.RECEIPT_RECORDED.value,
)
_RETENTION_COUNTER_NAMES = (
    "target_observation_deduplications",
    "target_observation_rows_written",
    "prune_runs",
    "world_snapshots_pruned",
    "target_observations_pruned",
)


@dataclass(frozen=True)
class RetentionTableStatus:
    rows: int
    estimated_bytes: int


@dataclass(frozen=True)
class RetentionStatus:
    tables: dict[str, RetentionTableStatus]
    counters: dict[str, int]
    database_bytes: int
    free_bytes: int
    auto_vacuum: str


@dataclass(frozen=True)
class PruneSummary:
    boundary: str
    cutoff: str
    pinned_snapshot_ids: tuple[str, ...]
    retained_snapshots: int
    rows_deleted: dict[str, int]


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


class WorldStore:
    """Durable v2 world/goal/lifecycle ledger, separate from plugin stores."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fresh_store = not self.path.exists() or self.path.stat().st_size == 0
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        if fresh_store:
            self.connection.execute("PRAGMA auto_vacuum=INCREMENTAL")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._create_schema()
        self._migrate_v1_goals()

    def close(self) -> None:
        try:
            self.connection.close()
        except sqlite3.ProgrammingError:
            pass

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS schema_versions (
                component TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS retention_counters_v1 (
                name TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS goal_specs_v2 (
                id TEXT NOT NULL,
                version INTEGER NOT NULL,
                body_json TEXT NOT NULL,
                status TEXT NOT NULL,
                current INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id, version)
            );
            CREATE TABLE IF NOT EXISTS mandates_v1 (
                id TEXT PRIMARY KEY,
                body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS target_observations_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                body_json TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                semantic_sha256 TEXT,
                observed_at TEXT NOT NULL,
                confirmed_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(target_id, revision)
            );
            CREATE TABLE IF NOT EXISTS world_snapshots_v2 (
                revision INTEGER PRIMARY KEY,
                snapshot_id TEXT NOT NULL UNIQUE,
                body_json TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS proposed_actions_v1 (
                id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS action_requests_v1 (
                id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL, body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS policy_decisions_v1 (
                id TEXT PRIMARY KEY, request_id TEXT NOT NULL, body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS authorizations_v1 (
                id TEXT PRIMARY KEY, request_id TEXT NOT NULL, body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS execution_receipts_v2 (
                id TEXT PRIMARY KEY, request_id TEXT NOT NULL, body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS effect_deltas_v1 (
                id TEXT PRIMARY KEY, request_id TEXT NOT NULL, body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS relation_hypotheses_v1 (
                id TEXT PRIMARY KEY, body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scheduled_wakes_v2 (
                id TEXT PRIMARY KEY, goal_id TEXT, target_id TEXT,
                wake_at TEXT NOT NULL, reason TEXT NOT NULL, payload_json TEXT NOT NULL,
                handled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS learning_evidence_v1 (
                id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS learning_candidates_v1 (
                id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS plugin_experience_cursors_v1 (
                provider_id TEXT PRIMARY KEY,
                plugin_id TEXT NOT NULL,
                cursor TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS lifecycle_cursors_v1 (
                observer_id TEXT PRIMARY KEY,
                last_sequence INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS behavior_signals_v1 (
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                plugin_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                capability_family TEXT NOT NULL,
                preference_id TEXT NOT NULL,
                body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS behavior_signal_links_v1 (
                signal_id TEXT NOT NULL,
                goal_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(signal_id, goal_id),
                FOREIGN KEY(signal_id) REFERENCES behavior_signals_v1(id)
            );
            CREATE TABLE IF NOT EXISTS plan_cache_v2 (
                cache_key TEXT PRIMARY KEY, goal_id TEXT NOT NULL,
                plugin_id TEXT NOT NULL, capability_family TEXT NOT NULL,
                manifest_fingerprint TEXT NOT NULL, mandate_id TEXT NOT NULL,
                proposal_template_json TEXT NOT NULL, outcomes_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS world_events_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id TEXT, kind TEXT NOT NULL, source TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS brain_calls_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id TEXT NOT NULL, brain_id TEXT NOT NULL, purpose TEXT NOT NULL,
                snapshot_id TEXT NOT NULL, projection_sha256 TEXT NOT NULL,
                output_sha256 TEXT, latency_ms REAL, usage_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS routine_specs_v1 (
                id TEXT PRIMARY KEY,
                goal_id TEXT NOT NULL UNIQUE,
                template_id TEXT NOT NULL,
                plugin_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS routine_candidates_v1 (
                id TEXT PRIMARY KEY,
                template_id TEXT NOT NULL,
                plugin_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS routine_shadow_events_v1 (
                id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                opportunity_key TEXT NOT NULL,
                body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(candidate_id, opportunity_key),
                FOREIGN KEY(candidate_id) REFERENCES routine_candidates_v1(id)
            );
            CREATE TABLE IF NOT EXISTS autonomy_profiles_v1 (
                id TEXT PRIMARY KEY,
                plugin_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS routine_occurrences_v1 (
                routine_id TEXT NOT NULL,
                occurrence_key TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(routine_id, occurrence_key),
                FOREIGN KEY(routine_id) REFERENCES routine_specs_v1(id)
            );
            CREATE TABLE IF NOT EXISTS routine_actions_v1 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                routine_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                request_id TEXT,
                acted_at TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(routine_id) REFERENCES routine_specs_v1(id)
            );
            CREATE TABLE IF NOT EXISTS autonomy_mode_v1 (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                mode TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                changed_at TEXT NOT NULL,
                changed_by TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS autonomy_enrollments_v2 (
                id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                plugin_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                current INTEGER NOT NULL DEFAULT 1,
                body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(id,revision)
            );
            CREATE TABLE IF NOT EXISTS autonomy_enrollment_resources_v1 (
                enrollment_id TEXT NOT NULL,
                enrollment_revision INTEGER NOT NULL,
                target_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                conflict_domain TEXT NOT NULL,
                PRIMARY KEY(target_id,entity_id,conflict_domain),
                FOREIGN KEY(enrollment_id,enrollment_revision)
                    REFERENCES autonomy_enrollments_v2(id,revision)
            );
            CREATE TABLE IF NOT EXISTS autonomy_evaluations_v1 (
                id TEXT PRIMARY KEY,
                enrollment_id TEXT NOT NULL,
                enrollment_revision INTEGER NOT NULL,
                body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS autonomy_bindings_v1 (
                evaluation_id TEXT PRIMARY KEY,
                enrollment_id TEXT NOT NULL,
                status TEXT NOT NULL,
                proposal_id TEXT,
                decision_json TEXT NOT NULL,
                binding_json TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS suggestions_v1 (
                id TEXT PRIMARY KEY,
                body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS dispatch_attempts_v1 (
                id TEXT PRIMARY KEY,
                operation_key TEXT NOT NULL UNIQUE,
                request_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                conflict_domain TEXT NOT NULL,
                state TEXT NOT NULL,
                body_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.connection.execute(
            """
            INSERT INTO autonomy_mode_v1(singleton,mode,epoch,changed_at,changed_by)
            VALUES(1,'observe',1,CURRENT_TIMESTAMP,'engine.migration/v3')
            ON CONFLICT(singleton) DO NOTHING
            """
        )
        self.connection.execute(
            """
            INSERT INTO schema_versions(component, version) VALUES('engine.world', ?)
            ON CONFLICT(component) DO UPDATE SET version=excluded.version,
                applied_at=CURRENT_TIMESTAMP
            """,
            (SCHEMA_VERSION,),
        )
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO retention_counters_v1(name,value)
            VALUES(?,0)
            """,
            ((name,) for name in _RETENTION_COUNTER_NAMES),
        )
        self._migrate_target_observation_confirmations()
        self.connection.commit()

    def _migrate_target_observation_confirmations(self) -> None:
        columns = {
            str(row["name"])
            for row in self.connection.execute(
                "PRAGMA table_info(target_observations_v2)"
            ).fetchall()
        }
        if "semantic_sha256" not in columns:
            self.connection.execute(
                "ALTER TABLE target_observations_v2 ADD COLUMN semantic_sha256 TEXT"
            )
        if "confirmed_at" not in columns:
            self.connection.execute(
                "ALTER TABLE target_observations_v2 ADD COLUMN confirmed_at TEXT"
            )
        rows = self.connection.execute(
            """
            SELECT id, body_json, observed_at FROM target_observations_v2
            WHERE semantic_sha256 IS NULL OR confirmed_at IS NULL
            """
        ).fetchall()
        for row in rows:
            observation = _target_observation(
                _decode_target_observation_body(row["body_json"])
            )
            self.connection.execute(
                """
                UPDATE target_observations_v2
                SET semantic_sha256=COALESCE(semantic_sha256, ?),
                    confirmed_at=COALESCE(confirmed_at, ?)
                WHERE id=?
                """,
                (
                    observation.semantic_fingerprint(),
                    str(row["observed_at"]),
                    int(row["id"]),
                ),
            )

    def retention_status(self) -> RetentionStatus:
        tables: dict[str, RetentionTableStatus] = {}
        table_rows = self.connection.execute(
            """
            SELECT name FROM sqlite_schema
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        for table_row in table_rows:
            table = str(table_row["name"])
            identifier = _quote_identifier(table)
            columns = tuple(
                str(row["name"])
                for row in self.connection.execute(
                    f"PRAGMA table_info({identifier})"
                ).fetchall()
            )
            byte_terms = [
                f"COALESCE(length(CAST({_quote_identifier(column)} AS BLOB)),0)"
                for column in columns
            ]
            byte_expression = "+".join(byte_terms) or "0"
            status_row = self.connection.execute(
                f"""
                SELECT COUNT(*) AS rows,
                       COALESCE(SUM({byte_expression}),0) AS estimated_bytes
                FROM {identifier}
                """
            ).fetchone()
            tables[table] = RetentionTableStatus(
                rows=int(status_row["rows"]),
                estimated_bytes=int(status_row["estimated_bytes"]),
            )
        counters = {
            str(row["name"]): int(row["value"])
            for row in self.connection.execute(
                "SELECT name,value FROM retention_counters_v1 ORDER BY name"
            ).fetchall()
        }
        page_size = int(self.connection.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(self.connection.execute("PRAGMA page_count").fetchone()[0])
        free_pages = int(
            self.connection.execute("PRAGMA freelist_count").fetchone()[0]
        )
        auto_vacuum_value = int(
            self.connection.execute("PRAGMA auto_vacuum").fetchone()[0]
        )
        return RetentionStatus(
            tables=tables,
            counters=counters,
            database_bytes=page_size * page_count,
            free_bytes=page_size * free_pages,
            auto_vacuum={0: "none", 1: "full", 2: "incremental"}.get(
                auto_vacuum_value, f"unknown:{auto_vacuum_value}"
            ),
        )

    def retention_pinned_snapshot_ids(self) -> tuple[str, ...]:
        pinned: set[str] = set()
        marks = ",".join("?" for _ in _OPEN_DISPATCH_STATES)
        attempt_rows = self.connection.execute(
            f"""
            SELECT attempt.id AS attempt_id, request.body_json AS request_json
            FROM dispatch_attempts_v1 AS attempt
            LEFT JOIN action_requests_v1 AS request
              ON request.id=attempt.request_id
            WHERE attempt.state IN ({marks})
            """,
            _OPEN_DISPATCH_STATES,
        ).fetchall()
        for row in attempt_rows:
            if row["request_json"] is None:
                raise ValueError(
                    "open dispatch attempt references a missing action request: "
                    f"{row['attempt_id']}"
                )
            request = json.loads(row["request_json"])
            snapshot_id = request.get("snapshot_id")
            if not isinstance(snapshot_id, str) or not snapshot_id:
                raise ValueError(
                    "open dispatch action request has no snapshot_id: "
                    f"{row['attempt_id']}"
                )
            pinned.add(snapshot_id)

        binding_rows = self.connection.execute(
            """
            SELECT binding.evaluation_id,
                   evaluation.body_json AS evaluation_json
            FROM autonomy_bindings_v1 AS binding
            LEFT JOIN autonomy_evaluations_v1 AS evaluation
              ON evaluation.id=binding.evaluation_id
            WHERE binding.status=?
            """,
            (AutonomyBindingStatusV1.PENDING_APPROVAL.value,),
        ).fetchall()
        for row in binding_rows:
            if row["evaluation_json"] is None:
                raise ValueError(
                    "pending approval references a missing autonomy evaluation: "
                    f"{row['evaluation_id']}"
                )
            evaluation = json.loads(row["evaluation_json"])
            context = evaluation.get("context")
            if not isinstance(context, Mapping):
                raise ValueError(
                    "pending approval evaluation has no context: "
                    f"{row['evaluation_id']}"
                )
            for field in ("previous_snapshot_id", "current_snapshot_id"):
                snapshot_id = context.get(field)
                if snapshot_id is not None:
                    if not isinstance(snapshot_id, str) or not snapshot_id:
                        raise ValueError(
                            "pending approval evaluation has an invalid "
                            f"{field}: {row['evaluation_id']}"
                        )
                    pinned.add(snapshot_id)
        return tuple(sorted(pinned))

    def prune(
        self,
        boundary: datetime | str,
        pinned_snapshot_ids: tuple[str, ...] = (),
    ) -> PruneSummary:
        boundary_at = _as_utc(boundary) if isinstance(boundary, str) else boundary
        if boundary_at.tzinfo is None:
            boundary_at = boundary_at.replace(tzinfo=UTC)
        else:
            boundary_at = boundary_at.astimezone(UTC)
        cutoff = boundary_at - timedelta(hours=24)
        pinned = set(self.retention_pinned_snapshot_ids())
        pinned.update(str(item) for item in pinned_snapshot_ids)
        rows_deleted = {
            "world_snapshots_v2": 0,
            "target_observations_v2": 0,
        }
        with self.connection:
            snapshot_rows = self.connection.execute(
                """
                SELECT revision,snapshot_id,body_json,observed_at
                FROM world_snapshots_v2 ORDER BY revision
                """
            ).fetchall()
            if snapshot_rows:
                pinned.add(str(snapshot_rows[-1]["snapshot_id"]))
            doomed = tuple(
                str(row["snapshot_id"])
                for row in snapshot_rows
                if str(row["snapshot_id"]) not in pinned
                and _as_utc(str(row["observed_at"])) < cutoff
            )
            if doomed:
                cursor = self.connection.executemany(
                    "DELETE FROM world_snapshots_v2 WHERE snapshot_id=?",
                    ((snapshot_id,) for snapshot_id in doomed),
                )
                rows_deleted["world_snapshots_v2"] = cursor.rowcount

            retained_rows = self.connection.execute(
                """
                SELECT snapshot_id,body_json FROM world_snapshots_v2
                ORDER BY revision
                """
            ).fetchall()
            minimum_revisions: dict[str, int] = {}
            reference_pairs: set[tuple[str, int]] = set()
            for row in retained_rows:
                body = _decode_world_snapshot_body(row["body_json"])
                target_revisions = body.get("target_revisions", {})
                if not isinstance(target_revisions, Mapping):
                    raise ValueError(
                        "retained world snapshot has invalid target_revisions: "
                        f"{row['snapshot_id']}"
                    )
                is_reference = "entities" not in body
                for target_id_value, revision_value in target_revisions.items():
                    target_id = str(target_id_value)
                    revision = int(revision_value)
                    current = minimum_revisions.get(target_id)
                    minimum_revisions[target_id] = (
                        revision if current is None else min(current, revision)
                    )
                    if is_reference:
                        reference_pairs.add((target_id, revision))

            for target_id, minimum_revision in minimum_revisions.items():
                cursor = self.connection.execute(
                    """
                    DELETE FROM target_observations_v2
                    WHERE target_id=? AND revision<?
                    """,
                    (target_id, minimum_revision),
                )
                rows_deleted["target_observations_v2"] += cursor.rowcount

            for target_id, revision in sorted(reference_pairs):
                minimum_revision = minimum_revisions[target_id]
                if revision < minimum_revision:
                    raise AssertionError(
                        "retention minimum revision exceeds a retained reference"
                    )
                exists = self.connection.execute(
                    """
                    SELECT 1 FROM target_observations_v2
                    WHERE target_id=? AND revision=?
                    """,
                    (target_id, revision),
                ).fetchone()
                if exists is None:
                    raise AssertionError(
                        "retention left a dangling target reference: "
                        f"{target_id}@{revision}"
                    )

            self._increment_retention_counter("prune_runs")
            self._increment_retention_counter(
                "world_snapshots_pruned",
                rows_deleted["world_snapshots_v2"],
            )
            self._increment_retention_counter(
                "target_observations_pruned",
                rows_deleted["target_observations_v2"],
            )
        return PruneSummary(
            boundary=boundary_at.isoformat(),
            cutoff=cutoff.isoformat(),
            pinned_snapshot_ids=tuple(sorted(pinned)),
            retained_snapshots=len(retained_rows),
            rows_deleted=rows_deleted,
        )

    def vacuum(self) -> None:
        if self.connection.in_transaction:
            raise RuntimeError("cannot vacuum while a transaction is active")
        self.connection.execute("VACUUM")

    def _increment_retention_counter(self, name: str, amount: int = 1) -> None:
        if name not in _RETENTION_COUNTER_NAMES:
            raise ValueError(f"unknown retention counter: {name}")
        self.connection.execute(
            "UPDATE retention_counters_v1 SET value=value+? WHERE name=?",
            (amount, name),
        )

    def create_goal(self, goal: GoalSpecV2) -> None:
        if self.has_goal(goal.id):
            raise ValueError(f"goal already exists: {goal.id}")
        self._insert_goal(goal)
        self.append_event(goal.id, "goal_created", "heart.v2", goal.to_dict())

    def has_goal(self, goal_id: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM goal_specs_v2 WHERE id=? AND current=1", (goal_id,)
        ).fetchone() is not None

    def get_goal(self, goal_id: str) -> GoalSpecV2:
        row = self.connection.execute(
            "SELECT body_json FROM goal_specs_v2 WHERE id=? AND current=1",
            (goal_id,),
        ).fetchone()
        if row is None:
            raise KeyError(goal_id)
        return GoalSpecV2.from_dict(json.loads(row["body_json"]))

    def save_goal_version(self, goal: GoalSpecV2) -> None:
        current = self.get_goal(goal.id)
        if goal.version != current.version + 1:
            raise ValueError("goal version must advance exactly once")
        self.connection.execute(
            "UPDATE goal_specs_v2 SET current=0 WHERE id=?", (goal.id,)
        )
        self.connection.execute("DELETE FROM plan_cache_v2 WHERE goal_id=?", (goal.id,))
        self._insert_goal(goal, commit=False)
        self.connection.commit()
        self.append_event(goal.id, "goal_versioned", "heart.v2", {
            "previous_version": current.version,
            "version": goal.version,
        })

    def set_goal_status(self, goal_id: str, status: str) -> GoalSpecV2:
        goal = replace(self.get_goal(goal_id), status=status)
        self.connection.execute(
            "UPDATE goal_specs_v2 SET body_json=?, status=? WHERE id=? AND current=1",
            (canonical_json(goal), status, goal_id),
        )
        self.connection.commit()
        return goal

    def live_goals(self) -> tuple[GoalSpecV2, ...]:
        rows = self.connection.execute(
            """
            SELECT body_json FROM goal_specs_v2
            WHERE current=1 AND status IN
                ('active','monitoring','waiting','uncertain','degraded')
            ORDER BY json_extract(body_json, '$.priority') DESC, created_at ASC
            """
        ).fetchall()
        return tuple(GoalSpecV2.from_dict(json.loads(row["body_json"])) for row in rows)

    def save_mandate(self, mandate: StandingMandateV1) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO mandates_v1(id, body_json) VALUES(?,?)",
            (mandate.id, canonical_json(mandate)),
        )
        self.connection.commit()

    def get_mandate(self, mandate_id: str) -> StandingMandateV1:
        row = self.connection.execute(
            "SELECT body_json FROM mandates_v1 WHERE id=?", (mandate_id,)
        ).fetchone()
        if row is None:
            raise KeyError(mandate_id)
        return StandingMandateV1.from_dict(json.loads(row["body_json"]))

    def mandates(self) -> tuple[StandingMandateV1, ...]:
        rows = self.connection.execute(
            "SELECT body_json FROM mandates_v1 ORDER BY created_at,id"
        ).fetchall()
        return tuple(
            StandingMandateV1.from_dict(json.loads(row["body_json"])) for row in rows
        )

    def save_routine(self, routine: RoutineSpecV1) -> None:
        existing = self.connection.execute(
            "SELECT 1 FROM routine_specs_v1 WHERE id=?", (routine.id,)
        ).fetchone()
        self.connection.execute(
            """
            INSERT INTO routine_specs_v1(
                id,goal_id,template_id,plugin_id,target_id,body_json
            ) VALUES(?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                goal_id=excluded.goal_id,
                template_id=excluded.template_id,
                plugin_id=excluded.plugin_id,
                target_id=excluded.target_id,
                body_json=excluded.body_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                routine.id, routine.goal_id, routine.template_id,
                routine.plugin_id, routine.target_id, canonical_json(routine),
            ),
        )
        if existing is None:
            self._insert_event(
                routine.goal_id,
                "routine_created",
                routine.plugin_id,
                {
                    "routine_id": routine.id,
                    "template_id": routine.template_id,
                    "target_id": routine.target_id,
                    "entity_count": len(routine.entity_ids),
                },
            )
        self.connection.commit()

    def get_routine(self, routine_id: str) -> RoutineSpecV1:
        row = self.connection.execute(
            "SELECT body_json FROM routine_specs_v1 WHERE id=?", (routine_id,)
        ).fetchone()
        if row is None:
            raise KeyError(routine_id)
        return RoutineSpecV1.from_dict(json.loads(row["body_json"]))

    def routine_for_goal(self, goal_id: str) -> RoutineSpecV1 | None:
        row = self.connection.execute(
            "SELECT body_json FROM routine_specs_v1 WHERE goal_id=?", (goal_id,)
        ).fetchone()
        return RoutineSpecV1.from_dict(json.loads(row["body_json"])) if row else None

    def routines(
        self, *, statuses: tuple[str, ...] | None = None
    ) -> tuple[RoutineSpecV1, ...]:
        parameters: tuple[str, ...] = ()
        where = ""
        if statuses:
            marks = ",".join("?" for _ in statuses)
            where = f" WHERE json_extract(body_json, '$.status') IN ({marks})"
            parameters = statuses
        rows = self.connection.execute(
            "SELECT body_json FROM routine_specs_v1" + where + " ORDER BY created_at,id",
            parameters,
        ).fetchall()
        return tuple(
            RoutineSpecV1.from_dict(json.loads(row["body_json"])) for row in rows
        )

    def save_routine_candidate(self, candidate: RoutineCandidateV1) -> None:
        existing = self.connection.execute(
            "SELECT body_json FROM routine_candidates_v1 WHERE id=?",
            (candidate.id,),
        ).fetchone()
        previous_status = (
            str(json.loads(existing["body_json"]).get("status", ""))
            if existing is not None
            else None
        )
        self.connection.execute(
            """
            INSERT INTO routine_candidates_v1(
                id,template_id,plugin_id,target_id,body_json
            ) VALUES(?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                body_json=excluded.body_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                candidate.id, candidate.template_id, candidate.plugin_id,
                candidate.target_id, canonical_json(candidate),
            ),
        )
        if existing is None:
            self._insert_event(
                None,
                "routine_candidate_created",
                candidate.plugin_id,
                {
                    "candidate_id": candidate.id,
                    "template_id": candidate.template_id,
                    "target_id": candidate.target_id,
                    "example_count": candidate.example_count,
                    "status": candidate.status.value,
                },
            )
        elif (
            candidate.status is RoutineCandidateStatus.READY_FOR_APPROVAL
            and previous_status != candidate.status.value
        ):
            self._insert_event(
                None,
                "routine_candidate_ready",
                candidate.plugin_id,
                {
                    "candidate_id": candidate.id,
                    "template_id": candidate.template_id,
                    "target_id": candidate.target_id,
                    "example_count": candidate.example_count,
                    "status": candidate.status.value,
                },
            )
        self.connection.commit()

    def get_routine_candidate(self, candidate_id: str) -> RoutineCandidateV1:
        row = self.connection.execute(
            "SELECT body_json FROM routine_candidates_v1 WHERE id=?", (candidate_id,)
        ).fetchone()
        if row is None:
            raise KeyError(candidate_id)
        return RoutineCandidateV1.from_dict(json.loads(row["body_json"]))

    def routine_candidates(
        self,
        *,
        statuses: tuple[str, ...] | None = None,
        template_id: str | None = None,
    ) -> tuple[RoutineCandidateV1, ...]:
        clauses: list[str] = []
        parameters: list[str] = []
        if statuses:
            marks = ",".join("?" for _ in statuses)
            clauses.append(f"json_extract(body_json, '$.status') IN ({marks})")
            parameters.extend(statuses)
        if template_id is not None:
            clauses.append("template_id=?")
            parameters.append(template_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.connection.execute(
            "SELECT body_json FROM routine_candidates_v1" + where + " ORDER BY created_at,id",
            tuple(parameters),
        ).fetchall()
        return tuple(
            RoutineCandidateV1.from_dict(json.loads(row["body_json"])) for row in rows
        )

    def save_shadow_event(self, event: RoutineShadowEventV1) -> None:
        self.connection.execute(
            """
            INSERT INTO routine_shadow_events_v1(
                id,candidate_id,opportunity_key,body_json
            ) VALUES(?,?,?,?)
            ON CONFLICT(candidate_id,opportunity_key) DO UPDATE SET
                body_json=excluded.body_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (event.id, event.candidate_id, event.opportunity_key, canonical_json(event)),
        )
        self.connection.commit()

    def shadow_events(self, candidate_id: str) -> tuple[RoutineShadowEventV1, ...]:
        rows = self.connection.execute(
            """
            SELECT body_json FROM routine_shadow_events_v1
            WHERE candidate_id=? ORDER BY created_at,id
            """,
            (candidate_id,),
        ).fetchall()
        return tuple(
            RoutineShadowEventV1.from_dict(json.loads(row["body_json"])) for row in rows
        )

    def autonomy_mode(self) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT mode,epoch,changed_at,changed_by FROM autonomy_mode_v1 WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise RuntimeError("autonomy mode state is missing")
        return {
            "mode": AutonomyModeV1(str(row["mode"])),
            "epoch": int(row["epoch"]),
            "changed_at": str(row["changed_at"]),
            "changed_by": str(row["changed_by"]),
        }

    def set_autonomy_mode(
        self, mode: AutonomyModeV1, *, changed_at: str, changed_by: str
    ) -> dict[str, Any]:
        with self.connection:
            row = self.connection.execute(
                "SELECT mode,epoch FROM autonomy_mode_v1 WHERE singleton=1"
            ).fetchone()
            if row is None:
                raise RuntimeError("autonomy mode state is missing")
            epoch = int(row["epoch"])
            if str(row["mode"]) != mode.value:
                epoch += 1
            self.connection.execute(
                "UPDATE autonomy_mode_v1 SET mode=?,epoch=?,changed_at=?,changed_by=? WHERE singleton=1",
                (mode.value, epoch, changed_at, changed_by),
            )
            self._insert_event(
                None, "autonomy_mode_changed", changed_by,
                {"mode": mode.value, "epoch": epoch},
            )
        return self.autonomy_mode()

    def save_autonomy_enrollment(
        self,
        enrollment: AutonomyEnrollmentV2,
        *,
        resource_keys: tuple[tuple[str, str, str], ...],
    ) -> None:
        resources = set(resource_keys)
        if enrollment.enabled and not resources:
            raise ValueError("enabled autonomy enrollment requires resources")
        if any(not all(item) for item in resources):
            raise ValueError("autonomy enrollment resources must be exact")
        try:
            with self.connection:
                current = self.connection.execute(
                    "SELECT revision FROM autonomy_enrollments_v2 WHERE id=? AND current=1",
                    (enrollment.id,),
                ).fetchone()
                if current is not None:
                    if enrollment.revision != int(current["revision"]) + 1:
                        raise ValueError("enrollment updates require the next revision")
                    self.connection.execute(
                        "UPDATE autonomy_enrollments_v2 SET current=0 WHERE id=? AND current=1",
                        (enrollment.id,),
                    )
                    self.connection.execute(
                        "DELETE FROM autonomy_enrollment_resources_v1 WHERE enrollment_id=?",
                        (enrollment.id,),
                    )
                elif enrollment.revision != 1:
                    raise ValueError("new autonomy enrollment must start at revision one")
                self.connection.execute(
                    """
                    INSERT INTO autonomy_enrollments_v2(
                        id,revision,plugin_id,strategy_id,enabled,current,body_json
                    ) VALUES(?,?,?,?,?,1,?)
                    """,
                    (
                        enrollment.id, enrollment.revision, enrollment.plugin_id,
                        enrollment.strategy_id, int(enrollment.enabled),
                        canonical_json(enrollment),
                    ),
                )
                if enrollment.enabled:
                    self.connection.executemany(
                        """
                        INSERT INTO autonomy_enrollment_resources_v1(
                            enrollment_id,enrollment_revision,target_id,entity_id,conflict_domain
                        ) VALUES(?,?,?,?,?)
                        """,
                        (
                            (enrollment.id, enrollment.revision, *resource)
                            for resource in sorted(resources)
                        ),
                    )
                self._insert_event(
                    None, "autonomy_enrollment_saved", enrollment.enrolled_by,
                    {
                        "enrollment_id": enrollment.id,
                        "revision": enrollment.revision,
                        "plugin_id": enrollment.plugin_id,
                        "enabled": enrollment.enabled,
                        "resource_count": len(resources),
                    },
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "autonomy enrollment overlaps an active target/entity/conflict_domain"
            ) from exc

    def autonomy_enrollments(
        self, *, enabled_only: bool = False, include_history: bool = False
    ) -> tuple[AutonomyEnrollmentV2, ...]:
        clauses = [] if include_history else ["current=1"]
        if enabled_only:
            clauses.append("enabled=1")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.connection.execute(
            "SELECT body_json FROM autonomy_enrollments_v2" + where + " ORDER BY id,revision"
        ).fetchall()
        return tuple(
            AutonomyEnrollmentV2.from_dict(json.loads(row["body_json"]))
            for row in rows
        )

    def get_autonomy_enrollment(
        self, enrollment_id: str, revision: int | None = None
    ) -> AutonomyEnrollmentV2:
        if revision is None:
            row = self.connection.execute(
                "SELECT body_json FROM autonomy_enrollments_v2 WHERE id=? AND current=1",
                (enrollment_id,),
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT body_json FROM autonomy_enrollments_v2 WHERE id=? AND revision=?",
                (enrollment_id, revision),
            ).fetchone()
        if row is None:
            raise KeyError(enrollment_id)
        return AutonomyEnrollmentV2.from_dict(json.loads(row["body_json"]))

    def disable_autonomy_enrollment(
        self, enrollment_id: str, *, revoked_at: str
    ) -> AutonomyEnrollmentV2:
        current = self.get_autonomy_enrollment(enrollment_id)
        if not current.enabled:
            return current
        disabled = replace(
            current, revision=current.revision + 1,
            enabled=False, revoked_at=revoked_at,
        )
        self.save_autonomy_enrollment(disabled, resource_keys=())
        return disabled

    def expire_autonomy_enrollments(
        self, *, boundary: str
    ) -> tuple[AutonomyEnrollmentV2, ...]:
        now = _as_utc(boundary)
        expired = tuple(
            item
            for item in self.autonomy_enrollments(enabled_only=True)
            if _as_utc(item.expires_at) <= now
        )
        return tuple(
            self.disable_autonomy_enrollment(item.id, revoked_at=boundary)
            for item in expired
        )

    def save_autonomy_evaluation(self, evaluation: AutonomyEvaluationV1) -> None:
        self.connection.execute(
            """
            INSERT INTO autonomy_evaluations_v1(
                id,enrollment_id,enrollment_revision,body_json
            ) VALUES(?,?,?,?)
            """,
            (
                evaluation.id, evaluation.enrollment_id,
                evaluation.enrollment_revision, canonical_json(evaluation),
            ),
        )
        self.connection.commit()

    def autonomy_evaluations(
        self, enrollment_id: str | None = None
    ) -> tuple[AutonomyEvaluationV1, ...]:
        if enrollment_id is None:
            rows = self.connection.execute(
                "SELECT body_json FROM autonomy_evaluations_v1 ORDER BY rowid"
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT body_json FROM autonomy_evaluations_v1 WHERE enrollment_id=? ORDER BY rowid",
                (enrollment_id,),
            ).fetchall()
        return tuple(
            AutonomyEvaluationV1.from_dict(json.loads(row["body_json"])) for row in rows
        )

    def get_autonomy_evaluation(self, evaluation_id: str) -> AutonomyEvaluationV1:
        row = self.connection.execute(
            "SELECT body_json FROM autonomy_evaluations_v1 WHERE id=?", (evaluation_id,)
        ).fetchone()
        if row is None:
            raise KeyError(evaluation_id)
        return AutonomyEvaluationV1.from_dict(json.loads(row["body_json"]))

    def save_autonomy_binding(
        self,
        binding: AutonomyBindingV1,
        decision: AutonomyDecisionV1,
        *,
        status: AutonomyBindingStatusV1,
        proposal_id: str | None = None,
        reason: str = "",
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO autonomy_bindings_v1(
                evaluation_id,enrollment_id,status,proposal_id,decision_json,
                binding_json,reason
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                binding.evaluation_id, binding.enrollment_id, status.value,
                proposal_id, canonical_json(decision), canonical_json(binding), reason,
            ),
        )
        self.connection.commit()

    def autonomy_bindings(
        self, *, statuses: tuple[AutonomyBindingStatusV1, ...] = ()
    ) -> tuple[dict[str, Any], ...]:
        parameters = tuple(item.value for item in statuses)
        where = ""
        if parameters:
            where = " WHERE status IN (" + ",".join("?" for _ in parameters) + ")"
        rows = self.connection.execute(
            """
            SELECT status,proposal_id,decision_json,binding_json,reason,
                   created_at,updated_at FROM autonomy_bindings_v1
            """ + where + " ORDER BY rowid",
            parameters,
        ).fetchall()
        return tuple(self._autonomy_binding_row(row) for row in rows)

    def get_autonomy_binding(self, evaluation_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT status,proposal_id,decision_json,binding_json,reason,
                   created_at,updated_at FROM autonomy_bindings_v1
            WHERE evaluation_id=?
            """,
            (evaluation_id,),
        ).fetchone()
        if row is None:
            raise KeyError(evaluation_id)
        return self._autonomy_binding_row(row)

    def set_autonomy_binding_status(
        self, evaluation_id: str, status: AutonomyBindingStatusV1, *, reason: str = ""
    ) -> dict[str, Any]:
        cursor = self.connection.execute(
            """
            UPDATE autonomy_bindings_v1
            SET status=?,reason=?,updated_at=CURRENT_TIMESTAMP WHERE evaluation_id=?
            """,
            (status.value, reason, evaluation_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(evaluation_id)
        self.connection.commit()
        return self.get_autonomy_binding(evaluation_id)

    def set_autonomy_binding_proposal(
        self, evaluation_id: str, proposal_id: str
    ) -> None:
        cursor = self.connection.execute(
            """
            UPDATE autonomy_bindings_v1
            SET proposal_id=?,updated_at=CURRENT_TIMESTAMP WHERE evaluation_id=?
            """,
            (proposal_id, evaluation_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(evaluation_id)
        self.connection.commit()

    @staticmethod
    def _autonomy_binding_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "status": AutonomyBindingStatusV1(str(row["status"])),
            "proposal_id": str(row["proposal_id"]) if row["proposal_id"] is not None else None,
            "decision": AutonomyDecisionV1.from_dict(json.loads(row["decision_json"])),
            "binding": AutonomyBindingV1.from_dict(json.loads(row["binding_json"])),
            "reason": str(row["reason"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def save_suggestion(self, suggestion: SuggestionV1) -> None:
        self.connection.execute(
            "INSERT INTO suggestions_v1(id,body_json) VALUES(?,?)",
            (suggestion.id, canonical_json(suggestion)),
        )
        self.connection.commit()

    def suggestions(self) -> tuple[SuggestionV1, ...]:
        rows = self.connection.execute(
            "SELECT body_json FROM suggestions_v1 ORDER BY rowid"
        ).fetchall()
        return tuple(SuggestionV1.from_dict(json.loads(row["body_json"])) for row in rows)

    def save_dispatch_attempt(self, attempt: DispatchAttemptV1) -> None:
        self.connection.execute(
            """
            INSERT INTO dispatch_attempts_v1(
                id,operation_key,request_id,target_id,entity_id,conflict_domain,
                state,body_json
            ) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET state=excluded.state,
                body_json=excluded.body_json,updated_at=CURRENT_TIMESTAMP
            """,
            (
                attempt.id, attempt.operation_key, attempt.request_id,
                attempt.target_id, attempt.entity_id, attempt.conflict_domain,
                attempt.state.value, canonical_json(attempt),
            ),
        )
        self.connection.commit()

    def dispatch_attempt_for_operation(
        self, operation_key: str
    ) -> DispatchAttemptV1 | None:
        row = self.connection.execute(
            "SELECT body_json FROM dispatch_attempts_v1 WHERE operation_key=?",
            (operation_key,),
        ).fetchone()
        return DispatchAttemptV1.from_dict(json.loads(row["body_json"])) if row else None

    def dispatch_attempt_for_request(self, request_id: str) -> DispatchAttemptV1 | None:
        row = self.connection.execute(
            "SELECT body_json FROM dispatch_attempts_v1 WHERE request_id=? ORDER BY rowid DESC LIMIT 1",
            (request_id,),
        ).fetchone()
        return DispatchAttemptV1.from_dict(json.loads(row["body_json"])) if row else None

    def dispatch_attempts(self, *, open_only: bool = False) -> tuple[DispatchAttemptV1, ...]:
        where = ""
        parameters: tuple[str, ...] = ()
        if open_only:
            where = " WHERE state IN (?,?,?)"
            parameters = _OPEN_DISPATCH_STATES
        rows = self.connection.execute(
            "SELECT body_json FROM dispatch_attempts_v1" + where + " ORDER BY rowid",
            parameters,
        ).fetchall()
        return tuple(
            DispatchAttemptV1.from_dict(json.loads(row["body_json"])) for row in rows
        )

    def save_autonomy_profile(self, profile: AutonomyProfileV1) -> None:
        existing_row = self.connection.execute(
            "SELECT body_json FROM autonomy_profiles_v1 WHERE id=?",
            (profile.id,),
        ).fetchone()
        if existing_row is not None:
            existing = AutonomyProfileV1.from_dict(
                json.loads(existing_row["body_json"])
            )
            if existing != profile:
                raise ValueError(
                    "autonomy profiles are immutable; disable and enroll a new profile"
                )
            return
        active = self.active_autonomy_profile(profile.plugin_id, profile.target_id)
        if profile.enabled and active is not None:
            raise ValueError(
                "an active autonomy profile already exists for this plugin/target"
            )
        self.connection.execute(
            """
            INSERT INTO autonomy_profiles_v1(id,plugin_id,target_id,body_json)
            VALUES(?,?,?,?)
            """,
            (profile.id, profile.plugin_id, profile.target_id, canonical_json(profile)),
        )
        self.connection.commit()

    def autonomy_profiles(self, *, enabled_only: bool = False) -> tuple[AutonomyProfileV1, ...]:
        where = " WHERE json_extract(body_json, '$.enabled') = 1" if enabled_only else ""
        rows = self.connection.execute(
            "SELECT body_json FROM autonomy_profiles_v1" + where + " ORDER BY created_at,id"
        ).fetchall()
        return tuple(
            AutonomyProfileV1.from_dict(json.loads(row["body_json"])) for row in rows
        )

    def active_autonomy_profile(
        self, plugin_id: str, target_id: str
    ) -> AutonomyProfileV1 | None:
        row = self.connection.execute(
            """
            SELECT body_json FROM autonomy_profiles_v1
            WHERE plugin_id=? AND target_id=?
              AND json_extract(body_json, '$.enabled') = 1
            ORDER BY updated_at DESC LIMIT 1
            """,
            (plugin_id, target_id),
        ).fetchone()
        return AutonomyProfileV1.from_dict(json.loads(row["body_json"])) if row else None

    def disable_autonomy_profile(self, profile_id: str, *, revoked_at: str) -> AutonomyProfileV1:
        profile = next(
            (item for item in self.autonomy_profiles() if item.id == profile_id),
            None,
        )
        if profile is None:
            raise KeyError(profile_id)
        disabled = replace(
            profile, enabled=False, revoked_at=revoked_at
        )
        with self.connection:
            self.connection.execute(
                "UPDATE autonomy_profiles_v1 SET body_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (canonical_json(disabled), profile.id),
            )
            routines = self.routines()
            for routine in routines:
                if routine.profile_id != profile.id:
                    continue
                suspended = replace(
                    routine,
                    status=RoutineStatus.SUSPENDED,
                    status_reason="autonomy profile was disabled",
                )
                self.connection.execute(
                    "UPDATE routine_specs_v1 SET body_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (canonical_json(suspended), routine.id),
                )
                goal = self.get_goal(routine.goal_id)
                if goal.mandate_id is None:
                    continue
                try:
                    mandate = self.get_mandate(goal.mandate_id)
                except KeyError:
                    continue
                self.connection.execute(
                    "UPDATE mandates_v1 SET body_json=? WHERE id=?",
                    (canonical_json(replace(mandate, revoked=True)), mandate.id),
                )
            self.connection.execute(
                "INSERT INTO world_events_v2(goal_id,kind,source,payload_json) VALUES(NULL,?,?,?)",
                (
                    "autonomy_profile_disabled",
                    "engine.routines/v1",
                    canonical_json({"profile_id": profile.id}),
                ),
            )
        return disabled

    def activate_routine(
        self,
        candidate: RoutineCandidateV1,
        routine: RoutineSpecV1,
        goal: GoalSpecV2,
        mandate: StandingMandateV1,
    ) -> None:
        """Atomically install the exact routine, goal and submandate."""
        if routine.goal_id != goal.id or goal.mandate_id != mandate.id:
            raise ValueError("routine activation identities do not match")
        if self.has_goal(goal.id):
            raise ValueError(f"goal already exists: {goal.id}")
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO mandates_v1(id,body_json) VALUES(?,?)",
                (mandate.id, canonical_json(mandate)),
            )
            self._insert_goal(goal, commit=False)
            self.connection.execute(
                """
                INSERT INTO routine_specs_v1(
                    id,goal_id,template_id,plugin_id,target_id,body_json
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    routine.id, routine.goal_id, routine.template_id,
                    routine.plugin_id, routine.target_id, canonical_json(routine),
                ),
            )
            self.connection.execute(
                """
                UPDATE routine_candidates_v1 SET body_json=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (canonical_json(candidate), candidate.id),
            )
            self.connection.execute(
                """
                INSERT INTO world_events_v2(goal_id,kind,source,payload_json)
                VALUES(?,?,?,?)
                """,
                (
                    goal.id, "routine_activated", "engine.routines/v1",
                    canonical_json({
                        "routine_id": routine.id,
                        "candidate_id": candidate.id,
                        "mandate_id": mandate.id,
                    }),
                ),
            )

    def rollback_active_routine(
        self,
        routine: RoutineSpecV1,
        candidate: RoutineCandidateV1 | None,
        mandate: StandingMandateV1 | None,
        *,
        reason: str,
    ) -> None:
        rolled = replace(routine, status=RoutineStatus.ROLLED_BACK, status_reason=reason)
        with self.connection:
            self.connection.execute(
                "UPDATE routine_specs_v1 SET body_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (canonical_json(rolled), routine.id),
            )
            goal = self.get_goal(routine.goal_id)
            stopped = replace(goal, status="abandoned")
            self.connection.execute(
                "UPDATE goal_specs_v2 SET body_json=?,status='abandoned' WHERE id=? AND current=1",
                (canonical_json(stopped), goal.id),
            )
            self.connection.execute("DELETE FROM plan_cache_v2 WHERE goal_id=?", (goal.id,))
            if mandate is not None:
                self.connection.execute(
                    "UPDATE mandates_v1 SET body_json=? WHERE id=?",
                    (canonical_json(replace(mandate, revoked=True)), mandate.id),
                )
            if candidate is not None:
                self.connection.execute(
                    "UPDATE routine_candidates_v1 SET body_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (
                        canonical_json(replace(candidate, status=RoutineCandidateStatus.ROLLED_BACK)),
                        candidate.id,
                    ),
                )
            self.connection.execute(
                "INSERT INTO world_events_v2(goal_id,kind,source,payload_json) VALUES(?,?,?,?)",
                (goal.id, "routine_rolled_back", "engine.routines/v1", canonical_json({"routine_id": routine.id, "reason": reason})),
            )

    def occurrence_exists(self, routine_id: str, occurrence_key: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM routine_occurrences_v1 WHERE routine_id=? AND occurrence_key=?",
            (routine_id, occurrence_key),
        ).fetchone() is not None

    def record_occurrence(
        self, routine_id: str, occurrence_key: str, observed_at: str,
        result: Mapping[str, Any],
    ) -> bool:
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO routine_occurrences_v1(
                routine_id,occurrence_key,observed_at,result_json
            ) VALUES(?,?,?,?)
            """,
            (routine_id, occurrence_key, observed_at, canonical_json(result)),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def record_routine_action(
        self, routine_id: str, entity_id: str, request_id: str | None,
        acted_at: str, result: Mapping[str, Any],
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO routine_actions_v1(
                routine_id,entity_id,request_id,acted_at,result_json
            ) VALUES(?,?,?,?,?)
            """,
            (routine_id, entity_id, request_id, acted_at, canonical_json(result)),
        )
        self.connection.commit()

    def routine_action_count(
        self, *, since: str, entity_id: str | None = None
    ) -> int:
        if entity_id is None:
            row = self.connection.execute(
                "SELECT COUNT(*) AS value FROM routine_actions_v1 WHERE acted_at>=?",
                (since,),
            ).fetchone()
        else:
            row = self.connection.execute(
                """
                SELECT COUNT(*) AS value FROM routine_actions_v1
                WHERE acted_at>=? AND entity_id=?
                """,
                (since, entity_id),
            ).fetchone()
        return int(row["value"])

    def save_target_observation(self, observation: TargetObservationV2) -> bool:
        body = _encode_target_observation_body(observation)
        digest = artifact_sha256(observation)
        semantic_digest = observation.semantic_fingerprint()
        confirmed_at = observation.confirmed_at or observation.observed_at
        latest = self.connection.execute(
            """
            SELECT revision, semantic_sha256, body_json
            FROM target_observations_v2
            WHERE target_id=? ORDER BY revision DESC LIMIT 1
            """,
            (observation.target_id,),
        ).fetchone()
        if latest is not None and observation.revision == int(latest["revision"]):
            stored_semantic = latest["semantic_sha256"]
            if stored_semantic is None:
                stored_semantic = _target_observation(
                    _decode_target_observation_body(latest["body_json"])
                ).semantic_fingerprint()
            if stored_semantic != semantic_digest:
                raise ValueError("same target revision cannot describe different state")
            self.connection.execute(
                """
                UPDATE target_observations_v2 SET confirmed_at=?
                WHERE target_id=? AND revision=?
                """,
                (confirmed_at, observation.target_id, observation.revision),
            )
            self._increment_retention_counter(
                "target_observation_deduplications"
            )
            self.connection.commit()
            return False
        if latest is not None and observation.revision <= int(latest["revision"]):
            raise ValueError("target revision must be monotone")
        self.connection.execute(
            """
            INSERT INTO target_observations_v2(
                target_id, revision, body_json, artifact_sha256, semantic_sha256,
                observed_at, confirmed_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                observation.target_id,
                observation.revision,
                body,
                digest,
                semantic_digest,
                observation.observed_at,
                confirmed_at,
            ),
        )
        self._increment_retention_counter("target_observation_rows_written")
        self.connection.commit()
        return True

    def latest_target_observation(self, target_id: str) -> TargetObservationV2 | None:
        row = self.connection.execute(
            """
            SELECT body_json, confirmed_at FROM target_observations_v2
            WHERE target_id=? ORDER BY revision DESC LIMIT 1
            """,
            (target_id,),
        ).fetchone()
        if row is None:
            return None
        observation = _target_observation(
            _decode_target_observation_body(row["body_json"])
        )
        return replace(
            observation,
            confirmed_at=(
                str(row["confirmed_at"])
                if row["confirmed_at"] is not None
                else observation.observed_at
            ),
        )

    def save_world_snapshot(self, snapshot: WorldSnapshotV2) -> None:
        expected = self.next_world_revision()
        if snapshot.revision != expected:
            raise ValueError(f"world revision must be {expected}")
        reference = {
            "revision": snapshot.revision,
            "snapshot_id": snapshot.id,
            "observed_at": snapshot.observed_at,
            "target_revisions": snapshot.target_revisions,
            "coverage": snapshot.coverage,
        }
        reconstructed = _reconstruct_world_snapshot(self.connection, reference)
        if reconstructed.sha256 != snapshot.sha256:
            raise ValueError(
                f"world snapshot is not reconstructible: {snapshot.id}"
            )
        self.connection.execute(
            """
            INSERT INTO world_snapshots_v2(
                revision, snapshot_id, body_json, artifact_sha256, observed_at
            ) VALUES(?,?,?,?,?)
            """,
            (
                snapshot.revision,
                snapshot.id,
                canonical_json(reference),
                snapshot.sha256,
                snapshot.observed_at,
            ),
        )
        self.connection.commit()

    def next_world_revision(self) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(revision), 0) AS revision FROM world_snapshots_v2"
        ).fetchone()
        return int(row["revision"]) + 1

    def latest_world_snapshot(self) -> WorldSnapshotV2 | None:
        row = self.connection.execute(
            "SELECT * FROM world_snapshots_v2 ORDER BY revision DESC LIMIT 1"
        ).fetchone()
        return _load_world_snapshot_row(self.connection, row) if row else None

    def world_snapshot(self, snapshot_id: str) -> WorldSnapshotV2:
        row = self.connection.execute(
            "SELECT * FROM world_snapshots_v2 WHERE snapshot_id=?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        return _load_world_snapshot_row(self.connection, row)

    def save_proposal(self, value: ProposedActionV1) -> None:
        self.connection.execute(
            "INSERT INTO proposed_actions_v1(id, goal_id, body_json) VALUES(?,?,?)",
            (value.id, value.goal_id, canonical_json(value)),
        )
        self._insert_event(
            value.goal_id,
            "proposal_created",
            value.proposed_by,
            {
                "proposal_id": value.id,
                "proposed_by": value.proposed_by,
                "capability_family": value.capability_family,
                "target_id": value.target_id,
                "entity_id": value.entity_id,
            },
        )
        self.connection.commit()

    def save_request(self, value: ActionRequestV1) -> None:
        self._save_lifecycle("action_requests_v1", value.id, value.proposal_id, value)

    def save_policy_decision(self, value: PolicyDecisionV1) -> None:
        self._save_lifecycle("policy_decisions_v1", value.id, value.request_id, value)

    def save_authorization(self, value: AuthorizationV1) -> None:
        self._save_lifecycle("authorizations_v1", value.id, value.request_id, value)

    def save_receipt(self, value: ExecutionReceiptV2) -> None:
        self._save_lifecycle("execution_receipts_v2", value.id, value.request_id, value)

    def save_effect(self, value: EffectDeltaV1) -> None:
        self._save_lifecycle("effect_deltas_v1", value.id, value.request_id, value)

    def pending_task(self, goal_id: str) -> dict[str, Any] | None:
        """Return the latest durable nonterminal task lifecycle for a goal."""
        row = self.connection.execute(
            """
            SELECT
                proposal.body_json AS proposal_json,
                request.body_json AS request_json,
                authorization.body_json AS authorization_json,
                receipt.body_json AS receipt_json
            FROM proposed_actions_v1 AS proposal
            JOIN action_requests_v1 AS request
              ON request.proposal_id = proposal.id
            JOIN authorizations_v1 AS authorization
              ON authorization.request_id = request.id
            JOIN execution_receipts_v2 AS receipt
              ON receipt.request_id = request.id
            WHERE proposal.goal_id = ?
              AND json_extract(request.body_json, '$.invocation_mode') = 'task'
              AND json_extract(receipt.body_json, '$.state') IN ('accepted','running')
              AND receipt.rowid = (
                  SELECT MAX(latest.rowid)
                  FROM execution_receipts_v2 AS latest
                  WHERE latest.request_id = request.id
              )
            ORDER BY receipt.rowid DESC
            LIMIT 1
            """,
            (goal_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "proposal": ProposedActionV1.from_dict(json.loads(row["proposal_json"])),
            "request": ActionRequestV1.from_dict(json.loads(row["request_json"])),
            "authorization": AuthorizationV1.from_dict(
                json.loads(row["authorization_json"])
            ),
            "receipt": ExecutionReceiptV2.from_dict(json.loads(row["receipt_json"])),
        }

    def lifecycle_counts(self, goal_id: str) -> dict[str, int]:
        proposal_ids = tuple(
            row["id"] for row in self.connection.execute(
                "SELECT id FROM proposed_actions_v1 WHERE goal_id=?", (goal_id,)
            ).fetchall()
        )
        if not proposal_ids:
            return {name: 0 for name in ("proposals", "requests", "decisions", "authorizations", "receipts", "effects")}
        placeholders = ",".join("?" for _ in proposal_ids)
        request_rows = self.connection.execute(
            f"SELECT id FROM action_requests_v1 WHERE proposal_id IN ({placeholders})",
            proposal_ids,
        ).fetchall()
        request_ids = tuple(row["id"] for row in request_rows)
        def count(table: str, column: str, values: tuple[str, ...]) -> int:
            if not values:
                return 0
            marks = ",".join("?" for _ in values)
            return int(self.connection.execute(
                f"SELECT COUNT(*) AS value FROM {table} WHERE {column} IN ({marks})", values
            ).fetchone()["value"])
        return {
            "proposals": len(proposal_ids),
            "requests": len(request_ids),
            "decisions": count("policy_decisions_v1", "request_id", request_ids),
            "authorizations": count("authorizations_v1", "request_id", request_ids),
            "receipts": count("execution_receipts_v2", "request_id", request_ids),
            "effects": count("effect_deltas_v1", "request_id", request_ids),
        }

    def proposals(self, goal_id: str) -> tuple[ProposedActionV1, ...]:
        rows = self.connection.execute(
            "SELECT body_json FROM proposed_actions_v1 WHERE goal_id=? ORDER BY rowid",
            (goal_id,),
        ).fetchall()
        return tuple(
            ProposedActionV1.from_dict(json.loads(row["body_json"])) for row in rows
        )

    def save_hypothesis(self, value: RelationHypothesisV1) -> None:
        self.connection.execute(
            "INSERT INTO relation_hypotheses_v1(id, body_json) VALUES(?,?)",
            (value.id, canonical_json(value)),
        )
        self.connection.commit()

    def schedule_wake(
        self, wake_id: str, wake_at: str, reason: str, *,
        goal_id: str | None = None, target_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO scheduled_wakes_v2(
                id, goal_id, target_id, wake_at, reason, payload_json, handled
            ) VALUES(?,?,?,?,?,?,0)
            """,
            (wake_id, goal_id, target_id, wake_at, reason, canonical_json(payload or {})),
        )
        self.connection.commit()

    def due_wakes(self, now: str) -> tuple[dict[str, Any], ...]:
        rows = self.connection.execute(
            """
            SELECT id,goal_id,target_id,wake_at,reason,payload_json
            FROM scheduled_wakes_v2
            WHERE handled=0 AND wake_at<=?
            ORDER BY wake_at,id
            """,
            (now,),
        ).fetchall()
        return tuple(
            {
                "id": str(row["id"]),
                "goal_id": row["goal_id"],
                "target_id": row["target_id"],
                "wake_at": str(row["wake_at"]),
                "reason": str(row["reason"]),
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        )

    def mark_wakes_handled(self, wake_ids: tuple[str, ...]) -> None:
        if not wake_ids:
            return
        marks = ",".join("?" for _ in wake_ids)
        self.connection.execute(
            f"UPDATE scheduled_wakes_v2 SET handled=1 WHERE id IN ({marks})",
            wake_ids,
        )
        self.connection.commit()

    def next_wake_at(self) -> str | None:
        row = self.connection.execute(
            "SELECT MIN(wake_at) AS wake_at FROM scheduled_wakes_v2 WHERE handled=0"
        ).fetchone()
        return str(row["wake_at"]) if row and row["wake_at"] is not None else None

    def append_event(
        self, goal_id: str | None, kind: str, source: str, payload: Mapping[str, Any]
    ) -> None:
        self._insert_event(goal_id, kind, source, payload)
        self.connection.commit()

    def _insert_event(
        self, goal_id: str | None, kind: str, source: str, payload: Mapping[str, Any]
    ) -> None:
        self.connection.execute(
            "INSERT INTO world_events_v2(goal_id, kind, source, payload_json) VALUES(?,?,?,?)",
            (goal_id, kind, source, canonical_json(payload)),
        )

    def latest_event_sequence(self) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(id), 0) AS value FROM world_events_v2"
        ).fetchone()
        return int(row["value"])

    def lifecycle_events_after(
        self, sequence: int, *, limit: int = 1000
    ) -> tuple[LifecycleEventV1, ...]:
        if sequence < 0:
            raise ValueError("lifecycle event sequence cannot be negative")
        if limit < 1 or limit > 10_000:
            raise ValueError("lifecycle event limit must be in [1, 10000]")
        rows = self.connection.execute(
            "SELECT * FROM world_events_v2 WHERE id>? ORDER BY id LIMIT ?",
            (sequence, limit),
        ).fetchall()
        return tuple(
            LifecycleEventV1(
                sequence=int(row["id"]),
                goal_id=(str(row["goal_id"]) if row["goal_id"] is not None else None),
                kind=str(row["kind"]),
                source=str(row["source"]),
                payload=dict(json.loads(row["payload_json"])),
                created_at=str(row["created_at"]),
            )
            for row in rows
        )

    def lifecycle_cursor(self, observer_id: str) -> int | None:
        row = self.connection.execute(
            "SELECT last_sequence FROM lifecycle_cursors_v1 WHERE observer_id=?",
            (observer_id,),
        ).fetchone()
        return int(row["last_sequence"]) if row is not None else None

    def initialize_lifecycle_cursor(self, observer_id: str) -> int:
        if not observer_id:
            raise ValueError("lifecycle observer id cannot be empty")
        try:
            self.connection.execute(
                """
                INSERT OR IGNORE INTO lifecycle_cursors_v1(observer_id,last_sequence)
                SELECT ?,COALESCE(MAX(id),0) FROM world_events_v2
                """,
                (observer_id,),
            )
            row = self.connection.execute(
                "SELECT last_sequence FROM lifecycle_cursors_v1 WHERE observer_id=?",
                (observer_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError("lifecycle cursor initialization did not persist")
            self.connection.commit()
            return int(row["last_sequence"])
        except Exception:
            self.connection.rollback()
            raise

    def save_lifecycle_cursor(self, observer_id: str, sequence: int) -> int:
        if not observer_id:
            raise ValueError("lifecycle observer id cannot be empty")
        if sequence < 0:
            raise ValueError("lifecycle cursor sequence cannot be negative")
        try:
            self.connection.execute(
                """
                INSERT INTO lifecycle_cursors_v1(observer_id,last_sequence)
                VALUES(?,?)
                ON CONFLICT(observer_id) DO UPDATE SET
                    last_sequence=MAX(
                        lifecycle_cursors_v1.last_sequence,
                        excluded.last_sequence
                    ),
                    updated_at=CASE
                        WHEN excluded.last_sequence > lifecycle_cursors_v1.last_sequence
                        THEN CURRENT_TIMESTAMP
                        ELSE lifecycle_cursors_v1.updated_at
                    END
                """,
                (observer_id, sequence),
            )
            row = self.connection.execute(
                "SELECT last_sequence FROM lifecycle_cursors_v1 WHERE observer_id=?",
                (observer_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError("lifecycle cursor advancement did not persist")
            self.connection.commit()
            return int(row["last_sequence"])
        except Exception:
            self.connection.rollback()
            raise

    def latest_event_payload(self, kind: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT payload_json FROM world_events_v2
            WHERE kind=? ORDER BY id DESC LIMIT 1
            """,
            (kind,),
        ).fetchone()
        return dict(json.loads(row["payload_json"])) if row is not None else None

    def retention_counter(self, name: str) -> int:
        if name not in _RETENTION_COUNTER_NAMES:
            raise ValueError(f"unknown retention counter: {name}")
        row = self.connection.execute(
            "SELECT value FROM retention_counters_v1 WHERE name=?", (name,)
        ).fetchone()
        return int(row["value"]) if row is not None else 0

    def database_size_bytes(self) -> int:
        page_size = int(self.connection.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(self.connection.execute("PRAGMA page_count").fetchone()[0])
        return page_size * page_count

    def events(self, goal_id: str | None = None) -> tuple[dict[str, Any], ...]:
        if goal_id is None:
            rows = self.connection.execute("SELECT * FROM world_events_v2 ORDER BY id").fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM world_events_v2 WHERE goal_id=? ORDER BY id", (goal_id,)
            ).fetchall()
        return tuple({
            "id": row["id"], "goal_id": row["goal_id"], "kind": row["kind"],
            "source": row["source"], "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        } for row in rows)

    def record_brain_call(
        self, goal_id: str, brain_id: str, purpose: str, snapshot_id: str,
        projection_sha256: str, *, output: Any = None, latency_ms: float | None = None,
        usage: Mapping[str, Any] | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO brain_calls_v2(
                goal_id, brain_id, purpose, snapshot_id, projection_sha256,
                output_sha256, latency_ms, usage_json
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                goal_id, brain_id, purpose, snapshot_id, projection_sha256,
                artifact_sha256(output) if output is not None else None,
                latency_ms, canonical_json(usage or {}),
            ),
        )
        self.connection.commit()

    def brain_call_count(self, goal_id: str | None = None) -> int:
        if goal_id is None:
            row = self.connection.execute("SELECT COUNT(*) AS value FROM brain_calls_v2").fetchone()
        else:
            row = self.connection.execute(
                "SELECT COUNT(*) AS value FROM brain_calls_v2 WHERE goal_id=?", (goal_id,)
            ).fetchone()
        return int(row["value"])

    def save_preference_evidence(self, evidence: PreferenceEvidenceV1) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO learning_evidence_v1(id, goal_id, body_json) VALUES(?,?,?)",
            (evidence.id, evidence.goal_id, canonical_json(evidence)),
        )
        self.connection.commit()

    def preference_evidence(self, goal_id: str) -> tuple[PreferenceEvidenceV1, ...]:
        rows = self.connection.execute(
            "SELECT body_json FROM learning_evidence_v1 WHERE goal_id=? ORDER BY created_at,id",
            (goal_id,),
        ).fetchall()
        return tuple(_preference_evidence(json.loads(row["body_json"])) for row in rows)

    def save_learning_candidate(self, candidate: LearningCandidateV1) -> None:
        existing = self.connection.execute(
            "SELECT body_json FROM learning_candidates_v1 WHERE id=?",
            (candidate.id,),
        ).fetchone()
        self.connection.execute(
            "INSERT OR REPLACE INTO learning_candidates_v1(id, goal_id, body_json) VALUES(?,?,?)",
            (candidate.id, candidate.goal_id, canonical_json(candidate)),
        )
        if existing is None:
            self._insert_event(
                candidate.goal_id,
                "learning_candidate_created",
                candidate.plugin_id or "engine.learning/v2",
                {
                    "candidate_id": candidate.id,
                    "field_path": candidate.field_path,
                    "preference_id": candidate.preference_id,
                    "evidence_count": len(candidate.evidence_ids),
                    "status": candidate.status.value,
                },
            )
        self.connection.commit()

    def learning_candidates(
        self,
        *,
        goal_id: str | None = None,
        statuses: tuple[str, ...] | None = None,
    ) -> tuple[LearningCandidateV1, ...]:
        clauses: list[str] = []
        parameters: list[str] = []
        if goal_id is not None:
            clauses.append("goal_id=?")
            parameters.append(goal_id)
        if statuses:
            marks = ",".join("?" for _ in statuses)
            clauses.append(f"json_extract(body_json, '$.status') IN ({marks})")
            parameters.extend(statuses)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.connection.execute(
            "SELECT body_json FROM learning_candidates_v1"
            + where
            + " ORDER BY created_at,id",
            tuple(parameters),
        ).fetchall()
        return tuple(
            LearningCandidateV1.from_dict(json.loads(row["body_json"])) for row in rows
        )

    def get_learning_candidate(self, candidate_id: str) -> LearningCandidateV1:
        row = self.connection.execute(
            "SELECT body_json FROM learning_candidates_v1 WHERE id=?", (candidate_id,)
        ).fetchone()
        if row is None:
            raise KeyError(candidate_id)
        return LearningCandidateV1.from_dict(json.loads(row["body_json"]))

    def plugin_cursor(self, provider_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT cursor FROM plugin_experience_cursors_v1 WHERE provider_id=?",
            (provider_id,),
        ).fetchone()
        return str(row["cursor"]) if row is not None else None

    def save_behavior_batch(
        self,
        provider_id: str,
        plugin_id: str,
        batch: BehaviorBatchV1,
    ) -> tuple[BehaviorSignalV1, ...]:
        """Atomically persist new signals and advance the opaque provider cursor."""
        inserted: list[BehaviorSignalV1] = []
        with self.connection:
            for signal in batch.signals:
                cursor = self.connection.execute(
                    """
                    INSERT OR IGNORE INTO behavior_signals_v1(
                        id,provider_id,plugin_id,target_id,entity_id,
                        capability_family,preference_id,body_json
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        signal.id,
                        provider_id,
                        plugin_id,
                        signal.target_id,
                        signal.entity_id,
                        signal.capability_family,
                        signal.preference_id,
                        canonical_json(signal),
                    ),
                )
                if cursor.rowcount == 1:
                    inserted.append(signal)
            self.connection.execute(
                """
                INSERT INTO plugin_experience_cursors_v1(provider_id,plugin_id,cursor)
                VALUES(?,?,?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    plugin_id=excluded.plugin_id,
                    cursor=excluded.cursor,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (provider_id, plugin_id, batch.cursor),
            )
        return tuple(inserted)

    def link_behavior_signal(
        self,
        signal_id: str,
        *,
        goal_id: str | None,
        status: str,
        reason: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO behavior_signal_links_v1(
                signal_id,goal_id,status,reason
            ) VALUES(?,?,?,?)
            """,
            (signal_id, goal_id or "", status, reason),
        )
        self.connection.commit()

    def behavior_signal_count(self) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(*) AS value FROM behavior_signals_v1"
            ).fetchone()["value"]
        )

    def behavior_signals(
        self, *, routine_template_id: str | None = None
    ) -> tuple[BehaviorSignalV1, ...]:
        if routine_template_id is None:
            rows = self.connection.execute(
                "SELECT body_json FROM behavior_signals_v1 ORDER BY created_at,id"
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT body_json FROM behavior_signals_v1
                WHERE json_extract(body_json, '$.routine_template_id')=?
                ORDER BY created_at,id
                """,
                (routine_template_id,),
            ).fetchall()
        return tuple(
            BehaviorSignalV1.from_dict(json.loads(row["body_json"])) for row in rows
        )

    def behavior_signal_links(self, signal_id: str) -> tuple[dict[str, str], ...]:
        rows = self.connection.execute(
            """
            SELECT goal_id,status,reason FROM behavior_signal_links_v1
            WHERE signal_id=? ORDER BY goal_id
            """,
            (signal_id,),
        ).fetchall()
        return tuple(
            {
                "goal_id": str(row["goal_id"]),
                "status": str(row["status"]),
                "reason": str(row["reason"]),
            }
            for row in rows
        )

    def invalidate_plans(self, goal_id: str) -> None:
        self.connection.execute("DELETE FROM plan_cache_v2 WHERE goal_id=?", (goal_id,))
        self.connection.commit()

    def plan_count(self, goal_id: str | None = None) -> int:
        if goal_id is None:
            row = self.connection.execute(
                "SELECT COUNT(*) AS value FROM plan_cache_v2"
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT COUNT(*) AS value FROM plan_cache_v2 WHERE goal_id=?",
                (goal_id,),
            ).fetchone()
        return int(row["value"])

    def save_plan(
        self, cache_key: str, goal_id: str, plugin_id: str, capability_family: str,
        manifest_fingerprint: str, mandate_id: str,
        proposal_template: Mapping[str, Any], outcome: Mapping[str, Any],
    ) -> None:
        row = self.connection.execute(
            "SELECT outcomes_json FROM plan_cache_v2 WHERE cache_key=?", (cache_key,)
        ).fetchone()
        outcomes = json.loads(row["outcomes_json"]) if row else []
        outcomes.append(dict(outcome))
        self.connection.execute(
            """
            INSERT INTO plan_cache_v2(
                cache_key, goal_id, plugin_id, capability_family,
                manifest_fingerprint, mandate_id, proposal_template_json, outcomes_json
            ) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(cache_key) DO UPDATE SET
                proposal_template_json=excluded.proposal_template_json,
                outcomes_json=excluded.outcomes_json, updated_at=CURRENT_TIMESTAMP
            """,
            (
                cache_key, goal_id, plugin_id, capability_family,
                manifest_fingerprint, mandate_id, canonical_json(proposal_template),
                canonical_json(outcomes),
            ),
        )
        self.connection.commit()

    def load_plan(
        self, cache_key: str, manifest_fingerprint: str, mandate_id: str
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT proposal_template_json, outcomes_json FROM plan_cache_v2
            WHERE cache_key=? AND manifest_fingerprint=? AND mandate_id=?
            """,
            (cache_key, manifest_fingerprint, mandate_id),
        ).fetchone()
        if row is None:
            return None
        outcomes = json.loads(row["outcomes_json"])
        if not outcomes or outcomes[-1].get("achieved") is not True:
            return None
        return json.loads(row["proposal_template_json"])

    def _insert_goal(self, goal: GoalSpecV2, *, commit: bool = True) -> None:
        self.connection.execute(
            "INSERT INTO goal_specs_v2(id, version, body_json, status, current) VALUES(?,?,?,?,1)",
            (goal.id, goal.version, canonical_json(goal), goal.status),
        )
        if commit:
            self.connection.commit()

    def _save_lifecycle(self, table: str, item_id: str, parent_id: str, value: Any) -> None:
        parent_column = {
            "proposed_actions_v1": "goal_id",
            "action_requests_v1": "proposal_id",
            "policy_decisions_v1": "request_id",
            "authorizations_v1": "request_id",
            "execution_receipts_v2": "request_id",
            "effect_deltas_v1": "request_id",
        }[table]
        self.connection.execute(
            f"INSERT INTO {table}(id, {parent_column}, body_json) VALUES(?,?,?)",
            (item_id, parent_id, canonical_json(value)),
        )
        self.connection.commit()

    def _migrate_v1_goals(self) -> None:
        exists = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='goals'"
        ).fetchone()
        if not exists:
            return
        rows = self.connection.execute("SELECT * FROM goals ORDER BY created_at,id").fetchall()
        for row in rows:
            if self.has_goal(str(row["id"])):
                continue
            target_id = str(row["target_id"])
            effect = DesiredEffectV1(
                id=f"legacy:{row['id']}:success",
                capability_family="engine.v1.observe-only",
                entity_selector={"target_ids": [target_id]},
                condition=ConditionV1("exists", path="world:entity_count"),
                parameters={"legacy_success_spec": json.loads(row["success_spec_json"])},
                description="Imported v1 success contract; observe-only until translated",
            )
            goal = GoalSpecV2(
                id=str(row["id"]), source_intent=str(row["instruction"]),
                mode=GoalModeV2(str(row["mode"])),
                entity_scope={"target_ids": [target_id]}, desired_effects=(effect,),
                budgets={"max_cycles": int(row["max_cycles"])}, mandate_id=None,
                status="imported_observe_only", priority=int(row["priority"]),
            )
            self._insert_goal(goal)
            self.append_event(goal.id, "v1_goal_migrated", "migration", {
                "target_selector": goal.entity_scope,
                "mutation": "observe_only",
            })


def _encode_target_observation_body(observation: TargetObservationV2) -> bytes:
    raw = canonical_json(observation).encode("utf-8")
    return _TARGET_BODY_ZLIB_PREFIX + zlib.compress(raw)


def _decode_target_observation_body(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        raw = value.encode("utf-8")
    elif isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        if raw.startswith(_TARGET_BODY_ZLIB_PREFIX):
            try:
                raw = zlib.decompress(raw[len(_TARGET_BODY_ZLIB_PREFIX):])
            except zlib.error as exc:
                raise ValueError("corrupt compressed target observation body") from exc
    else:
        raise ValueError("unsupported target observation body encoding")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid target observation body") from exc
    if not isinstance(decoded, dict):
        raise ValueError("target observation body must be an object")
    return decoded


def _decode_world_snapshot_body(value: Any) -> dict[str, Any]:
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = bytes(value).decode("utf-8")
    if not isinstance(value, str):
        raise ValueError("unsupported world snapshot body encoding")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid world snapshot body") from exc
    if not isinstance(decoded, dict):
        raise ValueError("world snapshot body must be an object")
    return decoded


def _load_world_snapshot_row(
    connection: sqlite3.Connection, row: Any
) -> WorldSnapshotV2:
    body = _decode_world_snapshot_body(row["body_json"])
    if "entities" in body:
        snapshot = _world_snapshot(body)
    else:
        snapshot = _reconstruct_world_snapshot(connection, body)
    expected = str(row["artifact_sha256"])
    if snapshot.sha256 != expected:
        raise ValueError(
            f"world snapshot artifact mismatch: {snapshot.id}"
        )
    return snapshot


def _reconstruct_world_snapshot(
    connection: sqlite3.Connection, reference: Mapping[str, Any]
) -> WorldSnapshotV2:
    required = {
        "revision",
        "snapshot_id",
        "observed_at",
        "target_revisions",
        "coverage",
    }
    missing = sorted(required - set(reference))
    if missing:
        raise ValueError(
            f"world snapshot reference is missing: {', '.join(missing)}"
        )
    raw_target_revisions = reference["target_revisions"]
    if not isinstance(raw_target_revisions, Mapping):
        raise ValueError("world snapshot target_revisions must be an object")
    target_revisions = {
        str(target_id): int(revision)
        for target_id, revision in raw_target_revisions.items()
    }
    raw_coverage = reference["coverage"]
    if not isinstance(raw_coverage, Mapping):
        raise ValueError("world snapshot coverage must be an object")
    coverage = dict(raw_coverage)
    entities: list[EntityV1] = []
    relations: list[RelationV1] = []
    observations: list[ObservationV1] = []
    for target_id, revision in sorted(target_revisions.items()):
        row = connection.execute(
            """
            SELECT body_json FROM target_observations_v2
            WHERE target_id=? AND revision=?
            """,
            (target_id, revision),
        ).fetchone()
        if row is None:
            raise ValueError(
                "world snapshot references missing target observation: "
                f"{target_id}@{revision}"
            )
        target = _target_observation(
            _decode_target_observation_body(row["body_json"])
        )
        if target.target_id != target_id or target.revision != revision:
            raise ValueError(
                "world snapshot target observation identity mismatch: "
                f"{target_id}@{revision}"
            )
        entities.extend(target.entities)
        relations.extend(target.relations)
        stale = _snapshot_target_is_stale(coverage, target_id)
        observations.extend(
            replace(item, evidence_grade=EvidenceGrade.STALE)
            if stale
            else item
            for item in target.observations
        )
    return WorldSnapshotV2(
        id=str(reference["snapshot_id"]),
        revision=int(reference["revision"]),
        observed_at=str(reference["observed_at"]),
        target_revisions=target_revisions,
        entities=tuple(sorted(entities, key=lambda item: item.id)),
        relations=tuple(sorted(relations, key=lambda item: item.id)),
        observations=tuple(sorted(observations, key=lambda item: item.id)),
        coverage=coverage,
    )


def _snapshot_target_is_stale(
    coverage: Mapping[str, Any], target_id: str
) -> bool:
    targets = coverage.get("targets", {})
    if not isinstance(targets, Mapping):
        return False
    target = targets.get(target_id, {})
    return isinstance(target, Mapping) and target.get("stale") is True


def _target_observation(value: Mapping[str, Any]) -> TargetObservationV2:
    return TargetObservationV2(
        target_id=str(value["target_id"]), revision=int(value["revision"]),
        observed_at=str(value["observed_at"]),
        entities=tuple(_entity(item) for item in value.get("entities", ())),
        relations=tuple(_relation(item) for item in value.get("relations", ())),
        observations=tuple(_observation(item) for item in value.get("observations", ())),
        coverage=dict(value.get("coverage", {})), source=str(value["source"]),
        available=value.get("available"),
        errors=tuple(str(item) for item in value.get("errors", ())),
        confirmed_at=(
            str(value["confirmed_at"])
            if value.get("confirmed_at") is not None
            else None
        ),
    )


def _as_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _world_snapshot(value: Mapping[str, Any]) -> WorldSnapshotV2:
    return WorldSnapshotV2(
        id=str(value["id"]), revision=int(value["revision"]),
        observed_at=str(value["observed_at"]),
        target_revisions=dict(value.get("target_revisions", {})),
        entities=tuple(_entity(item) for item in value.get("entities", ())),
        relations=tuple(_relation(item) for item in value.get("relations", ())),
        observations=tuple(_observation(item) for item in value.get("observations", ())),
        coverage=dict(value.get("coverage", {})),
    )


def _entity(value: Mapping[str, Any]) -> EntityV1:
    return EntityV1(
        id=str(value["id"]), target_id=str(value["target_id"]),
        entity_type=str(value["entity_type"]), source=str(value["source"]),
        name=str(value["name"]) if value.get("name") is not None else None,
        attributes=dict(value.get("attributes", {})),
        artifact_identity=(str(value["artifact_identity"]) if value.get("artifact_identity") is not None else None),
    )


def _relation(value: Mapping[str, Any]) -> RelationV1:
    return RelationV1(
        id=str(value["id"]), relation_type=str(value["relation_type"]),
        source_entity_id=str(value["source_entity_id"]),
        target_entity_id=str(value["target_entity_id"]), source=str(value["source"]),
        observed_at=str(value["observed_at"]),
        evidence_grade=EvidenceGrade(str(value["evidence_grade"])),
        confidence=float(value["confidence"]) if value.get("confidence") is not None else None,
        attributes=dict(value.get("attributes", {})),
    )


def _observation(value: Mapping[str, Any]) -> ObservationV1:
    return ObservationV1(
        id=str(value["id"]), entity_id=str(value["entity_id"]),
        property=str(value["property"]), value=value.get("value"),
        source=str(value["source"]), observed_at=str(value["observed_at"]),
        evidence_grade=EvidenceGrade(str(value["evidence_grade"])),
        unit=str(value["unit"]) if value.get("unit") is not None else None,
        quality=float(value["quality"]) if value.get("quality") is not None else None,
        coverage=str(value.get("coverage", "point")),
        artifact_identity=(str(value["artifact_identity"]) if value.get("artifact_identity") is not None else None),
    )


def _preference_evidence(value: Mapping[str, Any]) -> PreferenceEvidenceV1:
    return PreferenceEvidenceV1(
        id=str(value["id"]), goal_id=str(value["goal_id"]),
        grade=EvidenceGrade(str(value["grade"])), source=str(value["source"]),
        field_path=str(value["field_path"]), old_value=value.get("old_value"),
        new_value=value.get("new_value"), context=dict(value.get("context", {})),
        observed_at=str(value["observed_at"]),
        explicit_conflict=bool(value.get("explicit_conflict", False)),
        signal_id=(str(value["signal_id"]) if value.get("signal_id") is not None else None),
        plugin_id=(str(value["plugin_id"]) if value.get("plugin_id") is not None else None),
        target_id=(str(value["target_id"]) if value.get("target_id") is not None else None),
        entity_id=(str(value["entity_id"]) if value.get("entity_id") is not None else None),
        capability_family=(
            str(value["capability_family"])
            if value.get("capability_family") is not None else None
        ),
        preference_id=(
            str(value["preference_id"])
            if value.get("preference_id") is not None else None
        ),
    )
