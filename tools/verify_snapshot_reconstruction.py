#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for source_root in (ROOT / "src", ROOT / "packages/engine-sdk/src"):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from engine_sdk import canonical_json  # noqa: E402 - direct script execution

from engine.world_store import (  # noqa: E402 - direct script execution
    _decode_world_snapshot_body,
    _load_world_snapshot_row,
    _world_snapshot,
)


def verify(database: Path) -> int:
    uri = f"{database.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    verified = 0
    legacy = 0
    references = 0
    failures: list[str] = []
    try:
        rows = connection.execute(
            "SELECT * FROM world_snapshots_v2 ORDER BY revision"
        ).fetchall()
        for row in rows:
            snapshot_id = str(row["snapshot_id"])
            try:
                body = _decode_world_snapshot_body(row["body_json"])
                if "entities" in body:
                    legacy += 1
                else:
                    references += 1
                snapshot = _load_world_snapshot_row(connection, row)
                round_tripped = _world_snapshot(
                    json.loads(canonical_json(snapshot))
                )
                if (
                    round_tripped.semantic_fingerprint()
                    != snapshot.semantic_fingerprint()
                ):
                    raise ValueError("semantic fingerprint mismatch")
                verified += 1
            except Exception as exc:
                failures.append(f"{snapshot_id}: {type(exc).__name__}: {exc}")
    finally:
        connection.close()
    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    print(
        "snapshot reconstruction: "
        f"verified={verified} legacy={legacy} reference={references} "
        f"failures={len(failures)}"
    )
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify Engine world snapshot reconstruction without mutation."
    )
    parser.add_argument(
        "--database",
        type=Path,
        required=True,
        help="Path to an existing Engine SQLite database.",
    )
    args = parser.parse_args(argv)
    if not args.database.is_file():
        parser.error(f"database does not exist: {args.database}")
    return verify(args.database)


if __name__ == "__main__":
    raise SystemExit(main())
