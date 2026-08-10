from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from engine_sdk import (
    ActionRequestV1,
    AuthorizationV1,
    BehaviorBatchV1,
    BehaviorSignalV1,
    CapabilitySpecV2,
    EffectDeltaV1,
    EntityV1,
    EvidenceGrade,
    ExecutionReceiptV2,
    ExecutionStateV2,
    ObservationV1,
    PluginManifestV2,
    ProposedActionV1,
    RelationV1,
    SpecialistAdviceV1,
    TargetObservationV2,
    WorldSnapshotV2,
    canonical_json,
    load_static_manifest,
    locate_distribution_manifest,
)

PLUGIN_ID = "engine.reference-world"
TARGET_ID = "engine.reference-world.warehouse"
FAMILY = "warehouse.transfer-bin"
PREFERENCE_ID = "engine.reference-world.preference.reserve-target-band/v1"


class LazyWarehouseStore:
    """Factory construction is inert; SQLite opens on first observe/execute."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._connection: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(self.path)
            self._connection.row_factory = sqlite3.Row
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS state(
                    id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL,
                    incoming INTEGER NOT NULL, reserve INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO state(id,revision,incoming,reserve) VALUES(1,0,8,0);
                CREATE TABLE IF NOT EXISTS tasks(
                    idempotency_key TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL DEFAULT '',
                    authorization_id TEXT NOT NULL DEFAULT '',
                    capability_id TEXT NOT NULL DEFAULT '',
                    requested_at TEXT NOT NULL DEFAULT '',
                    requested_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'succeeded',
                    moved INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS behavior_signals(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL UNIQUE,
                    old_value_json TEXT NOT NULL,
                    new_value_json TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    provenance_json TEXT NOT NULL
                );
                """
            )
            columns = {
                str(row["name"])
                for row in self._connection.execute("PRAGMA table_info(tasks)")
            }
            migrations = {
                "request_id": "TEXT NOT NULL DEFAULT ''",
                "authorization_id": "TEXT NOT NULL DEFAULT ''",
                "capability_id": "TEXT NOT NULL DEFAULT ''",
                "requested_at": "TEXT NOT NULL DEFAULT ''",
                "requested_count": "INTEGER NOT NULL DEFAULT 0",
                "status": "TEXT NOT NULL DEFAULT 'succeeded'",
            }
            for name, declaration in migrations.items():
                if name not in columns:
                    self._connection.execute(
                        f"ALTER TABLE tasks ADD COLUMN {name} {declaration}"
                    )
            self._connection.commit()
        return self._connection

    def observe(self) -> tuple[int, int, int]:
        self.connection.execute("UPDATE state SET revision=revision+1 WHERE id=1")
        self.connection.commit()
        row = self.connection.execute("SELECT revision,incoming,reserve FROM state WHERE id=1").fetchone()
        return int(row["revision"]), int(row["incoming"]), int(row["reserve"])

    def start_transfer(
        self,
        key: str,
        *,
        request_id: str,
        authorization_id: str,
        capability_id: str,
        requested_at: str,
        count: int,
    ) -> tuple[sqlite3.Row, bool]:
        previous = self.task(key)
        if previous is not None:
            return previous, True
        self.connection.execute(
            """
            INSERT INTO tasks(
                idempotency_key, request_id, authorization_id, capability_id,
                requested_at, requested_count, status, moved, result_json
            ) VALUES(?,?,?,?,?,?,'running',0,'{}')
            """,
            (
                key, request_id, authorization_id, capability_id,
                requested_at, count,
            ),
        )
        self.connection.commit()
        task = self.task(key)
        assert task is not None
        return task, False

    def poll_transfer(self, key: str) -> sqlite3.Row:
        task = self.task(key)
        if task is None:
            raise KeyError(key)
        if task["status"] != "running":
            return task
        row = self.connection.execute(
            "SELECT incoming FROM state WHERE id=1"
        ).fetchone()
        requested = int(task["requested_count"])
        moved = min(requested, int(row["incoming"]))
        self.connection.execute(
            "UPDATE state SET incoming=incoming-?, reserve=reserve+? WHERE id=1",
            (moved, moved),
        )
        status = "succeeded" if moved == requested else "partial"
        self.connection.execute(
            """
            UPDATE tasks SET status=?, moved=?, result_json=?
            WHERE idempotency_key=?
            """,
            (status, moved, canonical_json({"moved": moved}), key),
        )
        self.connection.commit()
        result = self.task(key)
        assert result is not None
        return result

    def cancel_transfer(self, key: str) -> sqlite3.Row:
        task = self.task(key)
        if task is None:
            raise KeyError(key)
        if task["status"] == "running":
            self.connection.execute(
                "UPDATE tasks SET status='cancelled' WHERE idempotency_key=?",
                (key,),
            )
            self.connection.commit()
        result = self.task(key)
        assert result is not None
        return result

    def task(self, key: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM tasks WHERE idempotency_key=?", (key,)
        ).fetchone()

    def record_behavior(
        self,
        *,
        old_value: int,
        new_value: int,
        context: dict[str, Any],
        observed_at: str,
        signal_id: str | None = None,
    ) -> str:
        stable_id = signal_id or "warehouse-behavior:" + uuid4().hex
        self.connection.execute(
            """
            INSERT INTO behavior_signals(
                signal_id,old_value_json,new_value_json,context_json,
                observed_at,provenance_json
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                stable_id,
                canonical_json(old_value),
                canonical_json(new_value),
                canonical_json(context),
                observed_at,
                canonical_json({"source": "external_warehouse_operator"}),
            ),
        )
        self.connection.commit()
        return stable_id

    def behavior_after(self, cursor: int, limit: int) -> tuple[sqlite3.Row, ...]:
        return tuple(
            self.connection.execute(
                """
                SELECT * FROM behavior_signals WHERE sequence>?
                ORDER BY sequence LIMIT ?
                """,
                (cursor, limit),
            ).fetchall()
        )

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


class WarehouseProvider:
    plugin_id = PLUGIN_ID
    target_id = TARGET_ID
    poll_interval_seconds = 2.0
    freshness_seconds = 10.0

    def __init__(self, store: LazyWarehouseStore, manifest: PluginManifestV2):
        self.store = store
        self.manifest = manifest

    def discover(self) -> tuple[CapabilitySpecV2, ...]:
        return self.manifest.capabilities

    def observe(self) -> TargetObservationV2:
        revision, incoming_count, reserve_count = self.store.observe()
        now = datetime.now(UTC).isoformat()
        grid = EntityV1("warehouse:grid", TARGET_ID, "warehouse.grid", PLUGIN_ID, "Warehouse grid")
        incoming = EntityV1(
            "warehouse:bin:incoming", TARGET_ID, "warehouse.bin", PLUGIN_ID,
            "Incoming bin", {"alias": "incoming"},
        )
        reserve = EntityV1(
            "warehouse:bin:reserve", TARGET_ID, "warehouse.bin", PLUGIN_ID,
            "Reserve bin", {"alias": "reserve"},
        )
        observations = tuple(
            ObservationV1(
                f"{entity.id}:count:r{revision}", entity.id, "bin.count", count,
                PLUGIN_ID, now, EvidenceGrade.OBSERVED, unit="crate",
                quality=1.0, coverage="complete",
            )
            for entity, count in ((incoming, incoming_count), (reserve, reserve_count))
        )
        relations = (
            RelationV1("warehouse:contains:incoming", "contains", grid.id, incoming.id, PLUGIN_ID, now, EvidenceGrade.OBSERVED),
            RelationV1("warehouse:contains:reserve", "contains", grid.id, reserve.id, PLUGIN_ID, now, EvidenceGrade.OBSERVED),
        )
        return TargetObservationV2(
            TARGET_ID, revision, now, (grid, incoming, reserve), relations,
            observations, {"bins": "complete", "bin.count": "complete"}, PLUGIN_ID,
        )

    def subscribe(self, wake: Any) -> None:
        del wake


class WarehouseController:
    plugin_id = PLUGIN_ID
    supported_families = (FAMILY,)

    def concretize(
        self, proposal: ProposedActionV1, snapshot: WorldSnapshotV2,
        capability: CapabilitySpecV2,
    ) -> ActionRequestV1:
        current = _count(snapshot, proposal.entity_id)
        wanted = int(proposal.semantic_parameters["minimum_count"])
        count = max(1, min(10, wanted - current))
        return ActionRequestV1(
            id="request:" + uuid4().hex,
            proposal_id=proposal.id, goal_id=proposal.goal_id,
            plugin_id=PLUGIN_ID, target_id=TARGET_ID,
            entity_id=proposal.entity_id, capability_id=capability.id,
            capability_family=capability.family,
            parameters={"from": "incoming", "to": "reserve", "count": count},
            snapshot_id=snapshot.id, world_revision=snapshot.revision,
            target_revision=int(snapshot.target_revisions[TARGET_ID]),
            preconditions=(), idempotency_key=proposal.id,
            deadline_at=(datetime.now(UTC) + timedelta(seconds=5)).isoformat(),
            invocation_mode=capability.invocation_mode,
        )


class WarehouseExecutor:
    plugin_id = PLUGIN_ID

    def __init__(self, store: LazyWarehouseStore):
        self.store = store

    def dispatch(
        self, request: ActionRequestV1, authorization: AuthorizationV1
    ) -> ExecutionReceiptV2:
        if authorization.request_sha256 != request.sha256:
            raise PermissionError("authorization mismatch")
        if request.idempotency_key is None:
            raise ValueError("warehouse task requires an idempotency key")
        started = datetime.now(UTC).isoformat()
        task, replayed = self.store.start_transfer(
            request.idempotency_key,
            request_id=request.id,
            authorization_id=authorization.id,
            capability_id=request.capability_id,
            requested_at=started,
            count=int(request.parameters["count"]),
        )
        state = _execution_state(str(task["status"]))
        return ExecutionReceiptV2(
            id="receipt:" + uuid4().hex,
            request_id=request.id, authorization_id=authorization.id,
            target_id=TARGET_ID, capability_id=request.capability_id,
            state=state, requested_at=str(task["requested_at"]),
            completed_at=(
                datetime.now(UTC).isoformat()
                if state not in {ExecutionStateV2.ACCEPTED, ExecutionStateV2.RUNNING}
                else None
            ),
            acknowledged=True,
            result={"moved": int(task["moved"]), "idempotent_replay": replayed},
            external_handle=(
                request.idempotency_key
                if state in {ExecutionStateV2.ACCEPTED, ExecutionStateV2.RUNNING}
                else None
            ),
            adapter_version="0.2.0",
        )

    def poll(self, external_handle: str) -> ExecutionReceiptV2:
        return self._receipt(self.store.poll_transfer(external_handle), external_handle)

    def cancel(self, external_handle: str) -> ExecutionReceiptV2:
        return self._receipt(self.store.cancel_transfer(external_handle), external_handle)

    @staticmethod
    def _receipt(task: sqlite3.Row, external_handle: str) -> ExecutionReceiptV2:
        state = _execution_state(str(task["status"]))
        return ExecutionReceiptV2(
            id="receipt:" + uuid4().hex,
            request_id=str(task["request_id"]),
            authorization_id=str(task["authorization_id"]),
            target_id=TARGET_ID,
            capability_id=str(task["capability_id"]),
            state=state,
            requested_at=str(task["requested_at"]),
            completed_at=(
                None
                if state in {ExecutionStateV2.ACCEPTED, ExecutionStateV2.RUNNING}
                else datetime.now(UTC).isoformat()
            ),
            acknowledged=True,
            result={"moved": int(task["moved"])},
            external_handle=(
                external_handle
                if state in {ExecutionStateV2.ACCEPTED, ExecutionStateV2.RUNNING}
                else None
            ),
            adapter_version="0.2.0",
        )


class WarehouseOracle:
    plugin_id = PLUGIN_ID
    supported_families = (FAMILY,)

    def reconcile(
        self, proposal: ProposedActionV1, pre_state: WorldSnapshotV2,
        receipt: ExecutionReceiptV2, post_state: WorldSnapshotV2,
    ) -> EffectDeltaV1:
        before = _count(pre_state, proposal.entity_id)
        after, observation_id = _count_with_id(post_state, proposal.entity_id)
        wanted = int(proposal.semantic_parameters["minimum_count"])
        achieved = after >= wanted
        return EffectDeltaV1(
            id="effect:" + uuid4().hex,
            goal_id=proposal.goal_id, proposal_id=proposal.id,
            request_id=receipt.request_id, receipt_id=receipt.id,
            pre_snapshot_id=pre_state.id, post_snapshot_id=post_state.id,
            evidence_grade=EvidenceGrade.OBSERVED, achieved=achieved,
            changes={"before": before, "after": after},
            measurement_observation_ids=(observation_id,),
            reason="fresh reserve count reached requested minimum" if achieved else "fresh reserve count remains below requested minimum",
            observed_at=post_state.observed_at,
        )


class WarehouseExperienceProvider:
    id = "warehouse-experience"
    plugin_id = PLUGIN_ID

    def __init__(self, store: LazyWarehouseStore):
        self.store = store

    def read(self, after_cursor: str | None, limit: int) -> BehaviorBatchV1:
        cursor = int(after_cursor or 0)
        rows = self.store.behavior_after(cursor, limit + 1)
        selected = rows[:limit]
        signals = tuple(
            BehaviorSignalV1(
                id=str(row["signal_id"]),
                plugin_id=PLUGIN_ID,
                target_id=TARGET_ID,
                entity_id="warehouse:bin:reserve",
                capability_family=FAMILY,
                preference_id=PREFERENCE_ID,
                old_value=json.loads(row["old_value_json"]),
                new_value=json.loads(row["new_value_json"]),
                context=json.loads(row["context_json"]),
                observed_at=str(row["observed_at"]),
                provenance=json.loads(row["provenance_json"]),
                evidence_grade=EvidenceGrade.INFERRED,
            )
            for row in selected
        )
        next_cursor = str(selected[-1]["sequence"]) if selected else str(cursor)
        return BehaviorBatchV1(next_cursor, signals, len(rows) > limit)


class WarehouseSpecialist:
    id = "engine.reference-world.warehouse-specialist/v1"
    supported_families = (FAMILY,)

    def advise(
        self, goal: Any, snapshot: WorldSnapshotV2, request: dict[str, object]
    ) -> SpecialistAdviceV1:
        effect_id = str(request.get("effect_id", ""))
        effect = next(
            (item for item in goal.desired_effects if item.id == effect_id), None
        )
        if effect is None or effect.capability_family != FAMILY:
            return SpecialistAdviceV1(self.id, False, None, "Unsupported effect")
        entities = [
            item for item in snapshot.entities
            if item.id in set(effect.entity_selector.get("entity_ids", ()))
        ]
        if not entities:
            return SpecialistAdviceV1(self.id, False, None, "Reserve bin is not observed")
        minimum = int(
            goal.preferences.get(
                PREFERENCE_ID, effect.parameters.get("minimum_count", 1)
            )
        )
        proposal = ProposedActionV1(
            id="proposal:" + uuid4().hex,
            goal_id=goal.id,
            desired_effect_id=effect.id,
            capability_family=FAMILY,
            target_id=entities[0].target_id,
            entity_id=entities[0].id,
            semantic_parameters={"minimum_count": minimum},
            based_on_snapshot_id=snapshot.id,
            based_on_world_revision=snapshot.revision,
            proposed_by=self.id,
            rationale="Apply the declared warehouse preference without execution authority",
        )
        return SpecialistAdviceV1(self.id, True, proposal, "Typed warehouse preference")


@dataclass(frozen=True)
class WarehousePlugin:
    manifest: PluginManifestV2
    providers: tuple[Any, ...]
    controllers: tuple[Any, ...]
    executors: tuple[Any, ...]
    oracles: tuple[Any, ...]
    specialists: tuple[Any, ...] = ()
    experience_providers: tuple[Any, ...] = ()


def create_plugin(path: str | Path = ":memory:") -> WarehousePlugin:
    manifest_path = Path(__file__).resolve().parents[2] / "engine-plugin.toml"
    if not manifest_path.is_file():
        from importlib import metadata

        manifest_path = locate_distribution_manifest(
            metadata.distribution("engine-reference-world")
        )
        if manifest_path is None:
            raise FileNotFoundError(
                "engine-reference-world static manifest is not installed"
            )
    manifest = load_static_manifest(manifest_path)
    store = LazyWarehouseStore(path)
    return WarehousePlugin(
        manifest,
        (WarehouseProvider(store, manifest),),
        (WarehouseController(),),
        (WarehouseExecutor(store),),
        (WarehouseOracle(),),
        (WarehouseSpecialist(),),
        (WarehouseExperienceProvider(store),),
    )


def load_plugin() -> WarehousePlugin:
    return create_plugin(os.environ.get("ENGINE_REFERENCE_WORLD_DATABASE", ".engine/reference-world.sqlite3"))


def _count(snapshot: WorldSnapshotV2, entity_id: str) -> int:
    return _count_with_id(snapshot, entity_id)[0]


def _count_with_id(snapshot: WorldSnapshotV2, entity_id: str) -> tuple[int, str]:
    observation = next(
        item for item in snapshot.observations
        if item.entity_id == entity_id and item.property == "bin.count"
    )
    return int(observation.value), observation.id


def _execution_state(value: str) -> ExecutionStateV2:
    return {
        "running": ExecutionStateV2.RUNNING,
        "succeeded": ExecutionStateV2.SUCCEEDED,
        "partial": ExecutionStateV2.PARTIAL,
        "cancelled": ExecutionStateV2.CANCELLED,
    }[value]
