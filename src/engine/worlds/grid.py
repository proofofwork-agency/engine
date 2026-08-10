from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


class GridTarget:
    """A durable discrete spatial world with discoverable hidden obstacles."""

    def __init__(
        self,
        target_id: str,
        state_path: str | Path,
        initial_state: dict[str, Any] | None = None,
    ):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest = TargetManifest(
            id=target_id,
            description="Discrete spatial simulator target",
            plugin_id="engine.spatial-grid",
        )
        if not self.state_path.exists():
            if initial_state is None:
                raise ValueError("initial_state is required for a new grid target")
            self._write(initial_state)

    @classmethod
    def default(cls, target_id: str, state_path: str | Path) -> GridTarget:
        return cls(
            target_id,
            state_path,
            initial_state={
                "revision": 0,
                "bounds": [4, 4],
                "position": [0, 0],
                "blocked": [[1, 0]],
                "known_blocked": [],
                "items": {"key": [2, 0]},
                "inventory": [],
            },
        )

    def capabilities(self) -> tuple[CapabilitySpec, ...]:
        return (
            CapabilitySpec(
                id="engine.spatial.step/v1",
                local_name="move",
                description="Move one cell in a cardinal direction",
                input_schema={
                    "type": "object",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "enum": ["north", "east", "south", "west"],
                        }
                    },
                    "required": ["direction"],
                    "additionalProperties": False,
                },
                output_schema={"type": "object"},
            ),
            CapabilitySpec(
                id="engine.spatial.pick-up/v1",
                local_name="pick_up",
                description="Pick up a named item at the current position",
                input_schema={
                    "type": "object",
                    "properties": {"item": {"type": "string", "minLength": 1}},
                    "required": ["item"],
                    "additionalProperties": False,
                },
                output_schema={"type": "object"},
            ),
        )

    def observe(self) -> WorldSnapshot:
        state = self._read()
        visible = {
            "bounds": state["bounds"],
            "position": state["position"],
            "known_blocked": state["known_blocked"],
            "items": state["items"],
            "inventory": state["inventory"],
        }
        return WorldSnapshot(
            target_id=self.manifest.id,
            revision=int(state["revision"]),
            state=visible,
            observed_at=_now(),
        )

    def execute(self, call: ToolCall) -> ToolResult:
        state = self._read()
        if call.capability_id == "engine.spatial.step/v1":
            direction = str(call.arguments.get("direction", ""))
            deltas = {
                "north": (0, 1),
                "east": (1, 0),
                "south": (0, -1),
                "west": (-1, 0),
            }
            if direction not in deltas:
                return ToolResult(False, False, error="invalid direction")
            dx, dy = deltas[direction]
            attempted = [state["position"][0] + dx, state["position"][1] + dy]
            width, height = state["bounds"]
            if not (0 <= attempted[0] < width and 0 <= attempted[1] < height):
                return ToolResult(False, False, {"attempted": attempted}, "out of bounds")
            if attempted in state["blocked"]:
                if attempted not in state["known_blocked"]:
                    state["known_blocked"].append(attempted)
                state["revision"] += 1
                self._write(state)
                return ToolResult(
                    False,
                    True,
                    {"attempted": attempted, "obstacle_discovered": attempted},
                    "movement blocked",
                    partial=True,
                )
            state["position"] = attempted
            state["revision"] += 1
            self._write(state)
            return ToolResult(True, True, {"position": attempted})

        if call.capability_id == "engine.spatial.pick-up/v1":
            item = str(call.arguments.get("item", ""))
            location = state["items"].get(item)
            if location != state["position"]:
                return ToolResult(False, False, error="item is not at current position")
            state["inventory"].append(item)
            del state["items"][item]
            state["revision"] += 1
            self._write(state)
            return ToolResult(True, True, {"item": item, "inventory": state["inventory"]})

        return ToolResult(
            False, False, error=f"unsupported capability: {call.capability_id}"
        )

    def goal_satisfied(self, goal: Goal, snapshot: WorldSnapshot) -> bool:
        desired_position = list(goal.success_spec.get("target", []))
        required = set(goal.success_spec.get("requires", []))
        return (
            bool(desired_position)
            and snapshot.state["position"] == desired_position
            and required.issubset(set(snapshot.state["inventory"]))
        )

    def _read(self) -> dict[str, Any]:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(
            json.dumps(state, sort_keys=True, indent=2), encoding="utf-8"
        )
