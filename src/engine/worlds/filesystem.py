from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from ..models import (
    CapabilitySpec,
    Goal,
    TargetManifest,
    ToolCall,
    ToolResult,
    WorldSnapshot,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class FilesystemTarget:
    """A strictly rooted software world used as one Engine target plugin."""

    _state_name = ".engine-target-state.json"

    def __init__(self, target_id: str, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = TargetManifest(
            id=target_id,
            description="Sandboxed hierarchical filesystem target",
            plugin_id="engine.filesystem",
        )
        if not self._state_path.exists():
            self._write_revision(0)

    @property
    def _state_path(self) -> Path:
        return self.root / self._state_name

    def seed(self, files: dict[str, str]) -> None:
        for relative, contents in files.items():
            path = self._resolve(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
        self._increment_revision()

    def capabilities(self) -> tuple[CapabilitySpec, ...]:
        return (
            CapabilitySpec(
                id="engine.fs.make-directory/v1",
                local_name="make_directory",
                description="Create a directory and any missing parents inside this target",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string", "minLength": 1}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
                idempotent=True,
            ),
            CapabilitySpec(
                id="engine.fs.move-file/v1",
                local_name="move_file",
                description="Move one file to a new relative path inside this target",
                input_schema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "minLength": 1},
                        "destination": {"type": "string", "minLength": 1},
                    },
                    "required": ["source", "destination"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                    "additionalProperties": False,
                },
            ),
        )

    def observe(self) -> WorldSnapshot:
        entries: dict[str, dict[str, str]] = {}
        for path in sorted(self.root.rglob("*")):
            if path == self._state_path:
                continue
            relative = path.relative_to(self.root).as_posix()
            if path.is_dir():
                entries[relative] = {"kind": "directory"}
            elif path.is_file():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                entries[relative] = {"kind": "file", "sha256": digest}
        return WorldSnapshot(
            target_id=self.manifest.id,
            revision=self._read_revision(),
            state={"entries": entries},
            observed_at=_now(),
        )

    def execute(self, call: ToolCall) -> ToolResult:
        try:
            if call.capability_id == "engine.fs.make-directory/v1":
                path = self._resolve(str(call.arguments["path"]))
                path.mkdir(parents=True, exist_ok=True)
                self._increment_revision()
                return ToolResult(True, True, {"path": path.relative_to(self.root).as_posix()})
            if call.capability_id == "engine.fs.move-file/v1":
                source = self._resolve(str(call.arguments["source"]))
                destination = self._resolve(str(call.arguments["destination"]))
                if not source.is_file():
                    return ToolResult(False, False, error="source is missing")
                if not destination.parent.is_dir():
                    return ToolResult(False, False, error="destination parent is missing")
                if destination.exists():
                    return ToolResult(False, False, error="destination already exists")
                shutil.move(str(source), str(destination))
                self._increment_revision()
                return ToolResult(
                    True,
                    True,
                    {
                        "source": source.relative_to(self.root).as_posix(),
                        "destination": destination.relative_to(self.root).as_posix(),
                    },
                )
            return ToolResult(
                False, False, error=f"unsupported capability: {call.capability_id}"
            )
        except (KeyError, TypeError, ValueError) as error:
            return ToolResult(False, False, error=str(error))

    def goal_satisfied(self, goal: Goal, snapshot: WorldSnapshot) -> bool:
        entries = snapshot.state["entries"]
        for move in goal.success_spec.get("moves", []):
            if move["destination"] not in entries or move["source"] in entries:
                return False
        return bool(goal.success_spec.get("moves"))

    def _resolve(self, relative: str) -> Path:
        if not relative or Path(relative).is_absolute():
            raise ValueError("path must be a non-empty relative path")
        resolved = (self.root / relative).resolve()
        if self.root not in resolved.parents:
            raise ValueError("path escapes filesystem target root")
        return resolved

    def _read_revision(self) -> int:
        return int(json.loads(self._state_path.read_text(encoding="utf-8"))["revision"])

    def _write_revision(self, revision: int) -> None:
        self._state_path.write_text(json.dumps({"revision": revision}), encoding="utf-8")

    def _increment_revision(self) -> None:
        self._write_revision(self._read_revision() + 1)
