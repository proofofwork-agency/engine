from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable, Self
from uuid import uuid4


class LeaseHeldError(RuntimeError):
    pass


class RuntimeLease:
    """Expiring SQLite singleton lease for one active runtime per Engine store."""

    def __init__(
        self,
        path: str | Path,
        *,
        ttl_seconds: float = 15.0,
        on_lost: Callable[[], None] | None = None,
    ):
        if ttl_seconds <= 0:
            raise ValueError("lease ttl must be positive")
        self.path = Path(path)
        self.ttl_seconds = ttl_seconds
        self.token = "runtime:" + uuid4().hex
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._on_lost = on_lost
        self._lost = threading.Event()

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    def acquire(self) -> RuntimeLease:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=1.0, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_leases_v1(
                lease_name TEXT PRIMARY KEY,
                owner_token TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=self.ttl_seconds)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT owner_token,expires_at FROM runtime_leases_v1 WHERE lease_name='engine-runtime'"
            ).fetchone()
            if row is not None and _datetime(str(row["expires_at"])) > now:
                connection.rollback()
                raise LeaseHeldError(
                    f"Engine store already has an active runtime lease until {row['expires_at']}"
                )
            connection.execute(
                """
                INSERT INTO runtime_leases_v1(
                    lease_name,owner_token,acquired_at,expires_at
                ) VALUES('engine-runtime',?,?,?)
                ON CONFLICT(lease_name) DO UPDATE SET
                    owner_token=excluded.owner_token,
                    acquired_at=excluded.acquired_at,
                    expires_at=excluded.expires_at
                """,
                (self.token, now.isoformat(), expires.isoformat()),
            )
            connection.commit()
        except Exception:
            connection.close()
            raise
        self._connection = connection
        self._thread = threading.Thread(
            target=self._renew_loop, name="engine-runtime-lease", daemon=True
        )
        self._thread.start()
        return self

    def renew(self) -> None:
        connection = self._connection
        if connection is None:
            raise RuntimeError("lease is not acquired")
        expires = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
        with self._lock, connection:
            cursor = connection.execute(
                """
                UPDATE runtime_leases_v1 SET expires_at=?
                WHERE lease_name='engine-runtime' AND owner_token=?
                """,
                (expires.isoformat(), self.token),
            )
            if cursor.rowcount != 1:
                raise LeaseHeldError("runtime lease ownership was lost")

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=min(1.0, self.ttl_seconds))
        connection = self._connection
        self._connection = None
        if connection is not None:
            with self._lock, connection:
                connection.execute(
                    "DELETE FROM runtime_leases_v1 WHERE lease_name='engine-runtime' AND owner_token=?",
                    (self.token,),
                )
            connection.close()

    def __enter__(self) -> Self:
        return self.acquire()

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _renew_loop(self) -> None:
        while not self._stop.wait(max(0.1, self.ttl_seconds / 3)):
            try:
                self.renew()
            except Exception:  # noqa: BLE001 - a lost lease must stop the renewer
                self._lost.set()
                if self._on_lost is not None:
                    self._on_lost()
                self._stop.set()
                return


def lease_status(path: str | Path) -> dict[str, str] | None:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='runtime_leases_v1'"
        ).fetchone()
        if exists is None:
            return None
        row = connection.execute(
            "SELECT owner_token,acquired_at,expires_at FROM runtime_leases_v1 WHERE lease_name='engine-runtime'"
        ).fetchone()
        if row is None:
            return None
        return {
            "owner_token": str(row["owner_token"]),
            "acquired_at": str(row["acquired_at"]),
            "expires_at": str(row["expires_at"]),
        }
    finally:
        connection.close()


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
