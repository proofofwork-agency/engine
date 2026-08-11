from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SNAPSHOT_BODY_ZLIB_PREFIX = b"engine.homey.snapshot.zlib/v1\x00"
_SNAPSHOT_STORAGE_COUNTER_NAMES = (
    "snapshot_deduplications",
    "snapshot_raw_body_bytes_written",
    "snapshot_rows_written",
    "snapshot_stored_body_bytes_written",
)


@dataclass(frozen=True)
class StoredSnapshot:
    revision: int
    state_hash: str
    state: dict[str, Any]
    observed_at: str


@dataclass(frozen=True)
class StoredProviderProjection:
    provider_id: str
    revision: int
    semantic_sha256: str
    presence_state: dict[str, Any]
    last_observed_at: str


@dataclass(frozen=True)
class SnapshotStorageStatus:
    rows: int
    body_bytes: int
    database_bytes: int
    wal_bytes: int
    counters: dict[str, int]

    @property
    def total_database_bytes(self) -> int:
        return self.database_bytes + self.wal_bytes


class HomeOpsStore:
    """Plugin-owned state; never shares mutable tables with EngineStore."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS aliases (
                kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                alias TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (kind, source_id),
                UNIQUE (kind, alias)
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                revision INTEGER PRIMARY KEY,
                state_hash TEXT NOT NULL,
                state_json TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS charters (
                version_id TEXT PRIMARY KEY,
                parent_version_id TEXT,
                charter_json TEXT NOT NULL,
                source_text TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS active_charter (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                version_id TEXT NOT NULL REFERENCES charters(version_id)
            );
            CREATE TABLE IF NOT EXISTS preference_evidence (
                id TEXT PRIMARY KEY,
                grade TEXT NOT NULL,
                source TEXT NOT NULL,
                text TEXT,
                context_json TEXT NOT NULL,
                charter_before TEXT,
                charter_after TEXT,
                patch_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provider_revision_ledger (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                revision INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provider_projection_state (
                provider_id TEXT PRIMARY KEY,
                revision INTEGER NOT NULL,
                semantic_sha256 TEXT NOT NULL,
                presence_state_json TEXT NOT NULL,
                last_observed_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS snapshot_storage_counters_v1 (
                name TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO provider_revision_ledger(singleton, revision)
            VALUES(1, -1);
            """
        )
        self._connection.executemany(
            """
            INSERT OR IGNORE INTO snapshot_storage_counters_v1(name, value)
            VALUES(?, 0)
            """,
            ((name,) for name in _SNAPSHOT_STORAGE_COUNTER_NAMES),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def next_provider_revision(self) -> int:
        """Allocate a raw provider revision for legacy callers."""
        self._connection.execute(
            "UPDATE provider_revision_ledger SET revision = revision + 1 WHERE singleton = 1"
        )
        self._connection.commit()
        row = self._connection.execute(
            "SELECT revision FROM provider_revision_ledger WHERE singleton = 1"
        ).fetchone()
        assert row is not None
        return int(row["revision"])

    def provider_projection(
        self, provider_id: str
    ) -> StoredProviderProjection | None:
        row = self._connection.execute(
            "SELECT * FROM provider_projection_state WHERE provider_id=?",
            (provider_id,),
        ).fetchone()
        if row is None:
            return None
        presence_state = json.loads(row["presence_state_json"])
        if not isinstance(presence_state, dict):
            raise ValueError("persisted provider presence state must be an object")
        return StoredProviderProjection(
            provider_id=str(row["provider_id"]),
            revision=int(row["revision"]),
            semantic_sha256=str(row["semantic_sha256"]),
            presence_state=presence_state,
            last_observed_at=str(row["last_observed_at"]),
        )

    def save_provider_projection(
        self,
        provider_id: str,
        semantic_sha256: str,
        presence_state: dict[str, Any],
        last_observed_at: str,
    ) -> tuple[StoredProviderProjection, bool]:
        """Atomically allocate a changed revision and persist its projection."""
        encoded_presence = _dump(presence_state)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT * FROM provider_projection_state WHERE provider_id=?",
                (provider_id,),
            ).fetchone()
            changed = (
                existing is None
                or str(existing["semantic_sha256"]) != semantic_sha256
            )
            if changed:
                self._connection.execute(
                    """
                    UPDATE provider_revision_ledger
                    SET revision = revision + 1 WHERE singleton = 1
                    """
                )
                ledger = self._connection.execute(
                    """
                    SELECT revision FROM provider_revision_ledger
                    WHERE singleton = 1
                    """
                ).fetchone()
                assert ledger is not None
                revision = int(ledger["revision"])
            else:
                revision = int(existing["revision"])
            self._connection.execute(
                """
                INSERT INTO provider_projection_state(
                    provider_id, revision, semantic_sha256,
                    presence_state_json, last_observed_at, updated_at
                ) VALUES(?,?,?,?,?,?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    revision=excluded.revision,
                    semantic_sha256=excluded.semantic_sha256,
                    presence_state_json=excluded.presence_state_json,
                    last_observed_at=excluded.last_observed_at,
                    updated_at=excluded.updated_at
                """,
                (
                    provider_id,
                    revision,
                    semantic_sha256,
                    encoded_presence,
                    last_observed_at,
                    _now(),
                ),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return (
            StoredProviderProjection(
                provider_id,
                revision,
                semantic_sha256,
                dict(presence_state),
                last_observed_at,
            ),
            changed,
        )

    def alias_for(
        self,
        kind: str,
        source_id: str,
        suggested: str,
        *,
        fixed: str | None = None,
    ) -> str:
        row = self._connection.execute(
            "SELECT alias FROM aliases WHERE kind = ? AND source_id = ?",
            (kind, source_id),
        ).fetchone()
        if row is not None:
            existing = str(row["alias"])
            if fixed is not None and fixed != existing:
                raise ValueError(
                    f"configured alias {fixed!r} conflicts with persisted {existing!r}"
                )
            return existing
        base = fixed or _slug(suggested)
        candidate = base
        suffix = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:8]
        collision = self._connection.execute(
            "SELECT source_id FROM aliases WHERE kind = ? AND alias = ?",
            (kind, candidate),
        ).fetchone()
        if collision is not None:
            if fixed is not None:
                raise ValueError(
                    f"configured alias {fixed!r} is already bound to another {kind}"
                )
            candidate = f"{base[:54]}_{suffix}"
        self._connection.execute(
            "INSERT INTO aliases (kind, source_id, alias, created_at) VALUES (?, ?, ?, ?)",
            (kind, source_id, candidate, _now()),
        )
        self._connection.commit()
        return candidate

    def record_snapshot(
        self, state: dict[str, Any], observed_at: str
    ) -> StoredSnapshot:
        raw_body = _dump(state).encode("utf-8")
        state_hash = hashlib.sha256(raw_body).hexdigest()
        stored_body = _encode_snapshot_body(raw_body)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT * FROM snapshots ORDER BY revision DESC LIMIT 1"
            ).fetchone()
            latest = _stored_snapshot(row) if row is not None else None
            if latest is not None and latest.state_hash == state_hash:
                self._increment_snapshot_storage_counter(
                    "snapshot_deduplications"
                )
                self._connection.commit()
                return StoredSnapshot(
                    latest.revision, state_hash, state, observed_at
                )
            revision = 0 if latest is None else latest.revision + 1
            self._connection.execute(
                """
                INSERT INTO snapshots (
                    revision, state_hash, state_json, observed_at, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (revision, state_hash, stored_body, observed_at, _now()),
            )
            self._increment_snapshot_storage_counter("snapshot_rows_written")
            self._increment_snapshot_storage_counter(
                "snapshot_raw_body_bytes_written", len(raw_body)
            )
            self._increment_snapshot_storage_counter(
                "snapshot_stored_body_bytes_written", len(stored_body)
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return StoredSnapshot(revision, state_hash, state, observed_at)

    def latest_snapshot(self) -> StoredSnapshot | None:
        row = self._connection.execute(
            "SELECT * FROM snapshots ORDER BY revision DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return _stored_snapshot(row)

    def snapshot_history(self) -> tuple[StoredSnapshot, ...]:
        rows = self._connection.execute(
            "SELECT * FROM snapshots ORDER BY revision"
        ).fetchall()
        return tuple(_stored_snapshot(row) for row in rows)

    def snapshot_storage_status(self) -> SnapshotStorageStatus:
        row = self._connection.execute(
            """
            SELECT COUNT(*) AS rows,
                   COALESCE(SUM(length(state_json)), 0) AS body_bytes
            FROM snapshots
            """
        ).fetchone()
        assert row is not None
        counters = {
            str(item["name"]): int(item["value"])
            for item in self._connection.execute(
                """
                SELECT name, value FROM snapshot_storage_counters_v1
                ORDER BY name
                """
            ).fetchall()
        }
        wal_path = Path(f"{self.path}-wal")
        return SnapshotStorageStatus(
            rows=int(row["rows"]),
            body_bytes=int(row["body_bytes"]),
            database_bytes=self.path.stat().st_size,
            wal_bytes=wal_path.stat().st_size if wal_path.exists() else 0,
            counters=counters,
        )

    def _increment_snapshot_storage_counter(
        self, name: str, amount: int = 1
    ) -> None:
        if name not in _SNAPSHOT_STORAGE_COUNTER_NAMES:
            raise ValueError(f"unknown snapshot storage counter: {name}")
        cursor = self._connection.execute(
            """
            UPDATE snapshot_storage_counters_v1
            SET value=value+? WHERE name=?
            """,
            (amount, name),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"missing snapshot storage counter: {name}")

    def save_charter(
        self,
        charter: dict[str, Any],
        source_text: str,
        *,
        parent_version_id: str | None = None,
    ) -> str:
        version_id = str(charter["version_id"])
        source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        self._connection.execute(
            """
            INSERT INTO charters (
                version_id, parent_version_id, charter_json, source_text,
                source_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                parent_version_id,
                _dump(charter),
                source_text,
                source_hash,
                _now(),
            ),
        )
        self._connection.execute(
            """
            INSERT INTO active_charter (singleton, version_id) VALUES (1, ?)
            ON CONFLICT(singleton) DO UPDATE SET version_id = excluded.version_id
            """,
            (version_id,),
        )
        self._connection.commit()
        return version_id

    def active_charter(self) -> dict[str, Any] | None:
        row = self._connection.execute(
            """
            SELECT c.charter_json FROM charters c
            JOIN active_charter a ON a.version_id = c.version_id
            WHERE a.singleton = 1
            """
        ).fetchone()
        return json.loads(row["charter_json"]) if row is not None else None

    def charter_source(self, version_id: str) -> str:
        row = self._connection.execute(
            "SELECT source_text FROM charters WHERE version_id = ?", (version_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown charter version: {version_id}")
        return str(row["source_text"])

    def record_preference(
        self,
        *,
        grade: str,
        source: str,
        text: str | None,
        context: dict[str, Any],
        charter_before: str | None = None,
        charter_after: str | None = None,
        patch: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> str:
        evidence_id = uuid.uuid4().hex
        self._connection.execute(
            """
            INSERT INTO preference_evidence (
                id, grade, source, text, context_json, charter_before,
                charter_after, patch_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
                grade,
                source,
                text,
                _dump(context),
                charter_before,
                charter_after,
                _dump(patch) if patch is not None else None,
                created_at or _now(),
            ),
        )
        self._connection.commit()
        return evidence_id

    def preferences(self) -> tuple[dict[str, Any], ...]:
        rows = self._connection.execute(
            "SELECT * FROM preference_evidence ORDER BY created_at, id"
        ).fetchall()
        return tuple(
            {
                "id": row["id"],
                "grade": row["grade"],
                "source": row["source"],
                "text": row["text"],
                "context": json.loads(row["context_json"]),
                "charter_before": row["charter_before"],
                "charter_after": row["charter_after"],
                "patch": (
                    json.loads(row["patch_json"])
                    if row["patch_json"] is not None
                    else None
                ),
                "created_at": row["created_at"],
            }
            for row in rows
        )

    def preferences_after(
        self, cursor: int, limit: int
    ) -> tuple[dict[str, Any], ...]:
        rows = self._connection.execute(
            """
            SELECT rowid AS sequence,* FROM preference_evidence
            WHERE rowid>? ORDER BY rowid LIMIT ?
            """,
            (cursor, limit),
        ).fetchall()
        return tuple(
            {
                "sequence": int(row["sequence"]),
                "id": str(row["id"]),
                "grade": str(row["grade"]),
                "source": str(row["source"]),
                "context": json.loads(row["context_json"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        )


def _slug(value: str) -> str:
    lowered = value.casefold().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"item_{slug}" if slug else "item"
    return slug[:63]


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _encode_snapshot_body(raw_body: bytes) -> bytes:
    return _SNAPSHOT_BODY_ZLIB_PREFIX + zlib.compress(raw_body)


def _decode_snapshot_body(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        raw_body = value.encode("utf-8")
    elif isinstance(value, (bytes, bytearray, memoryview)):
        raw_body = bytes(value)
        if raw_body.startswith(_SNAPSHOT_BODY_ZLIB_PREFIX):
            try:
                raw_body = zlib.decompress(
                    raw_body[len(_SNAPSHOT_BODY_ZLIB_PREFIX) :]
                )
            except zlib.error as exc:
                raise ValueError("corrupt compressed Homey snapshot body") from exc
    else:
        raise ValueError("unsupported Homey snapshot body encoding")
    try:
        decoded = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid Homey snapshot body") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Homey snapshot body must be an object")
    return decoded


def _stored_snapshot(row: sqlite3.Row) -> StoredSnapshot:
    return StoredSnapshot(
        revision=int(row["revision"]),
        state_hash=str(row["state_hash"]),
        state=_decode_snapshot_body(row["state_json"]),
        observed_at=str(row["observed_at"]),
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
